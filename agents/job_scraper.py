"""Job Scraper Agent — jobspy multi-site scrape + dedup.

No LLM involved; "agent" here means "the graph node responsible for this
stage," matching the other five. Port of jobs_scraper.py + app.py's
ScraperTab dedup pipeline (URL-seen-set -> blacklist -> already-applied ->
fuzzy cross-site dedup).
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from difflib import SequenceMatcher

from jobspy import scrape_jobs

from db.manager import AppliedDB, JobsDB

EXPECTED_COLS = [
    "title", "company", "job_url", "location", "description",
    "date_posted", "site",
]

# Each jobspy site module already logs per-page/per-request progress
# (ZipRecruiter's "search page 2/5", JobRight's "fetching position 40", "N
# cards found", etc.) via logging.getLogger(f"JobSpy:{name}") — but every one
# of those loggers is created with propagate=False (jobspy/util.py), so none
# of it reaches anything outside its own console handler. Bridging it into
# `emit` surfaces that detail on the Logs page instead of leaving the UI
# blind between our own coarser per-term/per-filter messages.
_JOBSPY_LOGGER_NAMES = [
    "Indeed", "LinkedIn", "ZipRecruiter", "Glassdoor", "Google",
    "Bayt", "Naukri", "BDJobs", "JobRight", "Wellfound",
]


class _EmitLogHandler(logging.Handler):
    def __init__(self, emit):
        super().__init__(level=logging.INFO)
        self._emit = emit

    def emit(self, record):
        try:
            level = record.levelname if record.levelname in ("WARNING", "ERROR") else "INFO"
            site = record.name.removeprefix("JobSpy:")
            self._emit({"type": "log", "level": level, "message": f"[{site}] {record.getMessage()}"})
        except Exception:
            pass  # a logging hook must never be the thing that breaks a scrape


def _install_log_bridge(emit) -> tuple[logging.Handler, list[logging.Logger]]:
    handler = _EmitLogHandler(emit)
    loggers = [logging.getLogger(f"JobSpy:{name}") for name in _JOBSPY_LOGGER_NAMES]
    for lg in loggers:
        lg.addHandler(handler)
    return handler, loggers


def _remove_log_bridge(handler: logging.Handler, loggers: list[logging.Logger]):
    for lg in loggers:
        lg.removeHandler(handler)

# Several sites scrape via a real Playwright browser to dodge anti-bot checks
# (ZipRecruiter, Glassdoor, JobRight, Google, Naukri, Wellfound). Their JS runs
# through page.evaluate(), which — unlike goto()/wait_for_*() — has no timeout
# of its own: one stalled fetch() in the page can block that call forever with
# no exception raised for anything here to catch. A hard per-(term, site) wall
# clock cap keeps one bad site from freezing the whole scrape indefinitely;
# the orphaned thread (Python can't force-kill a thread) just finishes on its
# own later and is discarded. Generous on purpose — this bounds infinite
# hangs, not normal slowness (ZipRecruiter alone fetches full descriptions one
# job at a time via a real browser, no parallelism inside a single site).
_SITE_TIMEOUT_SECONDS = 1800

# scrape_jobs() runs every site it's given CONCURRENTLY with no cap of its
# own (jobspy/__init__.py) — with sites=[a,b,...,j] that means every browser
# (up to 6 of them: ZipRecruiter/Glassdoor/JobRight/Google/Naukri/Wellfound)
# launches at once. That's enough memory pressure to crash one mid-navigation
# and, in the worst case, take the whole backend process down with it
# (reproduced directly: Wellfound's page crashed under exactly this load).
# Below, every (search term, site) pair is scraped individually and fed
# through one shared pool capped at this width — sites AND terms now run in
# parallel (previously: term 2 couldn't start until term 1's entire multi-site
# batch finished), but never more than this many real scrapers — several of
# them real browsers — at once.
_GLOBAL_MAX_CONCURRENT_SCRAPES = 3

# google and wellfound each launch Chromium against a single FIXED, shared
# on-disk profile directory (Path.home() / ".jobspy_google_profile", and
# wellfound's own equivalent) so cookies/solved CAPTCHAs survive across runs.
# Chromium refuses to open a second instance against a profile another
# instance already has open — reproduced directly: running two search terms'
# worth of Wellfound scraping concurrently (only possible now that terms run
# in parallel) failed the second one outright with "profile is already in use
# by another instance of Chromium." Serializing just these two sites avoids
# it without giving up parallelism for anything else.
_SITE_LOCKS: dict[str, threading.Lock] = {
    "google": threading.Lock(),
    "wellfound": threading.Lock(),
}


def _scrape_one(term: str, site: str, **kwargs):
    lock = _SITE_LOCKS.get(site)
    if lock:
        lock.acquire()
    try:
        # Not a context manager on purpose: ThreadPoolExecutor.__exit__ calls
        # shutdown(wait=True), which would block right here until the hung
        # call finishes on its own — exactly what this timeout exists to
        # avoid. The pool (and its one stuck worker, if it never returns) is
        # simply dropped; Python can't force-kill a thread, so it lingers
        # until it exits by itself.
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(scrape_jobs, site_name=[site], search_term=term, **kwargs)
        try:
            return future.result(timeout=_SITE_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            logging.warning("Scrape of %s for %r exceeded %ds — abandoning it", site, term, _SITE_TIMEOUT_SECONDS)
            return None
        finally:
            pool.shutdown(wait=False)
    finally:
        if lock:
            lock.release()


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


def scrape_new_jobs(cfg: dict, jobs_db: JobsDB, applied_db: AppliedDB, emit=None) -> list[dict]:
    emit = emit or (lambda event: None)
    scraper_cfg = cfg["scraper"]
    screener_cfg = cfg["screener"]
    sites = [s.strip() for s in scraper_cfg["sites"].split(",") if s.strip()]
    search_terms = [t.strip() for t in scraper_cfg["search_terms"].splitlines() if t.strip()]

    # jobspy's Country.from_string("") raises ValueError, which aborts the
    # WHOLE multi-site call below (not just indeed) — so a blank country
    # here silently zeroed every site's results, not just indeed's. Omit the
    # kwarg entirely when blank so jobspy falls back to its own default.
    scrape_kwargs = {}
    if scraper_cfg.get("country_indeed"):
        scrape_kwargs["country_indeed"] = scraper_cfg["country_indeed"]
    if scraper_cfg.get("greenhouse_cookie"):
        scrape_kwargs["greenhouse_cookie"] = scraper_cfg["greenhouse_cookie"]

    work_items = [(term, site) for term in search_terms for site in sites]
    emit({"type": "log", "level": "INFO",
          "message": f"Starting scrape: {len(sites)} site(s) × {len(search_terms)} term(s) = "
                     f"{len(work_items)} scrape(s), up to {_GLOBAL_MAX_CONCURRENT_SCRAPES} at a time"})

    seen_urls: set[str] = set()
    all_rows: list[dict] = []
    log_handler, log_loggers = _install_log_bridge(emit)
    # Every submitted task is individually timeout-guarded by _scrape_one
    # (see its docstring comment) — none of them can hang, so this pool
    # always finishes in bounded time and is safe to use as a context
    # manager (no risk of __exit__'s shutdown(wait=True) blocking forever).
    try:
        with ThreadPoolExecutor(max_workers=_GLOBAL_MAX_CONCURRENT_SCRAPES) as pool:
            future_to_item = {
                pool.submit(
                    _scrape_one, term, site,
                    location=scraper_cfg["location"],
                    hours_old=scraper_cfg["hours_old"],
                    results_wanted=scraper_cfg["results_wanted"],
                    is_remote=scraper_cfg["is_remote"],
                    linkedin_fetch_description=True,
                    **scrape_kwargs,
                ): (term, site)
                for term, site in work_items
            }
            for future in as_completed(future_to_item):
                term, site = future_to_item[future]
                try:
                    df = future.result()
                except Exception as e:
                    logging.warning("Scrape of %s for %r failed: %s", site, term, e)
                    emit({"type": "log", "level": "ERROR", "message": f"[{site}] {term!r}: {e}"})
                    continue
                if df is None:
                    emit({"type": "log", "level": "ERROR",
                          "message": f"[{site}] {term!r}: timed out after {_SITE_TIMEOUT_SECONDS}s — skipped"})
                    continue
                if df.empty:
                    emit({"type": "log", "level": "INFO", "message": f"[{site}] {term!r}: 0 raw results"})
                    continue
                for col in EXPECTED_COLS:
                    if col not in df.columns:
                        df[col] = ""
                df = df[~df["job_url"].astype(str).isin(seen_urls)]
                seen_urls.update(df["job_url"].astype(str).tolist())
                rows = df[EXPECTED_COLS].fillna("").to_dict("records")
                all_rows.extend(rows)
                emit({"type": "log", "level": "INFO", "message": f"[{site}] {term!r}: {len(rows)} raw results"})
    finally:
        _remove_log_bridge(log_handler, log_loggers)

    if not all_rows:
        emit({"type": "log", "level": "INFO", "message": "No raw results from any site/term"})
        return []

    # Each filter step below silently drops rows — log before/after so "found
    # 200 but 0 candidates" is diagnosable from the Logs page instead of a
    # guessing game, matching the granular progress the screener stage already
    # emits per-job.
    def _log_filter(label: str, before: int, after: int):
        if before != after:
            emit({"type": "log", "level": "INFO", "message": f"{label}: {before} -> {after} (-{before - after})"})

    before = len(all_rows)
    # Skip URLs already known to jobs.db (already screened, pending/approved/skipped)
    known_urls = jobs_db.get_all_urls()
    all_rows = [r for r in all_rows if str(r["job_url"]) not in known_urls]
    _log_filter("Already in jobs.db", before, len(all_rows))

    # Blacklisted companies
    before = len(all_rows)
    blacklist = [c.lower() for c in screener_cfg.get("blacklisted_companies", [])]
    all_rows = [
        r for r in all_rows
        if not any(b in str(r.get("company", "")).lower() for b in blacklist)
    ]
    _log_filter("Blacklisted companies", before, len(all_rows))

    # Already applied (by URL or by company+title)
    if screener_cfg.get("skip_applied", True):
        before = len(all_rows)
        applied_urls = applied_db.get_urls()
        applied_pairs = applied_db.get_applied_pairs()
        all_rows = [
            r for r in all_rows
            if str(r["job_url"]) not in applied_urls
            and (str(r.get("company", "")).lower(), str(r.get("title", "")).lower()) not in applied_pairs
        ]
        _log_filter("Already applied", before, len(all_rows))

    if screener_cfg.get("fuzzy_dedup", True):
        before = len(all_rows)
        all_rows = _fuzzy_dedup(all_rows)
        _log_filter("Fuzzy duplicates", before, len(all_rows))

    return all_rows
