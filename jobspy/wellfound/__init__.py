# jobspy/wellfound/__init__.py
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from jobspy.util import create_logger, extract_emails_from_text

log = create_logger("Wellfound")

# ── Try to import jobspy model classes; fall back gracefully ──────────────────
try:
    from jobspy.model import (
        Compensation, CompensationInterval,
        JobPost, JobResponse, Location, Scraper, ScraperInput, Site,
    )
    _HAS_JOBSPY_MODEL = True
except ImportError:
    _HAS_JOBSPY_MODEL = False


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9\s-]", "", text.lower().strip())
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


# ── JavaScript helpers ────────────────────────────────────────────────────────

_EXTRACT_JOBS_JS = """
() => {
    const results = [];
    const seen    = new Set();
    const base    = 'https://wellfound.com';
    const JOB_RE  = /^\\/jobs\\/[^\\/\\?#]+\\/[^\\/\\?#]+$/;

    for (const link of document.querySelectorAll('a[href]')) {
        const rawHref = link.getAttribute('href') || '';
        if (!JOB_RE.test(rawHref)) continue;

        const url = base + rawHref;
        if (seen.has(url)) continue;
        seen.add(url);

        const title = (link.innerText || link.textContent || '').trim();
        if (!title) continue;

        // Walk up to nearest card-like ancestor
        let card = link.parentElement;
        for (let i = 0; i < 8; i++) {
            if (!card || card === document.body) break;
            const n = card.querySelectorAll('a[href]').length;
            if (n >= 2 && n <= 20) break;
            card = card.parentElement;
        }

        let company = '', companyUrl = '';
        if (card) {
            const cLink = card.querySelector(
                'a[href*="/company/"], a[href*="/startups/"], a[href*="/u/"]'
            );
            if (cLink) {
                company    = (cLink.innerText || '').trim();
                companyUrl = cLink.href || '';
            }
            if (!company) {
                for (const l of card.querySelectorAll('a')) {
                    const t = (l.innerText || '').trim();
                    if (t && t !== title) { company = t; companyUrl = l.href || ''; break; }
                }
            }
        }

        const getText = (selector) => {
            if (!card) return '';
            const el = card.querySelector(selector);
            return el ? el.innerText.trim() : '';
        };

        const location    = getText('[class*="location" i], [data-test*="location" i]');
        const salary      = getText('[class*="salary" i], [class*="compensation" i]');
        const timeEl      = card ? card.querySelector('time') : null;
        const postedAt    = timeEl
            ? (timeEl.getAttribute('datetime') || timeEl.innerText.trim())
            : '';

        // Extra: equity, job type
        const equity   = getText('[class*="equity" i]');
        const jobType  = getText('[class*="job-type" i], [class*="jobType" i]');

        results.push({ title, company, companyUrl, location, salary, equity, jobType, postedAt, url });
    }
    return results;
}
"""

_EXTRACT_DESC_JS = """
() => {
    // Wellfound job pages — try most specific selectors first
    const selectors = [
        '[data-test="job-description"]',
        '[data-test="JobDescription"]',
        '.prose',
        '[class*="jobDescription" i]',
        '[class*="description" i]',
        'article',
        'main section',
        'section',
        'main',
    ];
    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
            const text = (el.innerText || '').trim();
            if (text.length > 200) return text;
        }
    }
    return '';
}
"""

_PAGE_READY_JS = """
() => {
    const title = document.title.toLowerCase();
    if (!title || title.includes('just a moment') || title.includes('captcha') ||
        title.includes('checking') || title.includes('verify')) return false;
    for (const a of document.querySelectorAll('a[href]')) {
        if (/^\\/jobs\\/[^\\/]+\\/[^\\/]+$/.test(a.getAttribute('href') || '')) return true;
    }
    return false;
}
"""

_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    window.chrome = { runtime: {} };
"""


# ── Main scraper class ────────────────────────────────────────────────────────

class WellfoundScraper:
    """
    Standalone Wellfound scraper using Playwright persistent context.
    Works independently of jobspy's Site enum.

    Persistent context means the browser profile (cookies / login) is saved
    at ~/.jobspy_wellfound_profile — you only need to log in once.
    """

    base_url = "https://wellfound.com"

    def __init__(self):
        self.seen_urls: set[str] = set()
        self._profile_dir = str(Path.home() / ".jobspy_wellfound_profile")
        os.makedirs(self._profile_dir, exist_ok=True)

    # ── URL builder ───────────────────────────────────────────────────────────

    def _build_url(self, search_term: str, location: str, is_remote: bool) -> str:
        role_slug = _slugify(search_term) if search_term else ""
        loc_slug  = _slugify(location)   if location   else ""

        if is_remote:
            url = f"{self.base_url}/remote"
            if role_slug:
                url += f"?role[]={role_slug}"
            return url

        if role_slug and loc_slug:
            return f"{self.base_url}/role/r/{role_slug}?location[]={loc_slug}"

        if role_slug:
            return f"{self.base_url}/role/r/{role_slug}"

        if loc_slug:
            return f"{self.base_url}/location/{loc_slug}"

        return f"{self.base_url}/jobs"

    # ── Public entry point ────────────────────────────────────────────────────

    def scrape(
        self,
        search_term: str = "software engineer",
        location: str    = "",
        results_wanted: int = 20,
        hours_old: int   = 72,
        is_remote: bool  = False,
        fetch_descriptions: bool = True,
    ) -> list[dict]:
        """
        Returns a list of job dicts compatible with the jobs_scraper DataFrame schema:
          title, company, job_url, description, date_posted,
          location, compensation, is_remote, company_url, job_type
        """
        from playwright.sync_api import sync_playwright

        start_url = self._build_url(search_term, location, is_remote)
        log.info(f"Wellfound → {start_url}")

        _UA   = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        _ARGS = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
        ]

        jobs: list[dict] = []

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                self._profile_dir,
                headless=False,     # must be visible — Wellfound has CAPTCHA
                args=_ARGS,
                user_agent=_UA,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            context.add_init_script(_STEALTH_SCRIPT)
            page = context.new_page()

            try:
                # 1. Navigate to search URL
                page.goto(start_url, wait_until="domcontentloaded", timeout=45_000)

                # 2. Wait for CAPTCHA if present (user solves it manually)
                log.info("Wellfound: waiting for page ready (solve CAPTCHA if shown)...")
                try:
                    page.wait_for_function(
                        """() => {
                            const t = document.title.toLowerCase();
                            return t !== '' &&
                                   !t.includes('just a moment') &&
                                   !t.includes('captcha') &&
                                   !t.includes('checking') &&
                                   !t.includes('verify');
                        }""",
                        timeout=120_000,   # 2 minutes — enough to solve CAPTCHA
                    )
                except Exception:
                    log.warning("Wellfound: CAPTCHA wait timed out — proceeding anyway")

                page.wait_for_timeout(2_000)

                # 3. Wait for job cards
                try:
                    page.wait_for_function(_PAGE_READY_JS, timeout=20_000)
                except Exception:
                    log.warning("Wellfound: no jobs on primary URL — trying /jobs fallback")
                    page.goto(f"{self.base_url}/jobs", wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_timeout(2_000)
                    try:
                        page.wait_for_function(_PAGE_READY_JS, timeout=15_000)
                    except Exception:
                        log.warning("Wellfound: fallback page also has no jobs")

                page.wait_for_timeout(1_000)

                # 4. Collect job stubs by scrolling / load-more
                stubs:          list[dict] = []
                seen_stub_urls: set[str]   = set()
                stall_count = 0

                while len(stubs) < results_wanted and stall_count < 5:
                    raw = page.evaluate(_EXTRACT_JOBS_JS) or []
                    for r in raw:
                        u = r.get("url", "")
                        if u and u not in seen_stub_urls:
                            seen_stub_urls.add(u)
                            stubs.append(r)

                    log.info(f"Wellfound: {len(stubs)} stubs collected")
                    if len(stubs) >= results_wanted:
                        break

                    if self._click_load_more(page):
                        page.wait_for_timeout(2_500)
                        stall_count = 0
                        continue

                    # Scroll to load infinite-scroll content
                    prev_count = len(seen_stub_urls)
                    page.mouse.click(300, 450)
                    page.wait_for_timeout(200)
                    page.mouse.wheel(0, 2_500)
                    page.wait_for_timeout(2_000)

                    raw2      = page.evaluate(_EXTRACT_JOBS_JS) or []
                    new_count = sum(1 for r in raw2 if r.get("url") not in seen_stub_urls)
                    stall_count = 0 if new_count > 0 else stall_count + 1

                stubs = stubs[:results_wanted]
                log.info(f"Wellfound: {len(stubs)} stubs — fetching descriptions...")

                # 5. Fetch full descriptions per job page
                for idx, stub in enumerate(stubs):
                    job_url = stub.get("url", "").strip()
                    if not job_url or job_url in self.seen_urls:
                        continue
                    self.seen_urls.add(job_url)

                    description = ""
                    if fetch_descriptions:
                        description = self._fetch_description(context, job_url)

                    parsed = self._parse_stub(stub, description, hours_old)
                    if parsed:
                        jobs.append(parsed)
                        log.info(
                            f"  [{idx+1}/{len(stubs)}] "
                            f"{stub.get('title')} @ {stub.get('company')} "
                            f"({len(description)} chars)"
                        )

            except Exception as exc:
                log.error(f"Wellfound scrape error: {exc}")
                import traceback
                log.debug(traceback.format_exc())
            finally:
                context.close()

        log.info(f"Wellfound: collected {len(jobs)} jobs total")
        return jobs

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _click_load_more(self, page) -> bool:
        try:
            btn = page.query_selector(
                'button:has-text("Load more"), button:has-text("Show more"), '
                'button:has-text("More jobs"), [data-test="load-more"]'
            )
            if btn and btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click()
                return True
        except Exception:
            pass
        return False

    def _fetch_description(self, context, job_url: str) -> str:
        try:
            p = context.new_page()
            p.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
            p.wait_for_timeout(1_500)
            desc = p.evaluate(_EXTRACT_DESC_JS) or ""
            p.close()
            return desc.strip()
        except Exception as exc:
            log.debug(f"Wellfound: description fetch failed for {job_url}: {exc}")
            return ""

    # ── Parser ────────────────────────────────────────────────────────────────

    def _parse_stub(self, stub: dict, description: str, hours_old: int) -> dict | None:
        title   = (stub.get("title")   or "").strip()
        company = (stub.get("company") or "").strip()
        if not title:
            return None

        job_url      = (stub.get("url")        or "").strip()
        location_str = (stub.get("location")   or "").strip()
        salary_str   = (stub.get("salary")     or "").strip()
        posted_raw   = (stub.get("postedAt")   or "").strip()
        company_url  = (stub.get("companyUrl") or "").strip()
        job_type     = (stub.get("jobType")    or "").strip()

        # Date filter
        date_posted = self._parse_date(posted_raw)
        if hours_old and date_posted:
            cutoff = datetime.now().date() - timedelta(hours=hours_old / 24)
            if date_posted < cutoff:
                return None   # too old

        # Compensation
        compensation_str = self._parse_salary_string(salary_str)

        # Location
        is_remote = (
            "remote" in location_str.lower() or
            "remote" in description.lower()
        )

        return {
            "title":          title,
            "company":        company,
            "company_url":    company_url,
            "job_url":        job_url,
            "location":       location_str,
            "description":    description,
            "date_posted":    date_posted,
            "compensation":   compensation_str,
            "is_remote":      is_remote,
            "job_type":       job_type,
            "site":           "wellfound",
        }

    @staticmethod
    def _parse_date(posted_raw: str):
        if not posted_raw:
            return datetime.now().date()
        now = datetime.now()
        try:
            return datetime.fromisoformat(posted_raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        m = re.search(r"(\d+)\s*(hour|day|week|month)", posted_raw, re.IGNORECASE)
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            delta = {
                "hour":  timedelta(hours=n),
                "day":   timedelta(days=n),
                "week":  timedelta(weeks=n),
                "month": timedelta(days=n * 30),
            }.get(unit, timedelta(days=n))
            return (now - delta).date()
        return now.date()

    @staticmethod
    def _parse_salary_string(salary_str: str) -> str:
        if not salary_str:
            return ""
        cleaned = re.sub(r"[kK]", "000", salary_str)
        nums = [float(n.replace(",", "")) for n in re.findall(r"[\d,]+", cleaned)]
        if len(nums) >= 2:
            lo, hi = int(nums[0]), int(nums[1])
            return f"${lo:,} – ${hi:,}/yr"
        if len(nums) == 1:
            return f"${int(nums[0]):,}/yr"
        return salary_str


# ── jobspy model wrapper (optional — used only if jobspy is installed) ────────

if _HAS_JOBSPY_MODEL:
    class Wellfound(Scraper):
        """jobspy-compatible wrapper around WellfoundScraper."""

        base_url = "https://wellfound.com"

        def __init__(self, proxies=None, ca_cert=None, user_agent=None):
            try:
                super().__init__(Site.WELLFOUND, proxies=proxies, ca_cert=ca_cert)
            except Exception:
                pass
            self._impl = WellfoundScraper()
            self.scraper_input = None

        def scrape(self, scraper_input: ScraperInput) -> JobResponse:
            self.scraper_input = scraper_input
            raw = self._impl.scrape(
                search_term       = scraper_input.search_term or "",
                location          = scraper_input.location    or "",
                results_wanted    = scraper_input.results_wanted,
                hours_old         = scraper_input.hours_old or 72,
                is_remote         = scraper_input.is_remote,
                fetch_descriptions= scraper_input.linkedin_fetch_description,
            )
            jobs = [self._to_jobpost(r) for r in raw if r]
            return JobResponse(jobs=jobs)

        @staticmethod
        def _to_jobpost(r: dict) -> JobPost:
            loc_str = r.get("location", "")
            parts   = [p.strip() for p in re.split(r"[,·]", loc_str) if p.strip()]
            return JobPost(
                id          = f"wf-{abs(hash(r.get('job_url','') + r.get('title',''))) % 10**8:08d}",
                title       = r.get("title", ""),
                company_name= r.get("company"),
                job_url     = r.get("job_url", ""),
                company_url = r.get("company_url"),
                location    = Location(
                    city    = parts[0] if parts else None,
                    state   = parts[1] if len(parts) > 1 else None,
                    country = parts[2] if len(parts) > 2 else None,
                ),
                description = r.get("description"),
                date_posted = r.get("date_posted"),
                is_remote   = r.get("is_remote", False),
                emails      = extract_emails_from_text(r.get("description") or ""),
            )