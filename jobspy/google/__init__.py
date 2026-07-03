from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta

from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    Location,
    JobType,
)
from jobspy.util import extract_emails_from_text, extract_job_type
from jobspy.google.util import log

# JavaScript run inside Playwright to extract job card metadata (no clicking needed).
#
# Selectors confirmed from live Google Jobs HTML (June 2025):
#   Card container : [data-preview-id]
#   Title          : .tNxQIb.PUpOsf
#   Company        : .wHYlTd.MKCbgd.a3jPc
#   Location+source: .wHYlTd.FqK3wc.MKCbgd
#   Date           : span.Yf9oye > span[aria-hidden]
#
# Descriptions require clicking each card. Google uses a horizontal carousel
# in the right panel: active description is always at the column with the
# smallest left > viewport_width/2. _GET_ACTIVE_DESC_JS extracts it.
_EXTRACT_JS = """
() => {
    const results = [];
    const seen    = new Set();
    const baseUrl = 'https://www.google.com/search';
    const cards   = Array.from(document.querySelectorAll('[data-preview-id]'));

    for (const card of cards) {
        const previewId = card.getAttribute('data-preview-id') || '';

        const titleEl  = card.querySelector('.tNxQIb.PUpOsf');
        const compEl   = card.querySelector('.wHYlTd.MKCbgd.a3jPc');
        const locEl    = card.querySelector('.wHYlTd.FqK3wc.MKCbgd');
        const dateEl   = card.querySelector('span.Yf9oye span[aria-hidden]');
        const salaryEl = card.querySelector('.I2Cbhb');

        const title   = titleEl  ? titleEl.innerText.trim()  : null;
        const company = compEl   ? compEl.innerText.trim()   : null;
        const locRaw  = locEl    ? locEl.innerText.trim()    : '';
        const date    = dateEl   ? dateEl.innerText.trim()   : null;
        const salary  = salaryEl ? salaryEl.innerText.trim() : null;

        if (!title || !company) continue;
        const key = title + '|' + company;
        if (seen.has(key)) continue;
        seen.add(key);

        let location = locRaw, source = '';
        const viaIdx = locRaw.indexOf(' via ');
        if (viaIdx > -1) {
            location = locRaw.substring(0, viaIdx).trim();
            source   = locRaw.substring(viaIdx + 5).trim();
        }
        location = location.replace(/[•∙·]/g, '').trim();

        const jobUrl = previewId
            ? baseUrl + '?q=' + encodeURIComponent(title + ' ' + company) + '&udm=8&jid=' + previewId
            : baseUrl + '?q=' + encodeURIComponent(title + ' ' + company + ' jobs') + '&udm=8';

        results.push({ title, company, location, source, date, salary, url: jobUrl, previewId });
    }
    return results;
}
"""

# After clicking a job card, Google slides the description into the right panel as a
# horizontal carousel. The active description sits at the column with the smallest
# left > viewport_width/2.
#
# Returns { text, applyUrl } where applyUrl is the actual hiring-site URL extracted
# from the topmost external link in the right panel (the "Apply on [X]" button).
_GET_ACTIVE_DESC_JS = """
() => {
    const halfVW = window.innerWidth / 2;

    // --- Apply URL: topmost external link in the right-panel column ---
    function unwrapGoogleRedirect(href) {
        if (href && href.includes('google.com/url')) {
            const m = href.match(/[?&]q=([^&]+)/);
            if (m) return decodeURIComponent(m[1]);
        }
        return href;
    }

    const rightLinks = Array.from(document.querySelectorAll('a[href]'))
        .filter(a => {
            const r = a.getBoundingClientRect();
            return r.left >= halfVW && r.width > 10 && r.height > 0;
        })
        .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);

    let applyUrl = '';
    for (const a of rightLinks) {
        let href = unwrapGoogleRedirect(a.getAttribute('href') || a.href || '');
        if (href.startsWith('http') && !href.includes('google.com')) {
            applyUrl = href;
            break;
        }
    }

    // --- Description: active .XFOJCe block in the right half ---
    const allX   = Array.from(document.querySelectorAll('.XFOJCe'));
    const inPanel = allX.filter(x => {
        const r = x.getBoundingClientRect();
        return r.left >= halfVW && r.width > 50;
    });
    inPanel.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);

    let text = '';
    for (const x of inPanel) {
        const h2 = x.querySelector('h2');
        const heading = (h2 ? h2.innerText : '').toLowerCase().trim();
        if (heading === 'report this listing' || heading.startsWith('report')) continue;

        const vis = x.querySelector('[jsname="QAWWu"]');
        const hid = x.querySelector('[jsname="ij8cu"]');
        const t = ((vis ? vis.innerText : '') + ' ' + (hid ? hid.textContent : '')).trim();
        if (t.length > 30) { text = t; break; }
    }

    return { text, applyUrl };
}
"""


class Google(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        site = Site(Site.GOOGLE)
        super().__init__(site, proxies=proxies, ca_cert=ca_cert)

        self.country = None
        self.session = None
        self.scraper_input = None
        self.jobs_per_page = 10
        self.seen_urls: set[str] = set()
        self.url = "https://www.google.com/search"
        self.jobs_url = "https://www.google.com/async/callback:550"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        import os
        from pathlib import Path
        from playwright.sync_api import sync_playwright

        self.scraper_input = scraper_input
        results_wanted = min(100, scraper_input.results_wanted)

        search_url = self._build_url()
        log.info(f"Google: navigating to {search_url}")

        # Persistent profile so cookies / solved CAPTCHAs survive across runs
        profile_dir = str(Path.home() / ".jobspy_google_profile")
        os.makedirs(profile_dir, exist_ok=True)

        _LAUNCH_ARGS = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
        ]
        _UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )

        jobs: list[JobPost] = []
        processed_ids: set[str] = set()
        panel_ready = False

        with sync_playwright() as p:
            # launch_persistent_context keeps cookies / localStorage between runs
            context = p.chromium.launch_persistent_context(
                profile_dir,
                headless=False,
                args=_LAUNCH_ARGS,
                user_agent=_UA,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="America/Toronto",
            )
            # Hide the automation flag that Google detects
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = context.new_page()
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=45_000)

                # If Google shows a CAPTCHA the user can solve it manually (headless=False).
                # Wait up to 90 s for the page title to stop being a challenge page.
                try:
                    page.wait_for_function(
                        """document.title &&
                           !document.title.toLowerCase().includes('captcha') &&
                           !document.title.toLowerCase().includes('unusual traffic') &&
                           document.title !== 'Just a moment...'""",
                        timeout=90_000,
                    )
                except Exception:
                    log.warning("Google: CAPTCHA / challenge may still be present — proceeding anyway")

                page.wait_for_timeout(2_500)

                # Google uses infinite scroll: cards load lazily as the user scrolls.
                # We scroll to the bottom repeatedly until we have enough jobs.
                while len(jobs) < results_wanted:
                    log.info(f"Google: extracting (have {len(jobs)}/{results_wanted}, seen {len(processed_ids)} cards)")
                    new_jobs, panel_ready = self._extract_from_dom(page, processed_ids, panel_ready)
                    before = len(jobs)
                    for j in new_jobs:
                        if j.job_url not in self.seen_urls:
                            self.seen_urls.add(j.job_url)
                            jobs.append(j)
                    log.info(f"Google: +{len(jobs) - before} new jobs this pass")

                    if len(jobs) >= results_wanted:
                        break

                    if not self._scroll_for_more(page, len(processed_ids)):
                        log.info("Google: no additional cards after scrolling — stopping")
                        break

            except Exception as exc:
                log.error(f"Google scrape error: {exc}")
            finally:
                context.close()

        log.info(f"Google: collected {len(jobs)} jobs")
        offset = scraper_input.offset
        return JobResponse(jobs=jobs[offset: offset + results_wanted])

    # ------------------------------------------------------------------
    # DOM extraction (click each card for its description)
    # ------------------------------------------------------------------

    def _extract_from_dom(
        self, page, processed_ids: set, panel_ready: bool
    ) -> tuple[list[JobPost], bool]:
        try:
            raw_list = page.evaluate(_EXTRACT_JS) or []
        except Exception as exc:
            log.warning(f"DOM JS evaluate error: {exc}")
            return [], panel_ready

        now = datetime.now()
        jobs = []

        for i, rd in enumerate(raw_list):
            preview_id = rd.get("previewId", "")

            # Skip cards we already processed in a previous scroll batch
            if preview_id and preview_id in processed_ids:
                continue
            if preview_id:
                processed_ids.add(preview_id)

            description = ""
            if preview_id:
                try:
                    card = page.query_selector(f'[data-preview-id="{preview_id}"]')
                    if card:
                        card.click()
                        if not panel_ready:
                            # First ever click: wait for the carousel panel to appear
                            page.wait_for_selector(".XFOJCe", timeout=8_000)
                            page.wait_for_timeout(800)
                            panel_ready = True
                        else:
                            # Carousel slides in ~300 ms; 900 ms gives comfortable margin
                            page.wait_for_timeout(900)
                        result = page.evaluate(_GET_ACTIVE_DESC_JS) or {}
                        description = result.get("text", "") if isinstance(result, dict) else str(result)
                        apply_url   = result.get("applyUrl", "") if isinstance(result, dict) else ""
                        if apply_url:
                            rd["url"] = apply_url  # replace Google search URL with real job URL
                except Exception as exc:
                    log.debug(f"Description click error for card {i}: {exc}")

            rd["description"] = description
            try:
                job = self._parse_dom_job(rd, now)
                if job:
                    jobs.append(job)
            except Exception as exc:
                log.debug(f"DOM job parse error: {exc}")

        return jobs, panel_ready

    # ------------------------------------------------------------------
    # Infinite-scroll pagination
    # ------------------------------------------------------------------

    def _scroll_for_more(self, page, current_count: int) -> bool:
        """Scroll the job list to trigger Google's lazy card loading.
        Uses mouse.wheel (most human-like) in the left panel area.
        Returns True if new [data-preview-id] cards appeared, False otherwise."""
        try:
            # Click the left panel (job list side) so the wheel targets it
            page.mouse.click(300, 450)
            page.wait_for_timeout(200)

            # Scroll down in increments; try up to 3 times before giving up
            for _ in range(3):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(300)
                try:
                    page.wait_for_function(
                        f"document.querySelectorAll('[data-preview-id]').length > {current_count}",
                        timeout=4_000,
                    )
                    page.wait_for_timeout(500)
                    return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Job parsers
    # ------------------------------------------------------------------

    def _parse_dom_job(self, rd: dict, now: datetime) -> JobPost | None:
        title        = (rd.get("title")    or "").strip()
        company_name = (rd.get("company")  or "").strip()
        if not title or not company_name:
            return None

        location_str = (rd.get("location")    or "").strip()
        date_str     = (rd.get("date")        or "").strip()
        url          = (rd.get("url")         or "").strip()
        description  = (rd.get("description") or "").strip()
        salary_str   = (rd.get("salary")      or "").strip()

        city = state = country = None
        if location_str:
            parts = [p.strip() for p in re.split(r"[,·•]", location_str)]
            city    = parts[0] if parts else None
            state   = parts[1] if len(parts) > 1 else None
            country = parts[2] if len(parts) > 2 else None

        date_posted = None
        if date_str:
            m = re.search(r"(\d+)\s*(hour|day|week|month)", date_str, re.IGNORECASE)
            if m:
                n, unit = int(m.group(1)), m.group(2).lower()
                deltas = {
                    "hour":  timedelta(hours=n),
                    "day":   timedelta(days=n),
                    "week":  timedelta(weeks=n),
                    "month": timedelta(days=n * 30),
                }
                date_posted = (now - deltas[unit]).date()
            elif re.search(r"just.?posted|today", date_str, re.IGNORECASE):
                date_posted = now.date()

        if date_posted and self.scraper_input and self.scraper_input.hours_old:
            cutoff = (now - timedelta(hours=self.scraper_input.hours_old)).date()
            if date_posted < cutoff:
                return None

        job_id = f"go-{abs(hash(url + title)) % 10 ** 8:08d}"

        return JobPost(
            id=job_id,
            title=title,
            company_name=company_name,
            location=Location(city=city, state=state, country=country),
            job_url=url or self.url,
            date_posted=date_posted,
            is_remote="remote" in (description + location_str).lower(),
            description=description,
            emails=extract_emails_from_text(description),
            job_type=extract_job_type(description),
        )

    # ------------------------------------------------------------------
    # URL builder
    # ------------------------------------------------------------------

    def _build_url(self) -> str:
        si = self.scraper_input

        if si.google_search_term:
            query = si.google_search_term
        else:
            parts = [si.search_term]
            if si.location:
                parts.append(si.location)
            if si.is_remote:
                parts.append("remote")
            job_type_labels = {
                JobType.FULL_TIME:   "full time",
                JobType.PART_TIME:   "part time",
                JobType.INTERNSHIP:  "internship",
                JobType.CONTRACT:    "contract",
            }
            if si.job_type in job_type_labels:
                parts.append(job_type_labels[si.job_type])
            query = " ".join(parts) + " jobs"

        params: dict = {"q": query, "udm": "8", "hl": "en", "gl": "us"}

        if si.hours_old:
            days = max(1, si.hours_old // 24)
            if days == 1:
                params["tbs"] = "qdr:d"
            elif days <= 7:
                params["tbs"] = f"qdr:d{days}"
            elif days <= 30:
                params["tbs"] = "qdr:w"
            else:
                params["tbs"] = "qdr:m"

        return self.url + "?" + urllib.parse.urlencode(params)
