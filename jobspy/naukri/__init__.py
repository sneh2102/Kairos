from __future__ import annotations

import json as _json
import math
import random
import time
from datetime import datetime, date, timedelta
from typing import Optional
from jobspy.naukri.cookie_fetcher import get_naukri_headers
import regex as re
from bs4 import BeautifulSoup
from jobspy.naukri.constant import headers as naukri_headers
from jobspy.naukri.util import is_job_remote, parse_job_type, parse_company_industry
from jobspy.model import (
    JobPost, Location, JobResponse, Country,
    Compensation, DescriptionFormat, Scraper, ScraperInput, Site,
)
from jobspy.util import (
    extract_emails_from_text,
    markdown_converter, create_session, create_logger,
)

log = create_logger("Naukri")

_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    window.chrome = { runtime: {} };
"""

_DESC_SELECTORS = [
    '[class*="job-desc-container"]',
    '[class*="jdc_content"]',
    '[class*="dang-inner-html"]',
    '[class*="jd-desc"]',
    '[class*="job-desc"]',
    'section[class*="desc"]',
]


class Naukri(Scraper):
    base_url      = "https://www.naukri.com/jobapi/v3/search"
    delay         = 2
    band_delay    = 3
    jobs_per_page = 20

    # ── Set to False to hide the browser window during description fetching.
    #    Naukri detects headless mode and blocks pages, so visible is required.
    HEADLESS_DETAIL = False

    def __init__(self, proxies=None, ca_cert=None, user_agent=None):
        super().__init__(Site.NAUKRI, proxies=proxies, ca_cert=ca_cert)
        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert,
            is_tls=False, has_retry=True, delay=5, clear_cookies=False,
        )
        self._desc_cache: dict[str, str] = {}
        self._browser_cookies: list[dict] = []
        self._pw_context = None
        self._pw_page    = None      # single reused tab
        self._pw_instance = None

        try:
            log.info("Capturing Naukri session via browser...")
            result = get_naukri_headers()

            if isinstance(result, dict):
                headers, cookies, cached = result, {}, {}
            elif isinstance(result, (tuple, list)):
                if len(result) >= 4:
                    headers, cached, cookies = result[0], result[1], result[2]
                elif len(result) == 2:
                    headers, cookies, cached = result[0], result[1], {}
                else:
                    headers, cookies, cached = {}, {}, {}
            else:
                headers, cookies, cached = {}, {}, {}

            self._desc_cache = cached or {}
            merged = {**naukri_headers, **headers}
            self.session.headers.update(merged)
            for name, value in (cookies or {}).items():
                self.session.cookies.set(name, value, domain=".naukri.com")
            self._browser_cookies = [
                {"name": n, "value": v, "domain": ".naukri.com", "path": "/"}
                for n, v in (cookies or {}).items()
            ]
            self._has_nkparam = "nkparam" in merged
            log.info(
                f"Ready | headers={len(merged)} | cookies={len(cookies or {})} | "
                f"nkparam={'✓' if self._has_nkparam else '✗'} | pre-cached={len(self._desc_cache)}"
            )
        except Exception as e:
            log.warning(f"Header capture failed: {e}")
            self.session.headers.update(naukri_headers)
            self._has_nkparam = False

        self.scraper_input = None

    # ══════════════════════════════════════════════════════════
    # PLAYWRIGHT — single visible browser + single reused tab
    # ══════════════════════════════════════════════════════════

    def _start_playwright(self):
        try:
            from playwright.sync_api import sync_playwright
            self._pw_instance = sync_playwright().start()
            browser = self._pw_instance.chromium.launch(
                headless=self.HEADLESS_DETAIL,
                args=["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-dev-shm-usage"],
            )
            self._pw_context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            self._pw_context.add_init_script(_STEALTH_SCRIPT)
            if self._browser_cookies:
                self._pw_context.add_cookies(self._browser_cookies)
            # One reusable tab for all jobs (only one window pops up)
            self._pw_page = self._pw_context.new_page()
            log.info(f"Playwright ready (headless={self.HEADLESS_DETAIL}) | "
                     f"{len(self._browser_cookies)} cookies restored")
        except Exception as e:
            log.warning(f"Could not start Playwright: {e}")
            self._pw_context = None
            self._pw_page    = None

    def _stop_playwright(self):
        try:
            if self._pw_instance:
                self._pw_instance.stop()
                log.info("Playwright stopped")
        except Exception:
            pass
        finally:
            self._pw_context = self._pw_page = self._pw_instance = None

    # ══════════════════════════════════════════════════════════
    # SCRAPE
    # ══════════════════════════════════════════════════════════

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        job_list, seen_ids = [], set()
        start       = scraper_input.offset or 0
        page_num    = (start // self.jobs_per_page) + 1
        seconds_old = scraper_input.hours_old * 3600 if scraper_input.hours_old else None
        go = lambda: len(job_list) < scraper_input.results_wanted and page_num <= 50

        if scraper_input.linkedin_fetch_description:
            self._start_playwright()

        try:
            while go():
                log.info(f"Page {page_num} | {len(job_list)}/{scraper_input.results_wanted}")
                params = {
                    "noOfResults": self.jobs_per_page, "urlType": "search_by_keyword",
                    "searchType": "adv", "keyword": scraper_input.search_term,
                    "pageNo": page_num, "k": scraper_input.search_term,
                    "seoKey": f"{scraper_input.search_term.lower().replace(' ','-')}-jobs",
                    "src": "jobsearchDesk", "latLong": "", "location": scraper_input.location or "",
                }
                if scraper_input.is_remote: params["remote"] = "true"
                if seconds_old: params["days"] = seconds_old // 86400

                try:
                    resp = self.session.get(self.base_url, params=params, timeout=15)
                    if not resp.ok:
                        log.error(f"Search API HTTP {resp.status_code}")
                        break
                    data = resp.json()
                    jobs = data.get("jobDetails", [])
                    log.info(f"Search returned {len(jobs)} jobs")
                    if not jobs: break
                except Exception as e:
                    log.error(f"Search API failed: {e}")
                    break

                for job in jobs:
                    jid = job.get("jobId")
                    if not jid or jid in seen_ids: continue
                    seen_ids.add(jid)
                    try:
                        jp = self._process_job(job, jid, scraper_input.linkedin_fetch_description)
                        if jp: job_list.append(jp)
                        if not go(): break
                    except Exception as e:
                        log.error(f"Job {jid}: {e}")

                if go():
                    time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
                    page_num += 1
        finally:
            self._stop_playwright()

        return JobResponse(jobs=job_list[:scraper_input.results_wanted])

    # ══════════════════════════════════════════════════════════
    # PROCESS JOB
    # ══════════════════════════════════════════════════════════

    def _process_job(self, job: dict, job_id: str, full_descr: bool) -> Optional[JobPost]:
        title      = job.get("title", "N/A")
        company    = job.get("companyName", "N/A")
        job_url    = f"https://www.naukri.com{job.get('jdURL', f'/job/{job_id}')}"
        location   = self._location_from_placeholders(job.get("placeholders", []))
        comp       = self._salary_from_placeholders(job.get("placeholders", []))
        posted     = self._parse_date(job.get("footerPlaceholderLabel"), job.get("createdDate"))
        skills_str = job.get("tagsAndSkills", "")
        skills     = [s.strip() for s in skills_str.split(",") if s.strip()] if skills_str else None
        description = self._parse_html(job.get("jobDescription", ""))

        if full_descr:
            full = self._fetch_full_description(job_id, job_url)
            if full and len(full) > len(description):
                description = full
                log.info(f"[✓] {job_id}: {len(description)} chars")

        if description and self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            description = markdown_converter(description)

        ab = job.get("ambitionBoxData", {}) or {}
        return JobPost(
            id=f"nk-{job_id}", title=title, company_name=company,
            company_url=f"https://www.naukri.com/{job.get('staticUrl','')}" if job.get("staticUrl") else None,
            location=location, is_remote=is_job_remote(title, description or "", location),
            date_posted=posted, job_url=job_url, compensation=comp,
            job_type=parse_job_type(description or ""),
            company_industry=parse_company_industry(description or ""),
            description=description,
            emails=extract_emails_from_text(description or ""),
            company_logo=job.get("logoPathV3") or job.get("logoPath"),
            skills=skills, experience_range=job.get("experienceText"),
            company_rating=float(ab["AggregateRating"]) if ab.get("AggregateRating") else None,
            company_reviews_count=ab.get("ReviewsCount"),
            vacancy_count=job.get("vacancy"),
            work_from_home_type=self._infer_wfh(job.get("placeholders",[]), title, description or ""),
        )

    # ══════════════════════════════════════════════════════════
    # FULL DESCRIPTION — reuse single visible tab, DOM extraction
    # ══════════════════════════════════════════════════════════

    def _fetch_full_description(self, job_id: str, job_url: str) -> Optional[str]:
        # T1: pre-cached from cookie_fetcher
        if job_id in self._desc_cache:
            log.debug(f"[cache] {job_id}")
            return self._parse_html(self._desc_cache[job_id])

        page = self._pw_page
        if page is None:
            return None

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for the JD container to render
            try:
                page.wait_for_selector(",".join(_DESC_SELECTORS), timeout=12000)
            except Exception:
                page.wait_for_timeout(4000)

            # T2: extract description from rendered DOM
            for sel in _DESC_SELECTORS:
                try:
                    el = page.query_selector(sel)
                    if el:
                        html = el.inner_html()
                        if html and len(html) > 200:
                            log.info(f"[dom ✓] {job_id} via {sel}")
                            return self._parse_html(html)
                except Exception:
                    pass

            # T3: in-browser fetch() — runs on naukri.com origin with cookies
            try:
                data = page.evaluate(
                    """async (jobId) => {
                        const url = `https://www.naukri.com/jobapi/v4/job/${jobId}`
                                  + `?microsite=y&brandedConsultantJd=true`;
                        try {
                            const r = await fetch(url, {
                                headers: { 'appid':'109', 'systemid':'109' },
                                credentials: 'include'
                            });
                            if (!r.ok) return { error: r.status };
                            return await r.json();
                        } catch(e) { return { error: String(e) }; }
                    }""",
                    job_id,
                )
                if data and not data.get("error"):
                    desc = (
                        data.get("jobDetails", {}).get("description") or
                        data.get("jobDetails", {}).get("jobDescription") or ""
                    )
                    if desc:
                        log.info(f"[fetch ✓] {job_id}: {len(desc)} chars")
                        return self._parse_html(desc)
                else:
                    log.debug(f"[fetch] {job_id}: {data.get('error') if data else 'no data'}")
            except Exception as e:
                log.debug(f"[fetch] {job_id}: {e}")

            log.warning(f"[detail] all methods failed for {job_id}")
            return None

        except Exception as e:
            log.warning(f"[pw] {job_id}: {e}")
            return None

    # ══════════════════════════════════════════════════════════
    # HTML → PLAIN TEXT
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _parse_html(html: str) -> str:
        if not html or not html.strip(): return ""
        if "<" not in html: return html.strip()
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script","style","meta","link"]): t.decompose()
        lines = []
        def walk(el):
            if not hasattr(el,"name"):
                t=str(el).strip()
                if t: lines.append(t)
                return
            n=el.name
            if n in ("h1","h2","h3","h4","h5","h6"):
                t=el.get_text(" ",strip=True)
                if t: lines.append(f"\n{t}")
            elif n in ("ul","ol"):
                for li in el.find_all("li",recursive=False):
                    t=li.get_text(" ",strip=True)
                    if t: lines.append(f"• {t}")
            elif n=="li":
                t=el.get_text(" ",strip=True)
                if t: lines.append(f"• {t}")
            elif n in ("strong","b"):
                t=el.get_text(" ",strip=True)
                if t: lines.append(t)
            elif n=="br": lines.append("")
            elif n in ("p","div","section","article","span","td"):
                if el.find(["ul","ol"]):
                    for c in el.children: walk(c)
                else:
                    t=el.get_text(" ",strip=True)
                    if t: lines.append(t)
            else:
                t=el.get_text(" ",strip=True)
                if t: lines.append(t)
        for c in (soup.find("body") or soup).children: walk(c)
        if not lines: lines=[l for l in soup.get_text("\n",strip=True).split("\n") if l.strip()]
        return re.sub(r'\n{3,}','\n\n',"\n".join(lines)).strip()

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _location_from_placeholders(placeholders):
        for p in placeholders:
            if p.get("type") == "location":
                city = p.get("label","").split("(")[0].strip()
                return Location(city=city, country=Country.INDIA)
        return Location(country=Country.INDIA)

    @staticmethod
    def _salary_from_placeholders(placeholders):
        for p in placeholders:
            if p.get("type") == "salary":
                text = p.get("label","").strip()
                if not text or text.lower() == "not disclosed": return None
                m = re.match(
                    r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(Lacs?|Lakh|Cr)\s*(?:P\.?A\.?)?",
                    text, re.IGNORECASE
                )
                if m:
                    lo,hi=float(m.group(1)),float(m.group(2))
                    mult=100000 if m.group(3).lower() in ("lac","lacs","lakh") else 10000000
                    return Compensation(min_amount=int(lo*mult),max_amount=int(hi*mult),currency="INR")
        return None

    @staticmethod
    def _parse_date(label, created_date):
        today = datetime.now()
        if not label:
            if created_date:
                try:
                    ts=int(created_date)
                    if ts>1e10: ts//=1000
                    return datetime.fromtimestamp(ts).date()
                except Exception: pass
            return None
        lb=label.lower()
        if any(k in lb for k in ("today","just now","few hours","hour")): return today.date()
        m=re.search(r"(\d+)\s*day",lb)
        if m: return (today-timedelta(days=int(m.group(1)))).date()
        m=re.search(r"(\d+)\s*month",lb)
        if m: return (today-timedelta(days=int(m.group(1))*30)).date()
        if "30+" in lb: return (today-timedelta(days=31)).date()
        if created_date:
            try:
                ts=int(created_date)
                if ts>1e10: ts//=1000
                return datetime.fromtimestamp(ts).date()
            except Exception: pass
        return None

    @staticmethod
    def _infer_wfh(placeholders, title, description):
        loc=next((p["label"] for p in placeholders if p.get("type")=="location"),"").lower()
        combo=f"{title} {description} {loc}".lower()
        if "hybrid" in combo: return "Hybrid"
        if "remote" in combo or "work from home" in combo or "wfh" in combo: return "Remote"
        return "Work from office"