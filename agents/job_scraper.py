"""Job Scraper Agent — jobspy multi-site scrape + dedup.

No LLM involved; "agent" here means "the graph node responsible for this
stage," matching the other five. Port of jobs_scraper.py + app.py's
ScraperTab dedup pipeline (URL-seen-set -> blacklist -> already-applied ->
fuzzy cross-site dedup).
"""
import logging
from difflib import SequenceMatcher

from jobspy import scrape_jobs

from db.manager import AppliedDB, JobsDB

EXPECTED_COLS = [
    "title", "company", "job_url", "location", "description",
    "date_posted", "site",
]


def _fuzzy_dedup(rows: list[dict], threshold: float = 0.90) -> list[dict]:
    seen: list[tuple[str, str]] = []
    keep = []
    for row in rows:
        t = str(row.get("title", "")).lower().strip()
        c = str(row.get("company", "")).lower().strip()
        is_dup = any(
            SequenceMatcher(None, t, st).ratio() >= threshold
            and SequenceMatcher(None, c, sc).ratio() >= threshold
            for st, sc in seen
        )
        if not is_dup:
            seen.append((t, c))
            keep.append(row)
    return keep


def scrape_new_jobs(cfg: dict, jobs_db: JobsDB, applied_db: AppliedDB) -> list[dict]:
    scraper_cfg = cfg["scraper"]
    screener_cfg = cfg["screener"]
    sites = [s.strip() for s in scraper_cfg["sites"].split(",") if s.strip()]
    search_terms = [t.strip() for t in scraper_cfg["search_terms"].splitlines() if t.strip()]

    seen_urls: set[str] = set()
    all_rows: list[dict] = []
    for term in search_terms:
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=term,
                location=scraper_cfg["location"],
                hours_old=scraper_cfg["hours_old"],
                results_wanted=scraper_cfg["results_wanted"],
                country_indeed=scraper_cfg["country_indeed"],
                is_remote=scraper_cfg["is_remote"],
                linkedin_fetch_description=True,
            )
        except Exception as e:
            logging.warning("Scrape failed for term %r: %s", term, e)
            continue
        if df is None or df.empty:
            continue
        for col in EXPECTED_COLS:
            if col not in df.columns:
                df[col] = ""
        df = df[~df["job_url"].astype(str).isin(seen_urls)]
        seen_urls.update(df["job_url"].astype(str).tolist())
        all_rows.extend(df[EXPECTED_COLS].fillna("").to_dict("records"))

    if not all_rows:
        return []

    # Skip URLs already known to jobs.db (already screened, pending/approved/skipped)
    known_urls = jobs_db.get_all_urls()
    all_rows = [r for r in all_rows if str(r["job_url"]) not in known_urls]

    # Blacklisted companies
    blacklist = [c.lower() for c in screener_cfg.get("blacklisted_companies", [])]
    all_rows = [
        r for r in all_rows
        if not any(b in str(r.get("company", "")).lower() for b in blacklist)
    ]

    # Already applied (by URL or by company+title)
    if screener_cfg.get("skip_applied", True):
        applied_urls = applied_db.get_urls()
        applied_pairs = applied_db.get_applied_pairs()
        all_rows = [
            r for r in all_rows
            if str(r["job_url"]) not in applied_urls
            and (str(r.get("company", "")).lower(), str(r.get("title", "")).lower()) not in applied_pairs
        ]

    if screener_cfg.get("fuzzy_dedup", True):
        all_rows = _fuzzy_dedup(all_rows)

    return all_rows
