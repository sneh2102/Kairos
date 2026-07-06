"""apply_graph — the core multi-agent pipeline: parallel Skills/Experience/
Project writers -> ATS Checker -> (loop: rebuild only flagged sections) -> save.

Runs the same for a batch (Build tab, "yes" jobs) or a single job (Scraped
Jobs detail's "Build resume & cover letter" button) — both just pass a
`jobs` list of JobsDB rows into the initial state.

Building a resume no longer marks a job "applied" — it only saves the
generated artifacts back onto the JobsDB row. Moving a job into applied.db
is a separate explicit action (server.py's /api/jobs/{id}/apply).
"""
import logging
import threading
import time
from typing import Callable

from langgraph.graph import END, START, StateGraph

from agents import ats_checker, custom_section_writer, experience_writer, optimizer, project_writer, skills_writer
from config import CONFIG, collect_ollama_keys, load_text_file
from db.manager import JobsDB
from graph.state import ApplyState
from llm.client import RotatingOllamaClient
from tools import cover_letter as cover_letter_tool
from tools import latex

WRITER_SECTIONS = ("skills", "experience", "projects")


def build_apply_graph(emit: Callable[[dict], None] | None = None,
                       stop_event: threading.Event | None = None):
    """`emit`/`stop_event`: see scrape_graph.build_scrape_graph — same contract."""
    emit = emit or (lambda event: None)
    stop_event = stop_event or threading.Event()
    jobs_db = JobsDB()
    client = RotatingOllamaClient(
        collect_ollama_keys(), CONFIG["model"]["pipeline"],
        num_predict=CONFIG["model"]["num_predict"], num_ctx=CONFIG["model"]["num_ctx"],
        temperature=CONFIG["model"]["temperature"],
    )
    pcfg = CONFIG["pipeline"]
    existing_resume = load_text_file(pcfg["resume_path"])
    projects_text = load_text_file(pcfg["projects_path"])
    profile = CONFIG["profile"]
    experience_roles = CONFIG["experience_roles"]
    custom_sections = CONFIG.get("custom_sections", [])
    section_order = CONFIG["section_order"]
    max_iterations = pcfg["max_ats_iterations"]
    pass_threshold = pcfg["ats_pass_threshold"]
    max_no_improve = pcfg.get("max_no_improve", 2)
    output_dir = pcfg["output_dir"]

    # ---- nodes ---------------------------------------------------------

    def next_job(state: ApplyState) -> dict:
        idx = state["job_index"]
        jobs = state["jobs"]
        if idx >= len(jobs) or stop_event.is_set():
            if stop_event.is_set():
                emit({"type": "log", "level": "WARNING", "message": "Stopped by user"})
            emit({"type": "done", "stage": "apply"})
            return {"job_index": len(jobs)}

        job = jobs[idx]
        title, company = job.get("title", ""), job.get("company", "")
        description = job.get("description", "") or f"{title} role at {company}."
        location = job.get("location") if pcfg["use_jd_location"] else None
        location = location or pcfg["default_location"]

        emit({"type": "apply_progress", "company": company, "title": title, "stage": "building",
              "job_index": idx, "total": len(jobs)})

        header = latex.build_header(profile, location, profile.get("include_links", True))
        education = latex.build_education(profile)
        sections = {"header": header, "education": education, "skills": "", "experience": "", "projects": ""}

        for section_cfg in custom_sections:
            sid = section_cfg.get("id")
            if not sid:
                continue
            try:
                sections[sid] = custom_section_writer.write(
                    client, section_cfg, profile.get("full_name", ""), title, company, description, existing_resume,
                    experience_yrs=profile.get("experience_yrs", ""),
                )
            except Exception as e:
                logging.warning("Custom section %s failed for %s @ %s: %s", sid, title, company, e)
                sections[sid] = ""

        try:
            cover = cover_letter_tool.generate(client, title, company, description, existing_resume, profile)
        except Exception as e:
            logging.warning("Cover letter generation failed for %s @ %s: %s", title, company, e)
            cover = ""

        return {
            "current_job": job,
            "cover_letter": cover,
            "sections": sections,
            "ats_score": 0,
            "ats_feedback": {},
            "ats_iteration": 0,
            "ats_passed": False,
            "best_score": 0,
            "no_improve": 0,
            "_best_sections": {},
        }


    def route_after_next_job(state: ApplyState):
        if state["job_index"] >= len(state["jobs"]):
            return END
        return list(WRITER_SECTIONS)

    def make_writer_node(section: str):
        def node(state: ApplyState) -> dict:
            job = state["current_job"]
            title, company = job.get("title", ""), job.get("company", "")
            # feed-forward: name the JD's ATS keywords in the prompt so the first
            # draft targets them, instead of discovering them via feedback loops
            description = job.get("description", "") + optimizer.keyword_hint(job.get("description", ""))
            first_pass = state["ats_iteration"] == 0
            try:
                if section == "skills":
                    text = (skills_writer.write(client, title, company, description, existing_resume)
                            if first_pass else
                            skills_writer.rebuild(client, title, company, description,
                                                   state["ats_feedback"].get("skills_feedback", ""),
                                                   state["sections"].get("skills", "")))
                elif section == "experience":
                    text = (experience_writer.write(client, title, company, description, existing_resume, experience_roles)
                            if first_pass else
                            experience_writer.rebuild(client, title, company, description,
                                                       state["ats_feedback"].get("experience_feedback", ""),
                                                       state["sections"].get("experience", "")))
                else:
                    text = (project_writer.write(client, title, company, description, existing_resume, projects_text)
                            if first_pass else
                            project_writer.rebuild(client, title, company, description,
                                                    state["ats_feedback"].get("projects_feedback", ""),
                                                    state["sections"].get("projects", ""), projects_text))
            except Exception as e:
                logging.warning("%s writer failed for %s @ %s: %s", section, title, company, e)
                text = state["sections"].get(section, "")
            return {"sections": {section: text}}
        return node

    def optimize(state: ApplyState) -> dict:
        """Deterministic post-pass: keyword injection, AI-tell swaps, verb
        de-dup, grammar-lite, metric micro-fix. Guarantees the rule-engine
        points instead of hoping the writers followed instructions."""
        job = state["current_job"]
        try:
            updated = optimizer.optimize_sections(client, state["sections"], job.get("description", ""))
        except Exception as e:
            logging.warning("Optimizer failed for %s @ %s (sections kept): %s",
                            job.get("title", ""), job.get("company", ""), e)
            updated = {}
        return {"sections": updated} if updated else {}

    def check_ats(state: ApplyState) -> dict:
        job = state["current_job"]
        title, company = job.get("title", ""), job.get("company", "")
        emit({"type": "apply_progress", "company": company, "title": title, "stage": "checking_ats",
              "job_index": state["job_index"], "total": len(state["jobs"]),
              "iteration": state["ats_iteration"] + 1})
        full_latex = latex.reassemble(state["sections"], section_order)
        result = ats_checker.check(client, title, job.get("description", ""), full_latex)

        score = result["score"]
        best_score = max(score, state["best_score"])
        no_improve = 0 if score > state["best_score"] else state["no_improve"] + 1

        # snapshot the highest-scoring HONEST version — if a later rebuild makes
        # things worse, save_output falls back to this instead of the last draft
        prev_best = state.get("_best_sections") or {}
        if score >= prev_best.get("score", -1):
            best_sections = {"score": score, "sections": dict(state["sections"])}
        else:
            best_sections = prev_best

        # surface the FULL breakdown in the Logs tab so it's clear WHY the score
        # is what it is (which category leaked, which keywords are still missing)
        bd = result.get("breakdown", {})
        w = ats_checker.ats_rules.WEIGHTS
        emit({"type": "log", "level": "INFO", "message": (
            f"ATS {score}/100 (deterministic) for {title} @ {company} (iter {state['ats_iteration'] + 1}) — "
            f"keywords {bd.get('keywords', '?')}/{w['keywords']}, domain {bd.get('domain', '?')}/{w['domain']}, "
            f"metrics {bd.get('metrics', '?')}/{w['metrics']}, verbs {bd.get('verbs', '?')}/{w['verbs']}, "
            f"humanize {bd.get('humanize', '?')}/{w['humanize']}, structure {bd.get('structure', '?')}/{w['structure']}"
        )})
        jd_dom, res_dom = result.get("jd_domains", []), result.get("resume_domains", [])
        if jd_dom:
            emit({"type": "log", "level": "INFO",
                  "message": f"  domain: JD wants [{'/'.join(jd_dom)}], resume reads as "
                             f"[{'/'.join(res_dom) or 'unclear'}] (alignment {result.get('domain_alignment', 0)})"})
        if result.get("missing_keywords"):
            emit({"type": "log", "level": "INFO",
                  "message": "  missing JD keywords: " + ", ".join(result["missing_keywords"][:12])})
        if result.get("sections_to_rewrite"):
            emit({"type": "log", "level": "INFO",
                  "message": "  rewriting sections: " + ", ".join(result["sections_to_rewrite"])})
        for s in result.get("suggestions", [])[:3]:
            emit({"type": "log", "level": "INFO", "message": f"  suggestion: {s}"})

        feedback = {k: v for k, v in result.items() if k.endswith("_feedback")}
        emit({"type": "apply_progress", "company": company, "title": title, "stage": "ats_score",
              "job_index": state["job_index"], "total": len(state["jobs"]),
              "iteration": state["ats_iteration"] + 1, "score": score})
        return {
            "ats_score": score,
            "ats_feedback": feedback,
            "ats_iteration": state["ats_iteration"] + 1,
            "ats_passed": (result["pass"] or score >= pass_threshold),
            "best_score": best_score,
            "no_improve": no_improve,
            "_sections_to_rewrite": result["sections_to_rewrite"],
            "_best_sections": best_sections,
        }

    def route_after_check_ats(state: ApplyState):
        stagnated = state["no_improve"] >= max_no_improve
        exhausted = state["ats_iteration"] >= max_iterations
        flagged = [s for s in state.get("_sections_to_rewrite", []) if s in WRITER_SECTIONS]
        if stop_event.is_set() or state["ats_passed"] or exhausted or stagnated or not flagged:
            return "save_output"
        return flagged

    def save_output(state: ApplyState) -> dict:
        job = state["current_job"]
        title, company = job.get("title", ""), job.get("company", "")

        # the right decision, made autonomously: save the highest-scoring HONEST
        # version, not simply the last draft (a final rebuild can score worse)
        sections_to_save = state["sections"]
        final_score = state["ats_score"]
        best = state.get("_best_sections") or {}
        if best.get("sections") and best.get("score", -1) > final_score:
            emit({"type": "log", "level": "INFO",
                  "message": f"  keeping best version (score {best['score']}) over final draft (score {final_score})"})
            sections_to_save = best["sections"]
            final_score = best["score"]
        full_latex = latex.reassemble(sections_to_save, section_order)

        resume_pdf = latex.build_output_path(output_dir, company, title, pcfg["resume_filename"], "pdf")
        compiled = latex.compile_latex_to_pdf(full_latex, resume_pdf)

        cover_pdf = latex.build_output_path(output_dir, company, title, pcfg["cover_letter_filename"], "pdf")
        cover_letter_tool.save_cover_letter_pdf(state["cover_letter"], cover_pdf)

        job_id = job.get("id")
        if job_id is not None:
            jobs_db.save_build_artifacts(
                job_id, full_latex, state["cover_letter"], final_score, str(resume_pdf), str(cover_pdf),
            )

        logging.info("Built resume for %s @ %s — ATS score %d (%s)", title, company, final_score,
                     "compiled" if compiled else "tex only")
        emit({"type": "apply_progress", "company": company, "title": title, "stage": "done",
              "job_index": state["job_index"], "total": len(state["jobs"]),
              "score": final_score, "status": "done" if compiled else "tex_only",
              "resume_path": str(resume_pdf), "cover_path": str(cover_pdf), "job_id": job_id})
        time.sleep(1)
        return {
            "job_index": state["job_index"] + 1,
            "results": [{"company": company, "title": title, "score": final_score,
                          "status": "done" if compiled else "tex_only"}],
        }

    # ---- graph -----------------------------------------------------------

    g = StateGraph(ApplyState)
    g.add_node("next_job", next_job)
    for section in WRITER_SECTIONS:
        g.add_node(section, make_writer_node(section))
    g.add_node("optimize", optimize)
    g.add_node("check_ats", check_ats)
    g.add_node("save_output", save_output)

    g.add_edge(START, "next_job")
    g.add_conditional_edges("next_job", route_after_next_job, [*WRITER_SECTIONS, END])
    for section in WRITER_SECTIONS:
        g.add_edge(section, "optimize")
    g.add_edge("optimize", "check_ats")
    g.add_conditional_edges("check_ats", route_after_check_ats, [*WRITER_SECTIONS, "save_output"])
    g.add_edge("save_output", "next_job")

    return g.compile()

def load_buildable_jobs(verdicts: tuple[str, ...] = ("yes",)) -> list[dict]:
    return JobsDB().get_buildable(verdicts)
