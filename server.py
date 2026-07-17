"""FastAPI backend for the Electron GUI. Wraps the same agents/graphs the CLI
(main.py) uses — this is additive, main.py keeps working standalone.

Run: uvicorn server:app --port 8756
"""
import asyncio
import logging
import os
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import config
from agents import github_importer, prompt_registry, screener
from config import CONFIG
from db.manager import AppliedDB, JobsDB, mark_applied, unmark_applied
from graph.apply_graph import build_apply_graph, load_buildable_jobs
from graph.scrape_graph import build_scrape_graph
from llm.client import RotatingOllamaClient
from tools import latex, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Job Scraper backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Public exposure guard: uvicorn stays on 127.0.0.1, so the only way in from
# outside this PC is the Cloudflare Tunnel. Cloudflare stamps every proxied
# request with Cf-Connecting-Ip; the local desktop app (also on 127.0.0.1) does
# not. So we require the shared token ONLY on tunnel traffic — desktop app is
# untouched. Set TUNNEL_TOKEN in .env to enable; unset = gate off (LAN dev).
# ponytail: /ws/events stays ungated — it only emits scrape progress, can't
# mutate anything; add a query-param token check if that WS ever carries secrets.
TUNNEL_TOKEN = os.environ.get("TUNNEL_TOKEN")


@app.middleware("http")
async def require_tunnel_token(request: Request, call_next):
    via_tunnel = "cf-connecting-ip" in request.headers
    if via_tunnel and request.url.path != "/api/health":
        if not TUNNEL_TOKEN or request.headers.get("x-api-token") != TUNNEL_TOKEN:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)

jobs_db = JobsDB()
applied_db = AppliedDB()


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

# one background run per stage at a time ("apply" covers both the batch
# Build tab and a single-job build from the job detail view)
RUNNERS: dict[str, dict] = {"scrape": {}, "apply": {}}


@app.on_event("startup")
async def on_startup():
    broadcaster.bind_loop(asyncio.get_running_loop())
    threading.Thread(target=_scheduler_loop, daemon=True).start()


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
    config.save_config(new_cfg)
    return {"saved": True}


@app.get("/api/resume-data")
def get_resume_data():
    pcfg = CONFIG["pipeline"]

    def safe_load(path: str) -> str:
        try:
            return config.load_text_file(path)
        except FileNotFoundError:
            return ""

    return {
        "resume_text": safe_load(pcfg["resume_path"]),
        "projects_text": safe_load(pcfg["projects_path"]),
        "experience_roles": CONFIG["experience_roles"],
        "custom_sections": CONFIG.get("custom_sections", []),
        "section_order": CONFIG.get("section_order", []),
    }


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


@app.put("/api/resume-data")
def put_resume_data(payload: dict = Body(...)):
    pcfg = CONFIG["pipeline"]
    if "resume_text" in payload:
        config.save_text_file(pcfg["resume_path"], payload["resume_text"])
    if "projects_text" in payload:
        config.save_text_file(pcfg["projects_path"], payload["projects_text"])
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
    client = RotatingOllamaClient(
        config.collect_ollama_keys(), CONFIG["model"]["pipeline"],
        num_predict=CONFIG["model"]["num_predict"], num_ctx=CONFIG["model"]["num_ctx"],
        temperature=CONFIG["model"]["temperature"],
    )
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
    client = RotatingOllamaClient(
        config.collect_ollama_keys(), CONFIG["model"]["scraping"],
        num_predict=CONFIG["model"]["num_predict"], num_ctx=CONFIG["model"]["num_ctx"],
        temperature=CONFIG["model"]["temperature"],
    )
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
def build_one_job(job_id: int):
    if _is_running("apply"):
        raise HTTPException(409, "a build is already running")
    job = jobs_db.get_by_id(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    _run_apply([job])
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


def _run_apply(jobs: list[dict]):
    stop_event = threading.Event()
    RUNNERS["apply"]["stop_event"] = stop_event

    def work():
        try:
            graph = build_apply_graph(emit=broadcaster.emit, stop_event=stop_event)
            initial_state = {
                "jobs": jobs, "job_index": 0, "current_job": {}, "cover_letter": "",
                "sections": {}, "ats_score": 0, "ats_feedback": {}, "ats_iteration": 0,
                "ats_passed": False, "best_score": 0, "no_improve": 0,
                "_sections_to_rewrite": [], "_best_sections": {}, "results": [],
            }
            graph.invoke(initial_state, {"recursion_limit": 200})
        except Exception as e:
            logging.exception("Apply run failed")
            broadcaster.emit({"type": "log", "level": "ERROR", "message": str(e)})
            broadcaster.emit({"type": "done", "stage": "apply"})

    t = threading.Thread(target=work, daemon=True)
    RUNNERS["apply"]["thread"] = t
    t.start()


@app.post("/api/apply/start")
def start_apply(payload: dict = Body(default={})):
    if _is_running("apply"):
        raise HTTPException(409, "a build is already running")
    verdicts = tuple(payload.get("verdicts", ["yes"]))
    jobs = load_buildable_jobs(verdicts=verdicts)
    if not jobs:
        raise HTTPException(400, "No unbuilt jobs match — change verdicts in Scraped Jobs first")
    _run_apply(jobs)
    return {"started": True, "count": len(jobs)}


@app.post("/api/apply/stop")
def stop_apply():
    stop_event = RUNNERS["apply"].get("stop_event")
    if stop_event:
        stop_event.set()
    return {"stopping": True}


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
