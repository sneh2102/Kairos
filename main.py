"""CLI entry point (the Electron app in desktop/ talks to server.py instead —
this is the headless/standalone path, kept for scripting).

  python main.py scrape   — Job Scraper Agent + Screener Agent, writes jobs.db
  python main.py review   — browse yes/maybe jobs, flip a verdict if you disagree
  python main.py apply    — Skills/Experience/Project Writers + ATS Checker for
                             every "yes" job without a resume yet, then marks
                             each one applied (writes outputs/ + applied.db)
"""
import argparse
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def cmd_scrape(_args):
    from graph.scrape_graph import build_scrape_graph

    graph = build_scrape_graph()
    final = graph.invoke({"jobs": [], "screened": []})
    yes = sum(1 for r in final["screened"] if r["ai_recommendation"] == "yes")
    maybe = sum(1 for r in final["screened"] if r["ai_recommendation"] == "maybe")
    print(f"Screened {len(final['screened'])} jobs — {yes} yes, {maybe} maybe. Run `python main.py apply` next.")


def cmd_review(_args):
    from db.manager import JobsDB

    jobs_db = JobsDB()
    jobs = jobs_db.search(verdict="")
    jobs = [j for j in jobs if j["ai_recommendation"].lower() in ("yes", "maybe")]
    if not jobs:
        print("No yes/maybe jobs to review. Run `python main.py scrape` first.")
        return

    for job in jobs:
        print("\n" + "-" * 70)
        print(f"{job['title']} @ {job['company']}  [{job['ai_recommendation'].upper()}, "
              f"{job['skills_match_pct']}% match, {job['role_level']}]")
        print(f"  {job['link']}")
        print(f"  {job['reasoning']}")
        choice = input("  [y]es / [m]aybe / [n]o / [enter]=leave / [q]uit: ").strip().lower()
        if choice == "q":
            break
        if choice in ("y", "m", "n"):
            verdict = {"y": "yes", "m": "maybe", "n": "no"}[choice]
            jobs_db.set_verdict(job["id"], verdict)
            print(f"  -> {verdict}")


def cmd_apply(_args):
    from db.manager import AppliedDB, JobsDB, mark_applied
    from graph.apply_graph import build_apply_graph, load_buildable_jobs

    jobs = load_buildable_jobs(verdicts=("yes",))
    if not jobs:
        print("No unbuild 'yes' jobs. Run `python main.py scrape` (and review) first.")
        return

    graph = build_apply_graph()
    initial_state = {
        "jobs": jobs, "job_index": 0, "current_job": {}, "cover_letter": "",
        "sections": {}, "ats_score": 0, "ats_feedback": {}, "ats_iteration": 0,
        "ats_passed": False, "best_score": 0, "no_improve": 0,
        "_sections_to_rewrite": [], "results": [],
    }
    final = graph.invoke(initial_state, {"recursion_limit": 200})
    print(f"Built {len(final['results'])} resumes.")

    jobs_db, applied_db = JobsDB(), AppliedDB()
    today = date.today().isoformat()
    for job, result in zip(jobs, final["results"]):
        mark_applied(jobs_db, applied_db, job["id"], today)
        print(f"  [{result['score']}] {result['title']} @ {result['company']} ({result['status']}) -> applied")


def main():
    parser = argparse.ArgumentParser(description="Job scraper — LangGraph multi-agent pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scrape", help="Scrape + AI-screen new jobs into jobs.db").set_defaults(func=cmd_scrape)
    sub.add_parser("review", help="Browse yes/maybe jobs, flip verdicts").set_defaults(func=cmd_review)
    sub.add_parser("apply", help="Build + apply for every unbuilt 'yes' job").set_defaults(func=cmd_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
