"""FastAPI backend for the Electron GUI. Wraps the same agents/graphs the CLI
(main.py) uses — this is additive, main.py keeps working standalone.

Run: uvicorn server:app --port 8756
"""
import asyncio
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

import config
from agents import (custom_section_writer, experience_writer, github_importer, interviewer, project_writer,
                    prep_guide, prompt_registry, screener, skills_writer)
from agents.ats_rules import latex_to_text
from config import CONFIG
from db.manager import AppliedDB, InterviewDB, JobsDB, mark_applied, unmark_applied
from graph.apply_graph import build_apply_graph, load_buildable_jobs
from graph.scrape_graph import build_scrape_graph
from llm.client import make_client, validate_api_key, validate_gemini_key
from tools import designer, latex, speech, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Job Scraper backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Playwright browsers are bundled with the installer
# PLAYWRIGHT_BROWSERS_PATH env var (set by Electron) points to bundled location
# No installation needed - they're pre-downloaded and included in the package

# Public exposure guard: uvicorn stays on 127.0.0.1, so the only way in from
# outside this PC is the Cloudflare Tunnel. Cloudflare stamps every proxied
# request with Cf-Connecting-Ip; the local desktop app (also on 127.0.0.1) does
# not. So we require the shared token ONLY on tunnel traffic — desktop app is
# untouched. Set TUNNEL_TOKEN in .env to enable; unset = gate off (LAN dev).
# ponytail: /ws/events stays ungated — it only emits scrape progress, can't
# mutate anything; add a query-param token check if that WS ever carries secrets.
TUNNEL_TOKEN_FILE = os.environ.get("TUNNEL_TOKEN_FILE")


def current_tunnel_token():
    # Re-read on every call (not cached) so the desktop app's "change
    # password" button takes effect immediately, no backend restart needed.
    if TUNNEL_TOKEN_FILE:
        try:
            return Path(TUNNEL_TOKEN_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return os.environ.get("TUNNEL_TOKEN")


@app.middleware("http")
async def require_tunnel_token(request: Request, call_next):
    via_tunnel = "cf-connecting-ip" in request.headers
    # Browser CORS preflight (OPTIONS) never carries the custom x-api-token
    # header — that's normal, not an unauthorized caller — so let it through
    # to CORSMiddleware, which answers it. The real request right behind it
    # still gets checked.
    if via_tunnel and request.method != "OPTIONS" and request.url.path != "/api/health":
        # Header for normal fetch()/XHR calls; query param for plain <embed>/<a>
        # links (PDF previews) that can't set custom headers.
        token = request.headers.get("x-api-token") or request.query_params.get("token")
        expected = current_tunnel_token()
        if not expected or token != expected:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)

jobs_db = JobsDB()
applied_db = AppliedDB()
interview_db = InterviewDB()


# ---- live event broadcast (worker threads -> WebSocket clients) -----------

class Broadcaster:
    def __init__(self):
        self._clients: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def connect(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._clients.append(q)
        return q

    def disconnect(self, q: asyncio.Queue):
        if q in self._clients:
            self._clients.remove(q)

    def emit(self, event: dict):
        if self._loop is None:
            return
        for q in list(self._clients):
            self._loop.call_soon_threadsafe(q.put_nowait, event)


broadcaster = Broadcaster()

# one scrape run at a time; builds go through APPLY_QUEUE (see "build queue" below)
RUNNERS: dict[str, dict] = {"scrape": {}}


@app.on_event("startup")
async def on_startup():
    broadcaster.bind_loop(asyncio.get_running_loop())
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    for _ in range(max(1, int(CONFIG.get("pipeline", {}).get("build_workers", 2)))):
        threading.Thread(target=_apply_worker, daemon=True).start()
    _restore_queue()


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    q = broadcaster.connect()
    try:
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.disconnect(q)


# ---- health -----------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True}


# ---- config -------------------------------------------------------------

@app.get("/api/config")
def get_config():
    return CONFIG


@app.put("/api/config")
def put_config(new_cfg: dict = Body(...)):
    # A client holding a config fetched before keys existed would otherwise
    # wipe api_keys on a full-config save — always preserve them if omitted.
    if "api_keys" not in new_cfg:
        new_cfg["api_keys"] = CONFIG.get("api_keys", [])
    # greenhouse_cookie is server-managed (set by /api/greenhouse/connect) —
    # a client's config, fetched before a connect finished, would otherwise wipe it.
    new_scraper = new_cfg.get("scraper") or {}
    new_scraper["greenhouse_cookie"] = CONFIG.get("scraper", {}).get("greenhouse_cookie", "")
    new_cfg["scraper"] = new_scraper
    config.save_config(new_cfg)
    return {"saved": True}


@app.get("/api/greenhouse/status")
def greenhouse_status():
    return {"connected": bool(CONFIG.get("scraper", {}).get("greenhouse_cookie"))}


@app.post("/api/greenhouse/connect")
def greenhouse_connect():
    # Opens a real browser window on this machine for the user to log into
    # my.greenhouse.io in; blocks (in FastAPI's threadpool, not the event
    # loop) until that finishes, times out, or fails.
    from jobspy.greenhouse.cookie_fetcher import get_greenhouse_cookie

    profile_dir = config.DATA_DIR / ".greenhouse_browser_profile"
    try:
        cookie = get_greenhouse_cookie(profile_dir=str(profile_dir))
    except Exception as e:
        raise HTTPException(400, str(e))
    CONFIG.setdefault("scraper", {})["greenhouse_cookie"] = cookie
    config.save_config(CONFIG)
    return {"connected": True}


@app.post("/api/greenhouse/disconnect")
def greenhouse_disconnect():
    CONFIG.setdefault("scraper", {})["greenhouse_cookie"] = ""
    config.save_config(CONFIG)
    return {"disconnected": True}


@app.get("/api/jobright/status")
def jobright_status():
    from jobspy.jobright.session import state_path
    return {"connected": state_path().exists()}


@app.post("/api/jobright/connect")
def jobright_connect():
    from jobspy.jobright.session import login_and_save
    try:
        login_and_save()
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"connected": True}


@app.post("/api/jobright/disconnect")
def jobright_disconnect():
    from jobspy.jobright.session import state_path
    state_path().unlink(missing_ok=True)
    return {"disconnected": True}


@app.get("/api/resume-data")
def get_resume_data():
    pcfg = CONFIG.get("pipeline", {
        "resume_path": "resume.txt",
        "projects_path": "projects.txt",
        "output_dir": "",
        "latex_template": "classic",
        "max_ats_iterations": 5,
        "ats_pass_threshold": 85,
        "max_no_improve": 2,
        "resume_filename": "Resume",
        "cover_letter_filename": "Cover_Letter",
        "use_jd_location": True,
        "default_location": ""
    })

    def safe_load(path: str) -> str:
        try:
            return config.load_text_file(path)
        except FileNotFoundError:
            return ""

    return {
        "resume_text": safe_load(pcfg.get("resume_path", "resume.txt")),
        "projects_text": safe_load(pcfg.get("projects_path", "projects.txt")),
        "experience_roles": CONFIG.get("experience_roles", []),
        "custom_sections": CONFIG.get("custom_sections", []),
        "section_order": CONFIG.get("section_order", []),
    }


# ---- browser extension ------------------------------------------------------

_extension_job_id: int | None = None  # the job open in the Jobs review page


@app.post("/api/extension/current/{job_id}")
def extension_set_current(job_id: int):
    global _extension_job_id
    _extension_job_id = job_id
    return {"ok": True}


@app.get("/api/extension/context")
def extension_context():
    """Everything the autofill extension needs: the job currently open in Jobs review,
    its cover letter, the resume text and the projects."""
    job = _extension_job_id and jobs_db.get_by_id(_extension_job_id)
    data = get_resume_data()
    return {
        "job": job and {k: job.get(k) or "" for k in ("title", "company", "location", "description", "link")},
        "cover_letter": (job or {}).get("cover_letter_content") or "",
        "resume_text": data["resume_text"],
        "projects_text": data["projects_text"],
    }


@app.post("/api/extension/complete")
def extension_complete(payload: dict = Body(...)):
    """Lets the extension use Kairos's configured model and keys instead of its own."""
    client = make_client(CONFIG["model"]["pipeline"], "cover_letter")
    return {"text": client.complete(payload.get("system", ""), payload.get("user", ""), max_tokens=16000)}


@app.get("/api/ollama-key")
def get_ollama_key_status():
    return {"is_set": config.has_ollama_key()}


@app.put("/api/ollama-key")
def put_ollama_key(payload: dict = Body(...)):
    config.save_ollama_key(payload["api_key"])
    return {"saved": True}


@app.get("/api/ollama-keys")
def get_ollama_keys():
    return {"keys": config.get_ollama_keys()}


@app.put("/api/ollama-keys")
def put_ollama_keys(payload: dict = Body(...)):
    config.save_ollama_keys(payload["keys"])
    return {"saved": True}


@app.post("/api/validate/ollama-key")
def validate_ollama_key_route(payload: dict = Body(...)):
    valid, error = validate_api_key(payload.get("api_key", ""))
    return {"valid": valid, "error": error}


@app.post("/api/validate/gemini-key")
def validate_gemini_key_route(payload: dict = Body(...)):
    valid, error = validate_gemini_key(payload.get("api_key", ""))
    return {"valid": valid, "error": error}


@app.post("/api/validate/github-token")
def validate_github_token_route(payload: dict = Body(...)):
    valid, error = github_importer.validate_token(payload.get("token", ""))
    return {"valid": valid, "error": error}


@app.put("/api/resume-data")
def put_resume_data(payload: dict = Body(...)):
    pcfg = CONFIG.get("pipeline", {
        "resume_path": "resume.txt",
        "projects_path": "projects.txt",
        "output_dir": "",
        "latex_template": "classic",
        "max_ats_iterations": 5,
        "ats_pass_threshold": 85,
        "max_no_improve": 2,
        "resume_filename": "Resume",
        "cover_letter_filename": "Cover_Letter",
        "use_jd_location": True,
        "default_location": ""
    })
    if "resume_text" in payload:
        config.save_text_file(pcfg.get("resume_path", "resume.txt"), payload["resume_text"])
    if "projects_text" in payload:
        config.save_text_file(pcfg.get("projects_path", "projects.txt"), payload["projects_text"])
    new_cfg = None
    for key in ("experience_roles", "custom_sections", "section_order"):
        if key in payload:
            new_cfg = new_cfg or dict(CONFIG)
            new_cfg[key] = payload[key]
    if new_cfg is not None:
        config.save_config(new_cfg)
    return {"saved": True}


# ---- prompts --------------------------------------------------------------

@app.get("/api/prompts")
def get_prompts():
    return prompt_registry.list_prompts()


@app.put("/api/prompts/{key}")
def put_prompt(key: str, payload: dict = Body(...)):
    if key not in prompt_registry.REGISTRY:
        raise HTTPException(404, f"unknown prompt key: {key}")
    text = payload.get("text", "")
    ok, err = prompt_registry.validate(key, text)
    if not ok:
        raise HTTPException(400, err)
    new_cfg = dict(CONFIG)
    new_cfg["prompts"] = {**CONFIG.get("prompts", {}), key: text}
    config.save_config(new_cfg)
    return {"saved": True}


@app.post("/api/prompts/{key}/reset")
def reset_prompt(key: str):
    if key not in prompt_registry.REGISTRY:
        raise HTTPException(404, f"unknown prompt key: {key}")
    new_cfg = dict(CONFIG)
    new_cfg["prompts"] = {k: v for k, v in CONFIG.get("prompts", {}).items() if k != key}
    config.save_config(new_cfg)
    return {"text": prompt_registry.REGISTRY[key]["default"]}


# ---- resume templates (formats) ---------------------------------------------

@app.get("/api/templates")
def get_templates():
    return templates.list_templates()


@app.get("/api/templates/{template_id}")
def get_template(template_id: str):
    content = templates.get_content(template_id)
    if content is None:
        raise HTTPException(404, "template not found")
    return {"id": template_id, "content": content}


@app.post("/api/templates")
def add_template(payload: dict = Body(...)):
    try:
        tid = templates.save_template(payload.get("name", ""), payload.get("content", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": tid}


@app.put("/api/templates/{template_id}")
def update_template(template_id: str, payload: dict = Body(...)):
    if templates.get_content(template_id) is None or template_id == "classic":
        raise HTTPException(404 if template_id != "classic" else 400,
                            "template not found" if template_id != "classic" else "built-in template is read-only")
    try:
        templates.save_template(template_id, payload.get("content", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"saved": True}


@app.delete("/api/templates/{template_id}")
def remove_template(template_id: str):
    try:
        templates.delete_template(template_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/templates/{template_id}/activate")
def activate_template(template_id: str):
    try:
        templates.set_active(template_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"active": template_id}


@app.get("/api/templates/{template_id}/preview.pdf")
def template_preview(template_id: str):
    if templates.get_content(template_id) is None:
        raise HTTPException(404, "template not found")
    pdf, error = templates.build_preview(template_id)
    if pdf is None:
        raise HTTPException(422, error or "preview compile failed — check the template's LaTeX")
    return FileResponse(pdf, media_type="application/pdf")


# ---- visual resume designer -------------------------------------------------

@app.get("/api/layout")
def get_layout():
    return designer.get_layout()


@app.put("/api/layout")
def put_layout(payload: dict = Body(...)):
    """Saves style + section list/order/visibility and activates the generated template."""
    return designer.save_layout(payload)


@app.post("/api/layout/preview")
def layout_preview(payload: dict = Body(...)):
    """Compiles an UNSAVED layout draft so the designer can show changes live."""
    pdf, error = designer.preview(payload)
    if pdf is None:
        raise HTTPException(422, error or "preview compile failed")
    return FileResponse(pdf, media_type="application/pdf")


# ---- GitHub project importer ------------------------------------------------

@app.get("/api/github/repos")
def github_repos(username: str):
    token = CONFIG.get("github", {}).get("token", "")
    try:
        return github_importer.list_repos(username, token)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/github/generate-entry")
def github_generate_entry(payload: dict = Body(...)):
    repo_url = payload.get("repo_url", "")
    if not repo_url:
        raise HTTPException(400, "repo_url required")
    token = CONFIG.get("github", {}).get("token", "")
    client = make_client(CONFIG["model"]["pipeline"], "projects")
    try:
        entry = github_importer.generate_project_entry(client, repo_url, token)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"entry": entry}


# ---- jobs (Scraped Jobs tab) ------------------------------------------------

@app.get("/api/jobs")
def list_jobs(verdict: str = "", q: str = ""):
    return jobs_db.search(verdict=verdict, q=q)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    job = jobs_db.get_by_id(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.post("/api/jobs/manual")
def add_manual_job(payload: dict = Body(...)):
    """Adds a job posting you found yourself (not scraped) and runs it through
    the same Screener Agent + prompt as the automated scrape."""
    title = payload.get("title", "").strip()
    company = payload.get("company", "").strip()
    description = payload.get("description", "").strip()
    if not title or not company or not description:
        raise HTTPException(400, "title, company, and description are required")

    job = {
        "title": title,
        "company": company,
        "job_url": payload.get("job_url", "").strip() or f"manual-{uuid.uuid4()}",
        "location": payload.get("location", "").strip(),
        "site": "manual",
        "description": description,
        "date_posted": date.today().isoformat(),
    }

    resume_text = config.load_text_file(CONFIG["pipeline"]["resume_path"])
    client = make_client(CONFIG["model"]["scraping"], "screener")
    try:
        verdict = screener.screen_job(client, job, CONFIG, resume_text)
    except Exception as e:
        raise HTTPException(502, f"Screening failed: {e}")

    row = screener.verdict_to_job_row(job, verdict)
    jobs_db.upsert(row)
    return jobs_db.get_by_link(job["job_url"])


@app.put("/api/jobs/{job_id}/verdict")
def put_verdict(job_id: int, payload: dict = Body(...)):
    verdict = payload.get("verdict", "")
    if verdict not in ("yes", "maybe", "no"):
        raise HTTPException(400, "verdict must be yes/maybe/no")
    jobs_db.set_verdict(job_id, verdict)
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int):
    jobs_db.delete_by_id(job_id)
    return {"ok": True}


@app.post("/api/jobs/remove-no")
def remove_no_jobs():
    return {"removed": jobs_db.delete_by_verdict("no")}


@app.post("/api/jobs/remove-not-applied")
def remove_not_applied_jobs():
    return {"removed": jobs_db.delete_not_applied()}


@app.post("/api/jobs/remove-all")
def remove_all_jobs():
    return {"removed": jobs_db.delete_all()}


@app.post("/api/jobs/remove-blacklisted")
def remove_blacklisted_jobs():
    companies = CONFIG["screener"].get("blacklisted_companies", [])
    return {"removed": jobs_db.delete_by_companies(companies)}


@app.post("/api/jobs/{job_id}/apply")
def apply_job(job_id: int):
    row = mark_applied(jobs_db, applied_db, job_id, date.today().isoformat())
    if not row:
        raise HTTPException(404, "job not found")
    return row


@app.post("/api/jobs/{job_id}/build")
def build_one_job(job_id: int, payload: dict = Body(default={})):
    job = jobs_db.get_by_id(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    _run_apply([job], use_claude=payload.get("engine") == "claude")
    return {"started": True}


def _pdf_response_from_row(row: dict | None, field: str, not_found_msg: str) -> FileResponse:
    path = row and row.get(field)
    if not row or not path or not Path(path).exists():
        raise HTTPException(404, not_found_msg)
    return FileResponse(path, media_type="application/pdf")


@app.get("/api/jobs/{job_id}/resume.pdf")
def get_job_resume_pdf(job_id: int):
    return _pdf_response_from_row(jobs_db.get_by_id(job_id), "resume_path", "resume not built yet")


@app.get("/api/jobs/{job_id}/cover.pdf")
def get_job_cover_pdf(job_id: int):
    return _pdf_response_from_row(jobs_db.get_by_id(job_id), "cover_path", "cover letter not built yet")


@app.post("/api/jobs/{job_id}/compile")
def compile_job(job_id: int, payload: dict = Body(...)):
    """Overleaf-style recompile: takes edited LaTeX, compiles it, saves it back."""
    job = jobs_db.get_by_id(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return _compile_and_save(payload.get("latex", ""), job["company"], job["title"],
                              lambda resume_path: jobs_db.save_build_artifacts(
                                  job_id, payload.get("latex", ""), job.get("cover_letter_content", "") or "",
                                  job.get("ats_score", 0) or 0, str(resume_path), job.get("cover_path", "") or ""))


@app.get("/api/rebuildable-sections")
def rebuildable_sections():
    """Sections the editor's rebuilder can regenerate: the three core writer
    sections plus any user-defined custom sections."""
    core = [{"id": "skills", "name": "Skills"}, {"id": "experience", "name": "Experience"},
            {"id": "projects", "name": "Projects"}]
    custom = [{"id": s["id"], "name": s.get("name", s["id"])}
              for s in CONFIG.get("custom_sections", []) if s.get("id") and s.get("kind") != "static"]
    return core + custom


@app.post("/api/jobs/{job_id}/rebuild-section")
def rebuild_section(job_id: int, payload: dict = Body(...)):
    """Regenerate one resume section for a built job, optionally steered by a user
    message. Core sections (skills/experience/projects): a message drives a
    surgical rebuild against the current text; blank regenerates from scratch.
    Custom sections always regenerate, with the message as an extra instruction.
    Splices the fresh block into the supplied LaTeX (the editor's current text)
    and returns it — the caller reviews and hits Compile & Save. Nothing is
    persisted here."""
    job = jobs_db.get_by_id(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    section_id = payload.get("section_id", "")
    message = (payload.get("message", "") or "").strip()
    title, company = job.get("title", ""), job.get("company", "")
    description = job.get("description", "") or f"{title} role at {company}."
    profile = CONFIG["profile"]
    pcfg = CONFIG["pipeline"]
    existing_resume = config.load_text_file(pcfg["resume_path"])
    source = payload.get("latex", "") or job.get("latex_content", "") or ""

    custom = {s["id"]: s for s in CONFIG.get("custom_sections", []) if s.get("id")}
    name_map = {s.get("name", "").lower(): sid for sid, s in custom.items() if s.get("name")}
    heading, prior = latex.find_section(source, section_id, name_map)

    client = make_client(CONFIG["model"]["pipeline"],
                         section_id if section_id in ("skills", "experience", "projects") else "summary")
    try:
        if section_id == "skills":
            block = (skills_writer.rebuild(client, title, company, description, message, prior)
                     if message and prior else
                     skills_writer.write(client, title, company, description, existing_resume))
        elif section_id == "experience":
            roles = CONFIG["experience_roles"]
            block = (experience_writer.rebuild(client, title, company, description, message, prior)
                     if message and prior else
                     experience_writer.write(client, title, company, description, existing_resume, roles))
        elif section_id == "projects":
            projects_text = config.load_text_file(pcfg["projects_path"])
            block = (project_writer.rebuild(client, title, company, description, message, prior, projects_text,
                                           count=pcfg.get("project_count"))
                     if message and prior else
                     project_writer.write(client, title, company, description, existing_resume, projects_text,
                                           bullets=pcfg.get("project_bullets", 3),
                                          count=pcfg.get("project_count")))
        elif section_id in custom:
            # base it on the tailored resume (minus this section) when one exists
            others = latex.replace_section(source, heading, "") if heading and source else source
            block = custom_section_writer.write(
                client, custom[section_id], profile.get("full_name", ""), title, company, description,
                others or existing_resume, experience_yrs=profile.get("experience_yrs", ""), custom_instruction=message)
        else:
            raise HTTPException(404, f"section '{section_id}' is not rebuildable")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"rebuild failed: {e}")

    fallback_name = heading or custom.get(section_id, {}).get("name") or section_id
    return {"section_id": section_id, "block": block,
            "latex": latex.replace_section(source, fallback_name, block)}


# ---- applied --------------------------------------------------------------

@app.get("/api/applied")
def list_applied():
    return applied_db.get_all()


@app.get("/api/applied/{applied_id}")
def get_applied(applied_id: int):
    row = applied_db.get_by_id(applied_id)
    if not row:
        raise HTTPException(404, "not found")
    return row


@app.delete("/api/applied/{applied_id}")
def delete_applied(applied_id: int):
    applied_db.delete_by_id(applied_id)
    return {"ok": True}


@app.post("/api/applied/{applied_id}/unapply")
def unapply(applied_id: int):
    job = unmark_applied(jobs_db, applied_db, applied_id)
    if not job:
        raise HTTPException(404, "not found")
    return job


@app.post("/api/applied/{applied_id}/compile")
def compile_applied(applied_id: int, payload: dict = Body(...)):
    row = applied_db.get_by_id(applied_id)
    if not row:
        raise HTTPException(404, "not found")
    latex_code = payload.get("latex", "")

    def persist(resume_path):
        applied_db.update_tex(applied_id, latex_code, str(resume_path))

    return _compile_and_save(latex_code, row["company"], row["title"], persist)


def _compile_and_save(latex_code: str, company: str, title: str, persist) -> dict:
    pcfg = CONFIG["pipeline"]
    resume_path = latex.build_output_path(pcfg["output_dir"], company, title, pcfg["resume_filename"], "pdf")
    compiled = latex.compile_latex_to_pdf(latex_code, resume_path)
    persist(resume_path)
    return {"compiled": compiled, "resume_path": str(resume_path)}


def _pdf_response(applied_id: int, field: str) -> FileResponse:
    row = applied_db.get_by_id(applied_id)
    path = row and row.get(field)
    if not row or not path or not Path(path).exists():
        raise HTTPException(404, f"{field} not found for applied job {applied_id}")
    return FileResponse(path, media_type="application/pdf")


@app.get("/api/outputs/{applied_id}/resume.pdf")
def get_resume_pdf(applied_id: int):
    return _pdf_response(applied_id, "resume_path")


@app.get("/api/outputs/{applied_id}/cover.pdf")
def get_cover_pdf(applied_id: int):
    return _pdf_response(applied_id, "cover_path")


# ---- stats (dashboard) -----------------------------------------------------

@app.get("/api/stats")
def stats():
    return {
        "pending_jobs": jobs_db.count(),
        "applied_count": applied_db.count(),
        "total_extracted": jobs_db.lifetime_count(),
        # ponytail: counts resumes still on record; built-then-deleted jobs drop
        # out — add a meta counter if a true lifetime number ever matters.
        "resumes_created": jobs_db.built_count() + applied_db.built_count(),
        "verdict_counts": jobs_db.verdict_counts(),
        "applied_by_date": [{"date": d, "count": c} for d, c in applied_db.applied_by_date()],
        "ats_scores": applied_db.ats_scores(),
        "top_missing_skills": jobs_db.top_missing_skills(10),
        "site_counts": jobs_db.site_counts(),
        "recent_applied": applied_db.recent(5),
    }


# ---- scrape / apply runs ---------------------------------------------------

def _is_running(stage: str) -> bool:
    t = RUNNERS[stage].get("thread")
    return bool(t and t.is_alive())


def _run_scrape():
    stop_event = threading.Event()
    RUNNERS["scrape"]["stop_event"] = stop_event

    def work():
        try:
            graph = build_scrape_graph(emit=broadcaster.emit, stop_event=stop_event)
            graph.invoke({"jobs": [], "screened": []})
        except Exception as e:
            logging.exception("Scrape run failed")
            broadcaster.emit({"type": "log", "level": "ERROR", "message": str(e)})
            broadcaster.emit({"type": "done", "stage": "scrape"})
            return

    t = threading.Thread(target=work, daemon=True)
    RUNNERS["scrape"]["thread"] = t
    t.start()


@app.post("/api/scrape/start")
def start_scrape():
    if _is_running("scrape"):
        raise HTTPException(409, "scrape already running")
    _run_scrape()
    return {"started": True}


@app.post("/api/scrape/stop")
def stop_scrape():
    stop_event = RUNNERS["scrape"].get("stop_event")
    if stop_event:
        stop_event.set()
    return {"stopping": True}


# ---- build queue ------------------------------------------------------------
# Every build request (batch or single job) is queued one job at a time; a small
# pool of worker threads (pipeline.build_workers, default 2) pulls and runs them.
#
# Each queued job owns a state dict {stop, use_claude}; its `stop` Event is what
# makes cancel work per job (running: wind down at next checkpoint; waiting:
# skipped when a worker picks it up). The queue is mirrored to build_queue.json
# so builds still pending at shutdown resume on the next start.

APPLY_QUEUE: queue.Queue = queue.Queue()
_QUEUE_FILE = config.DATA_DIR / "build_queue.json"
_apply_lock = threading.Lock()
_apply_jobs: dict[int, dict] = {}    # job id -> state, for jobs waiting or running
_apply_batch = {"total": 0, "done": 0}
_output_locks: dict[tuple, threading.Lock] = {}   # same company+title share an output folder


def _persist_queue():
    """Call with _apply_lock held."""
    try:
        _QUEUE_FILE.write_text(json.dumps([{"id": i, "use_claude": s["use_claude"]} for i, s in _apply_jobs.items()]),
                               encoding="utf-8")
    except OSError:
        logging.warning("Could not write %s", _QUEUE_FILE)


def _apply_finish_one(job_id: int, state: dict):
    with _apply_lock:
        if _apply_jobs.get(job_id) is state:    # a re-queued job's newer state stays put
            del _apply_jobs[job_id]
        _apply_batch["done"] += 1
        idle = not _apply_jobs
        if idle:
            _apply_batch.update(total=0, done=0)
        _persist_queue()
    if idle:
        broadcaster.emit({"type": "done", "stage": "apply"})


def _apply_worker():
    while True:
        job, state = APPLY_QUEUE.get()
        company, title = job.get("company", ""), job.get("title", "")

        def emit(event: dict):
            if event.get("type") == "done":
                return  # each graph run is one job; "done" fires once the whole queue drains
            if event.get("type") == "apply_progress":
                event = {**event, "job_index": _apply_batch["done"], "total": _apply_batch["total"]}
            broadcaster.emit(event)

        try:
            if state["stop"].is_set():          # cancelled while still waiting
                broadcaster.emit({"type": "apply_progress", "company": company, "title": title, "stage": "cancelled",
                                  "job_index": _apply_batch["done"], "total": _apply_batch["total"], "job_id": job["id"]})
                continue
            with _apply_lock:
                out_lock = _output_locks.setdefault((company.lower(), title.lower()), threading.Lock())
            with out_lock:                      # two same-named jobs would write the same files
                graph = build_apply_graph(emit=emit, stop_event=state["stop"], use_claude=state["use_claude"])
                graph.invoke({
                    "jobs": [job], "job_index": 0, "current_job": {}, "cover_letter": "",
                    "sections": {}, "ats_score": 0, "ats_feedback": {}, "ats_iteration": 0,
                    "ats_passed": False, "best_score": 0, "no_improve": 0,
                    "_sections_to_rewrite": [], "_best_sections": {}, "results": [],
                }, {"recursion_limit": 200})
        except Exception as e:
            logging.exception("Build failed for %s @ %s", title, company)
            broadcaster.emit({"type": "log", "level": "ERROR", "message": str(e)})
        finally:
            _apply_finish_one(job["id"], state)


def _run_apply(jobs: list[dict], use_claude: bool = False) -> int:
    """Queue jobs for building; returns how many were newly queued."""
    new = []
    with _apply_lock:
        for j in jobs:
            existing = _apply_jobs.get(j["id"])
            if existing and not existing["stop"].is_set():
                continue                        # already waiting/running
            state = {"stop": threading.Event(), "use_claude": use_claude}
            _apply_jobs[j["id"]] = state        # replaces a cancelled-but-not-yet-drained entry
            new.append((j, state))
        _apply_batch["total"] += len(new)
        total = _apply_batch["total"]
        _persist_queue()
    for j, state in new:
        broadcaster.emit({"type": "apply_progress", "company": j.get("company", ""), "title": j.get("title", ""),
                          "stage": "queued", "job_index": _apply_batch["done"], "total": total, "job_id": j["id"]})
        APPLY_QUEUE.put((j, state))
    return len(new)


def _restore_queue():
    try:
        entries = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for use_claude in (False, True):
        jobs = [j for e in entries if bool(e.get("use_claude")) == use_claude
                and (j := jobs_db.get_by_id(e["id"])) and not j.get("latex_content")]
        if jobs:
            _run_apply(jobs, use_claude)


@app.post("/api/apply/start")
def start_apply(payload: dict = Body(default={})):
    verdicts = tuple(payload.get("verdicts", ["yes"]))
    jobs = load_buildable_jobs(verdicts=verdicts)
    if not jobs:
        raise HTTPException(400, "No unbuilt jobs match — change verdicts in Scraped Jobs first")
    return {"started": True, "count": _run_apply(jobs)}


@app.post("/api/apply/stop")
def stop_apply():
    with _apply_lock:
        for s in _apply_jobs.values():
            s["stop"].set()
    return {"stopping": True}


@app.post("/api/jobs/{job_id}/build/cancel")
def cancel_build(job_id: int):
    with _apply_lock:
        state = _apply_jobs.get(job_id)
        if state:
            state["stop"].set()
    return {"cancelling": bool(state)}


@app.get("/api/apply/queue")
def apply_queue_status():
    with _apply_lock:
        return {"running": bool(_apply_jobs), "job_ids": list(_apply_jobs),
                "total": _apply_batch["total"], "done": _apply_batch["done"]}


# ---- scheduler --------------------------------------------------------------

@app.get("/api/scheduler")
def get_scheduler():
    return CONFIG.get("scheduler", {"enabled": False, "time": "08:00"})


@app.put("/api/scheduler")
def put_scheduler(payload: dict = Body(...)):
    new_cfg = dict(CONFIG)
    new_cfg["scheduler"] = payload
    config.save_config(new_cfg)
    return {"saved": True}


def _scheduler_loop():
    last_run_date = None
    while True:
        time.sleep(30)
        sched = CONFIG.get("scheduler", {})
        if not sched.get("enabled"):
            continue
        now = datetime.now()
        if now.date().isoformat() == last_run_date:
            continue
        try:
            hh, mm = (int(x) for x in sched.get("time", "08:00").split(":"))
        except ValueError:
            continue
        if now.hour == hh and now.minute == mm:
            last_run_date = now.date().isoformat()
            if not _is_running("scrape"):
                broadcaster.emit({"type": "log", "level": "INFO", "message": "Scheduled scrape starting"})
                _run_scrape()


# ---- interview prep: speech -------------------------------------------------

_AUDIO_SUFFIX = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav",
                 "audio/mpeg": ".mp3", "audio/mp4": ".m4a"}


@app.get("/api/speech/status")
def speech_status():
    return speech.status()


@app.post("/api/speech/download")
def speech_download(payload: dict = Body(...)):
    what = payload.get("what", "")
    if what != "kokoro" and not what.startswith("whisper:"):
        raise HTTPException(400, "what must be 'kokoro' or 'whisper:<size>'")
    speech.start_download(what)
    return {"started": True}


@app.post("/api/speech/warmup")
def speech_warmup():
    speech.warmup()
    return {"ok": True}


@app.get("/api/speech/voices")
def speech_voices():
    return {"kokoro": speech.kokoro_voices()}


@app.post("/api/speech/transcribe")
async def speech_transcribe(request: Request):
    # raw audio body (not multipart) — avoids a python-multipart dependency
    audio = await request.body()
    if len(audio) < 200:
        raise HTTPException(400, "No audio received")
    suffix = _AUDIO_SUFFIX.get(request.headers.get("content-type", "").split(";")[0], ".webm")
    try:
        return await run_in_threadpool(speech.transcribe, audio, suffix)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/speech/tts")
def speech_tts(payload: dict = Body(...)):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is empty")
    out = speech.synthesize(text[:2000], payload.get("settings"))
    if out is None:   # browser engine, or every server engine failed: the renderer speaks it
        return Response(status_code=204)
    return Response(out[0], media_type=out[1])


# ---- interview prep: sessions -----------------------------------------------

def _job_context(source: str, job_id) -> dict:
    if not job_id:
        return {}
    row = (applied_db if source == "applied" else jobs_db).get_by_id(int(job_id))
    if not row:
        raise HTTPException(404, "linked job not found")
    # the resume actually built for this job; empty = not built, agents fall back to resume.txt
    tex = row.get("tex_content") or row.get("latex_content") or ""
    return {"company": row.get("company", ""), "title": row.get("title", ""),
            "description": row.get("description", ""), "source": source, "job_id": int(job_id),
            "resume": latex_to_text(tex.split(r"\begin{document}")[-1]) if tex else ""}


def _interviewer_reply(sid: int) -> dict:
    """Generates and stores the interviewer's next turn; ends the session on the closing turn."""
    session = interview_db.get_session(sid)
    try:
        out = interviewer.next_turn(session)
    except Exception as e:
        logging.exception("interviewer turn failed")
        raise HTTPException(502, f"Interviewer AI failed: {e}")
    turn = interview_db.add_turn(sid, "interviewer", out["reply"], meta=out["meta"])
    if out["done"]:
        interview_db.end_session(sid)
    return {"turn": turn, "done": out["done"]}


@app.post("/api/interview/sessions")
def interview_create(payload: dict = Body(...)):
    kind = payload.get("kind", "general")
    if kind not in interviewer.KINDS:
        raise HTTPException(400, f"unknown interview kind: {kind}")
    cfg = payload.get("config") or {}
    if kind == "technical":
        cfg["topics"] = [str(t).strip()[:40] for t in cfg.get("topics") or [] if str(t).strip()][:8]
        if not cfg["topics"]:
            raise HTTPException(400, "Pick at least one topic for a tech-stack interview")
    ctx = _job_context(cfg.get("job_source", "jobs"), cfg.get("job_id"))
    role, company = ctx.get("title") or cfg.get("role") or "", ctx.get("company") or cfg.get("company") or ""
    title = f"{role} @ {company}" if role and company else role or company or "Practice"
    sid = interview_db.create_session(kind, title, cfg, ctx)
    ctx["plan"] = interviewer.plan_questions(interview_db.get_session(sid))
    interview_db.update_context(sid, ctx)
    try:
        _interviewer_reply(sid)
    except HTTPException:
        pass   # session exists; the room offers Retry, which calls /answer with no text
    return interview_db.get_session(sid)


@app.get("/api/interview/sessions")
def interview_list():
    return interview_db.list_sessions()


@app.get("/api/interview/sessions/{sid}")
def interview_get(sid: int):
    session = interview_db.get_session(sid)
    if not session:
        raise HTTPException(404, "session not found")
    return session


@app.delete("/api/interview/sessions/{sid}")
def interview_delete(sid: int):
    import shutil
    interview_db.delete_session(sid)
    shutil.rmtree(config.DATA_DIR / "interviews" / str(sid), ignore_errors=True)
    return {"deleted": True}


@app.post("/api/interview/sessions/{sid}/answer")
def interview_answer(sid: int, payload: dict = Body(...)):
    """Body: {text, words?, duration?, edit_turn_id?, skip?}. Empty text = just
    get the interviewer's next turn (retry after an AI failure). edit_turn_id
    replaces that answer and drops everything said after it. The answer is
    scored in the background while the interviewer replies."""
    session = interview_db.get_session(sid)
    if not session:
        raise HTTPException(404, "session not found")
    if session["status"] != "active":
        raise HTTPException(409, "This interview has ended")
    text = (payload.get("text") or "").strip()
    if payload.get("edit_turn_id"):
        interview_db.delete_turns_from(sid, int(payload["edit_turn_id"]))
    candidate = None
    if payload.get("skip"):
        candidate = interview_db.add_turn(sid, "candidate", "(skipped this question)", meta={"skipped": True})
    elif text:
        candidate = interview_db.add_turn(sid, "candidate", text, payload.get("words"), payload.get("duration") or 0)
        threading.Thread(target=_score_answer, args=(sid, candidate["id"]), daemon=True).start()
    turns = interview_db.get_session(sid)["turns"]
    if turns and turns[-1]["speaker"] == "interviewer":
        raise HTTPException(400, "Nothing to respond to — send an answer")
    reply = _interviewer_reply(sid)
    return {"candidate": candidate, "interviewer": reply["turn"], "done": reply["done"]}


def _score_answer(sid: int, tid: int):
    session = interview_db.get_session(sid)
    if not session:
        return
    try:
        result = interviewer.evaluate(session, tid)
    except Exception as e:
        logging.warning("scoring answer %s failed: %s", tid, e)
        result = {"error": str(e)[:300]}
    if result is not None and interview_db.get_turn(tid):   # turn may have been edited away meanwhile
        interview_db.set_eval(tid, result)


@app.post("/api/interview/sessions/{sid}/score")
def interview_score_missing(sid: int):
    """Re-scores answers whose scoring failed or never ran (e.g. backend restarted mid-interview)."""
    session = interview_db.get_session(sid)
    if not session:
        raise HTTPException(404, "session not found")
    todo = [t["id"] for t in session["turns"] if t["speaker"] == "candidate"
            and not (t["meta"] or {}).get("skipped") and (not t["eval"] or "error" in t["eval"])]
    for tid in todo:
        threading.Thread(target=_score_answer, args=(sid, tid), daemon=True).start()
    return {"scoring": len(todo)}


@app.post("/api/interview/sessions/{sid}/end")
def interview_end(sid: int):
    interview_db.end_session(sid)
    return interview_db.get_session(sid)


# ---- interview prep: study guides -------------------------------------------

@app.post("/api/prep")
def prep_create(payload: dict = Body(...)):
    """Body: {job_source, job_id} or {role, company}. Takes ~30-60s (web research + generation)."""
    ctx = _job_context(payload.get("job_source", "jobs"), payload.get("job_id"))
    title = ctx.get("title") or (payload.get("role") or "").strip()
    company = ctx.get("company") or (payload.get("company") or "").strip()
    if not title and not company:
        raise HTTPException(400, "Pick a job, or enter a role or company")
    try:
        content = prep_guide.generate(company, title, ctx.get("description", ""), ctx.get("resume", ""))
    except Exception as e:
        logging.exception("prep guide failed")
        raise HTTPException(502, f"Couldn't build the prep guide: {e}")
    gid = interview_db.save_guide(title, company, ctx.get("source", ""), ctx.get("job_id"), content)
    return interview_db.get_guide(gid)


@app.get("/api/prep")
def prep_list():
    return interview_db.list_guides()


@app.get("/api/prep/{gid}")
def prep_get(gid: int):
    guide = interview_db.get_guide(gid)
    if not guide:
        raise HTTPException(404, "guide not found")
    return guide


@app.post("/api/prep/{gid}/qa")
def prep_more_qa(gid: int, payload: dict = Body(...)):
    """Body: {category}. Appends 5 new practice Q&As in that category (~15-30s)."""
    category = payload.get("category", "")
    if category not in prep_guide.QA_CATEGORIES:
        raise HTTPException(400, f"category must be one of {', '.join(prep_guide.QA_CATEGORIES)}")
    guide = interview_db.get_guide(gid)
    if not guide:
        raise HTTPException(404, "guide not found")
    try:
        ctx = _job_context(guide["job_source"], guide["job_id"])
    except HTTPException:  # linked job was deleted since; build from the title alone
        ctx = {}
    description = ctx.get("description", "")
    content = guide["content"]
    qa = content.get("qa") or []
    try:
        new = prep_guide.more_qa(guide["company"], guide["title"], description, content.get("company_info") or {},
                                 category, [q.get("question", "") for q in qa], resume=ctx.get("resume", ""))
    except Exception as e:
        logging.exception("more prep Q&A failed")
        raise HTTPException(502, f"Couldn't generate more questions: {e}")
    content["qa"] = qa + new
    interview_db.update_guide_content(gid, content)
    return interview_db.get_guide(gid)


@app.delete("/api/prep/{gid}")
def prep_delete(gid: int):
    interview_db.delete_guide(gid)
    return {"deleted": True}


@app.get("/api/interview/turns/{tid}/speech")
def interview_turn_speech(tid: int):
    turn = interview_db.get_turn(tid)
    if not turn or turn["speaker"] != "interviewer":
        raise HTTPException(404, "turn not found")
    s = speech.settings()
    voice = s["kokoro_voice"] if s["tts_engine"] == "kokoro" else s["edge_voice"]
    # cached per voice setting: replays (Repeat question) are instant, a voice change re-renders
    folder = config.DATA_DIR / "interviews" / str(turn["session_id"])
    stem = f"{tid}_{s['tts_engine']}_{voice}_{s['tts_speed']}"
    for ext, mime in ((".wav", "audio/wav"), (".mp3", "audio/mpeg")):
        if (folder / (stem + ext)).exists():
            return FileResponse(folder / (stem + ext), media_type=mime)
    out = speech.synthesize(turn["text"])
    if out is None:
        return Response(status_code=204)
    audio, mime = out
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (stem + (".wav" if mime == "audio/wav" else ".mp3"))).write_bytes(audio)
    return Response(audio, media_type=mime)
