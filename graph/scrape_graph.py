import logging
import threading
import time
from typing import Callable

from langgraph.graph import END, START, StateGraph

from agents import screener
from agents.job_scraper import scrape_new_jobs
from config import CONFIG, collect_ollama_keys, load_text_file
from db.manager import AppliedDB, JobsDB
from graph.state import ScrapeState
from llm.client import RotatingOllamaClient


def build_scrape_graph(emit: Callable[[dict], None] | None = None,
                        stop_event: threading.Event | None = None):
    """`emit` is called with a small event dict at key points (used by the
    Electron GUI's live feed). `stop_event` lets a caller cancel a run
    between jobs. Both are no-ops for the plain CLI path."""
    emit = emit or (lambda event: None)
    stop_event = stop_event or threading.Event()
    jobs_db = JobsDB()
    applied_db = AppliedDB()
    client = RotatingOllamaClient(
        collect_ollama_keys(), CONFIG["model"]["scraping"],
        num_predict=CONFIG["model"]["num_predict"], num_ctx=CONFIG["model"]["num_ctx"],
        temperature=CONFIG["model"]["temperature"],
    )
    resume_text = load_text_file(CONFIG["pipeline"]["resume_path"])

    def job_scraper_node(state: ScrapeState) -> dict:
        emit({"type": "status", "stage": "scrape", "state": "scraping"})
        # scrape_new_jobs() emits its own "Starting scrape: ..." line (with the
        # actual per-(term,site) work count and concurrency cap) — a second,
        # slightly different one here duplicated it and read like two
        # conflicting counts for the same thing.
        jobs = scrape_new_jobs(CONFIG, jobs_db, applied_db, emit=emit)
        logging.info("Job Scraper Agent: %d new candidate jobs", len(jobs))
        emit({"type": "log", "level": "INFO", "message": f"Found {len(jobs)} new candidate jobs"})
        return {"jobs": jobs}

    def screener_node(state: ScrapeState) -> dict:
        emit({"type": "status", "stage": "scrape", "state": "screening"})
        total = len(state["jobs"])
        screened = []
        verdict_counts = {"yes": 0, "maybe": 0, "no": 0}
        for i, job in enumerate(state["jobs"], start=1):
            if stop_event.is_set():
                emit({"type": "log", "level": "WARNING", "message": "Stopped by user"})
                break
            if not job.get("job_url"):
                continue
            try:
                verdict = screener.screen_job(client, job, CONFIG, resume_text)
                row = screener.verdict_to_job_row(job, verdict)
                jobs_db.upsert(row)
            except Exception as e:
                logging.warning("Screener failed for %s @ %s: %s", job.get("title"), job.get("company"), e)
                emit({"type": "log", "level": "ERROR",
                      "message": f"Screener failed for {job.get('title')} @ {job.get('company')}: {e}"})
                continue
            screened.append(row)
            verdict_counts[verdict["verdict"]] = verdict_counts.get(verdict["verdict"], 0) + 1
            logging.info("[%s] %s @ %s (%s%%)", verdict["verdict"].upper(),
                         job.get("title"), job.get("company"), verdict.get("skills_match_pct"))
            emit({"type": "scrape_job", "verdict": verdict["verdict"], "company": job.get("company"),
                  "title": job.get("title"), "location": job.get("location"),
                  "skills_match_pct": verdict.get("skills_match_pct"),
                  "matched_skills": verdict.get("matched_skills", []),
                  "missing_skills": verdict.get("missing_skills", [])})
            if i % 10 == 0 or i == total:
                emit({"type": "log", "level": "INFO", "message": f"Screened {i}/{total} jobs…"})
            time.sleep(0.5)
        emit({"type": "log", "level": "INFO",
              "message": f"Screening complete — {verdict_counts['yes']} yes, "
                         f"{verdict_counts['maybe']} maybe, {verdict_counts['no']} no"})
        emit({"type": "done", "stage": "scrape"})
        return {"screened": screened}

    g = StateGraph(ScrapeState)
    g.add_node("job_scraper", job_scraper_node)
    g.add_node("screener", screener_node)
    g.add_edge(START, "job_scraper")
    g.add_edge("job_scraper", "screener")
    g.add_edge("screener", END)
    return g.compile()
