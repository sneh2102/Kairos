from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta

import requests

from jobspy.util import create_logger, extract_emails_from_text, markdown_converter
from jobspy.model import (
    JobPost, Location, JobResponse, Scraper,
    ScraperInput, Site, Compensation, CompensationInterval,
)

log = create_logger("JobRight")

BASE_URL      = "https://jobright.ai"
JOBS_PER_PAGE = 20
COUNTRY_MAP   = {
    "canada":        "CA",
    "ca":            "CA",
    "united states": "US",
    "usa":           "US",
    "us":            "US",
}


class JobRight(Scraper):

    def __init__(self, proxies=None, ca_cert=None, user_agent=None):
        super().__init__(Site.JOBRIGHT, proxies=proxies, ca_cert=ca_cert)
        self.scraper_input  = None
        self.seen_ids       = set()
        self._logged_sample = False
        self.session        = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://jobright.ai/",
            "Origin":          "https://jobright.ai",
        })

    # ── public ────────────────────────────────────────────────────────────────
    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        country_code = self._detect_country(scraper_input)

        position = 0
        all_jobs = []

        while len(all_jobs) < scraper_input.results_wanted:
            log.info(f"JobRight: fetching position {position}")
            batch = self._fetch_via_post_api(scraper_input, country_code, position)

            if batch:
                all_jobs.extend(batch)
                if len(batch) < JOBS_PER_PAGE:
                    break
                position += JOBS_PER_PAGE
            else:
                log.info("JobRight: direct API empty — using Playwright")
                playwright_jobs = self._fetch_via_playwright(scraper_input, 1, country_code)
                all_jobs.extend(playwright_jobs)
                break

            if len(all_jobs) >= scraper_input.results_wanted:
                break

        log.info("JobRight: finished scraping")
        return JobResponse(jobs=all_jobs[: scraper_input.results_wanted])

    # ── country detection ─────────────────────────────────────────────────────
    def _detect_country(self, scraper_input: ScraperInput) -> str:
        location = scraper_input.location or ""
        code     = "US"
        for key, c in COUNTRY_MAP.items():
            if key in location.lower():
                code = c
                break
        if hasattr(scraper_input, "country") and scraper_input.country:
            cs   = scraper_input.country.value[0].lower().split(",")[0]
            code = COUNTRY_MAP.get(cs, code)
        return code

    # ── direct REST API ───────────────────────────────────────────────────────
    def _fetch_via_post_api(
        self,
        scraper_input: ScraperInput,
        country_code: str,
        position: int,
    ) -> list[JobPost] | None:
        search  = scraper_input.search_term or "software engineer"
        payload = {
            "value":             search,
            "country":           country_code,
            "jobTaxonomyList":   [],
            "locations":         [],
            "jobTypes":          [],
            "seniority":         [],
            "workModel":         ["Remote"] if scraper_input.is_remote else [],
            "searchType":        "job_title",
            "companies":         [],
            "isH1BOnly":         False,
            "excludedCompanies": [],
            "position":          position,
            "count":             JOBS_PER_PAGE,
        }
        url = (
            "https://jobright.ai/swan/recommend/visitor-list/jobs"
            f"?sortCondition=0&count={JOBS_PER_PAGE}"
            f"&position={position}&useLegacySearch=true"
        )
        try:
            res = self.session.post(url, json=payload, timeout=15)
            log.info(f"JobRight direct API: {res.status_code} country={country_code}")
            if res.status_code != 200:
                return None
            data     = res.json()
            result   = data.get("result", {})
            jobs_raw = (
                result.get("jobList") or
                result.get("list")    or
                result.get("jobs")    or
                (result if isinstance(result, list) else None)
            )
            if not jobs_raw:
                log.info("JobRight direct API: empty jobList (unauthenticated visitor)")
                return None
            log.info(f"JobRight direct API: {len(jobs_raw)} jobs")
            return [j for j in (self._parse_api_job(r) for r in jobs_raw) if j]
        except Exception as e:
            log.debug(f"JobRight direct API error: {e}")
            return None

    # ── playwright scraper ────────────────────────────────────────────────────
    def _fetch_via_playwright(self, scraper_input, page, country_code):
        from playwright.sync_api import sync_playwright

        all_raw        = []
        search         = scraper_input.search_term or "software engineer"
        slug           = search.lower().replace(" ", "-")
        location       = scraper_input.location or ""
        results_wanted = scraper_input.results_wanted or 20

        url = f"{BASE_URL}/jobs/{slug}"
        query = []
        if country_code == "CA":
            query.append("country=Canada")
        elif location:
            query.append(f"location={location.replace(' ', '+')}")
        if query:
            url += "?" + "&".join(query)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=not (country_code == "CA"),
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                    locale="en-US",
                )
                web_page = context.new_page()

                # ── Login for Canada ──────────────────────────────────
                if country_code == "CA":
                    logged_in = self._do_login(web_page)
                    if not logged_in:
                        log.warning("JobRight: login failed")

                # ── Navigate to jobs page ─────────────────────────────
                log.info(f"JobRight Playwright: {url}")
                web_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    web_page.wait_for_selector('a[class*="job-card"]', timeout=10000)
                except Exception:
                    pass
                web_page.wait_for_timeout(2000)

                # ── Paginate via real API using browser fetch() ───────
                position = 0
                count    = 10
                no_new   = 0

                while len(all_raw) < results_wanted:
                    log.info(
                        "JobRight API: position=%d | collected=%d / %d",
                        position, len(all_raw), results_wanted
                    )

                    result = web_page.evaluate(f"""
                        async () => {{
                            try {{
                                const res = await fetch(
                                    '/swan/recommend/list/jobs?refresh=false&sortCondition=0&position={position}&count={count}&syncRerank=false',
                                    {{
                                        method: 'GET',
                                        headers: {{
                                            'accept': 'application/json, text/plain, */*',
                                            'x-requested-with': 'XMLHttpRequest',
                                        }},
                                        credentials: 'include',
                                    }}
                                );
                                if (!res.ok) return {{ error: res.status }};
                                return await res.json();
                            }} catch(e) {{
                                return {{ error: String(e) }};
                            }}
                        }}
                    """)

                    if not result or result.get("error"):
                        log.warning("JobRight API error at position %d: %s", position, result)
                        break

                    job_list = (
                        result.get("result", {}).get("jobList") or
                        result.get("data",   {}).get("jobList") or
                        result.get("jobs")                      or
                        []
                    )

                    if not job_list:
                        no_new += 1
                        log.info("JobRight: empty jobList at position %d (%d/3)", position, no_new)
                        if no_new >= 3:
                            log.info("JobRight: API exhausted")
                            break
                        position += count
                        continue

                    no_new = 0

                    # Deduplicate by jobId
                    existing_ids = {
                        str(j.get("jobResult", j).get("jobId", j.get("id", "")))
                        for j in all_raw
                    }
                    new_jobs = [
                        j for j in job_list
                        if str(j.get("jobResult", j).get("jobId", j.get("id", "")))
                        not in existing_ids
                    ]

                    log.info(
                        "JobRight API position=%d: +%d new (total %d)",
                        position, len(new_jobs), len(all_raw) + len(new_jobs)
                    )
                    all_raw.extend(new_jobs)
                    position += count

                    if len(new_jobs) < count:
                        log.info("JobRight: last page (got %d < %d)", len(new_jobs), count)
                        break

                browser.close()

                if all_raw:
                    log.info("JobRight: parsing %d jobs", len(all_raw))
                    return [j for j in (self._parse_api_job(r) for r in all_raw) if j]

        except Exception as e:
            log.error(f"JobRight Playwright error: {e}")

        return []

    # ── SSO login ─────────────────────────────────────────────────────────────
    def _do_login(self, page) -> bool:
        log.info("JobRight: opening homepage for SSO login...")
        page.goto("https://jobright.ai/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        try:
            page.locator(
                'a[href*="sign"], button:has-text("Sign In"), '
                'a:has-text("Sign In"), a:has-text("SIGN IN")'
            ).first.click()
            page.wait_for_timeout(2000)
            log.info(f"JobRight: clicked Sign In, now at {page.url}")
        except Exception as e:
            log.warning(f"JobRight: could not click Sign In: {e}")

        print("\n" + "="*55)
        print("JOBRIGHT SSO LOGIN REQUIRED")
        print("="*55)
        print("Browser is open at:", page.url)
        print("Please complete your SSO login.")
        print("Scraper continues automatically after login.")
        print("="*55 + "\n")

        try:
            page.wait_for_function(
                """() => {
                    const url = window.location.href;
                    return (
                        url.includes('/jobs') ||
                        url.includes('/dashboard') ||
                        document.querySelector('img[alt*="avatar"]') !== null ||
                        document.querySelector('[class*="user-avatar"]') !== null
                    );
                }""",
                timeout=120000
            )
            log.info("JobRight: ✅ SSO login detected")
            page.wait_for_timeout(2000)
            return True
        except Exception:
            log.warning("JobRight: SSO login timeout")
            return False

    # ── main job parser ───────────────────────────────────────────────────────
    def _parse_api_job(self, job: dict) -> JobPost | None:
        try:
            job_result  = job.get("jobResult")     or job
            comp_result = job.get("companyResult") or {}

            job_id = (
                job_result.get("jobId")    or
                job_result.get("id")       or
                job_result.get("listingId")
            )
            if not job_id or str(job_id) in self.seen_ids:
                return None
            self.seen_ids.add(str(job_id))

            # ── Basic fields ──────────────────────────────────────────
            title      = job_result.get("jobTitle")    or "N/A"
            location   = job_result.get("jobLocation") or ""
            is_remote  = job_result.get("isRemote", False) or \
                         str(job_result.get("workModel", "")).lower() == "remote"
            date_str   = job_result.get("publishTime")
            job_url    = (
                job_result.get("originalUrl") or
                job_result.get("applyLink")   or
                f"https://jobright.ai/jobs/info/{job_id}"
            )
            logo       = job_result.get("jdLogo")       or comp_result.get("companyLogo")
            company    = comp_result.get("companyName") or job_result.get("companyName") or ""
            company_url= comp_result.get("companyURL")  or comp_result.get("companyLinkedinURL")
            job_type_s = job_result.get("employmentType", "")
            job_level  = job_result.get("jobSeniority", "")

            # ── Salary ────────────────────────────────────────────────
            salary_desc = job_result.get("salaryDesc", "")
            min_amount  = None
            max_amount  = None
            currency    = None
            interval    = None
            if salary_desc:
                currency = "CAD" if "CA$" in salary_desc else "USD" if "$" in salary_desc else None
                interval = "yearly" if "/yr" in salary_desc else "hourly" if "/hr" in salary_desc else None
                amounts  = re.findall(r'[\d,]+(?:\.\d+)?K?', salary_desc)

                def parse_amt(s):
                    s = s.replace(",", "")
                    if s.endswith("K"):
                        return float(s[:-1]) * 1000
                    return float(s) if s else None

                if len(amounts) >= 1:
                    min_amount = parse_amt(amounts[0])
                if len(amounts) >= 2:
                    max_amount = parse_amt(amounts[1])

            # ── Rich description ──────────────────────────────────────
            desc_parts = []

            summary = job_result.get("jobSummary", "")
            if summary:
                desc_parts.append(f"## Summary\n{summary}")

            responsibilities = job_result.get("coreResponsibilities", [])
            if responsibilities:
                desc_parts.append(
                    "## Responsibilities\n" + "\n".join(f"- {r}" for r in responsibilities)
                )

            must_have = job_result.get("qualifications", {}).get("mustHave", [])
            if must_have:
                desc_parts.append(
                    "## Requirements\n" + "\n".join(f"- {r}" for r in must_have)
                )

            preferred = job_result.get("qualifications", {}).get("preferredHave", [])
            if preferred:
                desc_parts.append(
                    "## Nice to Have\n" + "\n".join(f"- {r}" for r in preferred)
                )

            core_skills = job_result.get("jdCoreSkills", [])
            if core_skills:
                skill_names = [s["skill"] for s in core_skills if s.get("skill")]
                desc_parts.append("## Required Skills\n" + ", ".join(skill_names))

            skill_summaries = job_result.get("skillSummaries", [])
            if skill_summaries:
                desc_parts.append(
                    "## Skill Details\n" + "\n".join(f"- {s}" for s in skill_summaries)
                )

            benefits = job_result.get("benefitsSummaries", [])
            if benefits:
                desc_parts.append(
                    "## Benefits\n" + "\n".join(f"- {b}" for b in benefits)
                )

            why_join = job_result.get("whyJoinUs", "")
            if why_join:
                desc_parts.append(f"## Why Join Us\n{why_join}")

            # Company section
            comp_desc  = comp_result.get("companyDesc", "")
            comp_size  = comp_result.get("companySize", "")
            comp_cats  = comp_result.get("companyCategories", "")
            comp_loc   = comp_result.get("companyLocation", "")
            comp_year  = comp_result.get("companyFoundYear", "")
            comp_stage = comp_result.get("fundraisingCurrentStage", "")
            comp_info  = []
            if comp_desc:  comp_info.append(f"**About:** {comp_desc}")
            if comp_size:  comp_info.append(f"**Size:** {comp_size}")
            if comp_cats:  comp_info.append(f"**Industry:** {comp_cats}")
            if comp_loc:   comp_info.append(f"**HQ:** {comp_loc}")
            if comp_year:  comp_info.append(f"**Founded:** {comp_year}")
            if comp_stage: comp_info.append(f"**Stage:** {comp_stage}")
            if comp_info:
                desc_parts.append("## Company\n" + "\n".join(comp_info))

            taxonomy = job_result.get("jobTaxonomyV3", [])
            if taxonomy:
                desc_parts.append("## Category\n" + " > ".join(taxonomy))

            # Meta
            meta = []
            work_model = job_result.get("workModel", "")
            if work_model:  meta.append(f"**Work Model:** {work_model}")
            applicants = job_result.get("applicantsCount")
            if applicants:  meta.append(f"**Applicants:** {applicants}")
            h1b = job_result.get("isH1bSponsor")
            if h1b is not None: meta.append(f"**H1B Sponsor:** {'Yes' if h1b else 'No'}")
            if job_result.get("isWorkAuthRequired"):
                meta.append("**Work Auth Required:** Yes")
            if job_result.get("isClearanceRequired"):
                meta.append("**Clearance Required:** Yes")
            if meta:
                desc_parts.append("## Details\n" + "\n".join(meta))

            description = "\n\n".join(desc_parts)

            # ── Skills — must be list ─────────────────────────────────
            skills_list = [s["skill"] for s in core_skills if s.get("skill")]

            # ── company_num_employees — must be str ───────────────────
            comp_num_employees = None
            if comp_size:
                nums = re.findall(r'\d+', comp_size)
                if nums:
                    comp_num_employees = str(int(nums[-1]))  # str, not int

            # ── Log sample once ───────────────────────────────────────
            if not self._logged_sample:
                self._logged_sample = True
                log.info(
                    "JobRight sample — title: %s | company: %s | salary: %s | skills: %s",
                    title, company, salary_desc, ", ".join(skills_list[:5])
                )

            return JobPost(
                id=f"jr-{job_id}",
                title=str(title),
                company_name=company,
                company_url=company_url,
                company_logo=logo,
                company_industry=comp_cats or None,
                company_description=comp_desc or None,
                company_num_employees=comp_num_employees,   # str or None
                job_url=job_url,
                job_url_direct=job_result.get("originalUrl") or None,
                location=self._parse_location(str(location)),
                compensation=self._parse_salary_fields(min_amount, max_amount, currency, interval),
                date_posted=self._parse_date(str(date_str)) if date_str else None,
                is_remote=is_remote,
                job_type=self._parse_job_type(job_type_s),  # list or None
                job_level=job_level or None,
                description=description or None,
                emails=extract_emails_from_text(description) if description else None,
                skills=skills_list if skills_list else None,  # list or None
            )

        except Exception as e:
            log.warning(f"JobRight parse error: {e} | keys={list(job.keys())[:5]}")
            return None

    # ── salary builder ────────────────────────────────────────────────────────
    def _parse_salary_fields(self, min_amount, max_amount, currency, interval):
        try:
            if not min_amount and not max_amount:
                return None
            interval_map = {
                "yearly":  CompensationInterval.YEARLY,
                "hourly":  CompensationInterval.HOURLY,
                "monthly": CompensationInterval.MONTHLY,
            }
            return Compensation(
                min_amount=min_amount,
                max_amount=max_amount,
                currency=currency or "USD",
                interval=interval_map.get(interval, CompensationInterval.YEARLY),
            )
        except Exception:
            return None

    # ── job type — returns list ───────────────────────────────────────────────
    @staticmethod
    def _parse_job_type(job_type_str: str):
        try:
            from jobspy.model import JobType
            s = (job_type_str or "").lower()
            if "full" in s:     return [JobType.FULL_TIME]
            if "part" in s:     return [JobType.PART_TIME]
            if "contract" in s: return [JobType.CONTRACT]
            if "intern" in s:   return [JobType.INTERNSHIP]
            if "temp" in s:     return [JobType.TEMPORARY]
        except Exception:
            pass
        return None

    # ── DOM card fallback ─────────────────────────────────────────────────────
    def _parse_dom_card(self, card: dict) -> JobPost | None:
        try:
            job_id = card.get("id")
            if not job_id or job_id in self.seen_ids:
                return None
            self.seen_ids.add(job_id)

            title   = card.get("title")  or "N/A"
            company = card.get("company")
            job_url = card.get("url")    or f"{BASE_URL}/jobs/info/{job_id}"
            posted  = card.get("posted") or ""
            meta    = card.get("meta")   or []

            location_str = meta[0] if len(meta) > 0 else ""
            salary_str   = next((m for m in meta if "$" in m), "")
            is_remote    = any("remote" in m.lower() for m in meta) or "remote" in title.lower()

            return JobPost(
                id=f"jr-{job_id}",
                title=title,
                company_name=company,
                job_url=job_url,
                location=self._parse_location(location_str),
                compensation=self._parse_salary(salary_str),
                date_posted=self._parse_relative_date(posted),
                is_remote=is_remote,
            )
        except Exception as e:
            log.warning(f"JobRight DOM parse error: {e}")
            return None

    # ── static helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _parse_location(loc_str: str) -> Location:
        if not loc_str or loc_str == "None":
            return Location()
        parts = [p.strip() for p in loc_str.split(",")]
        city  = parts[0] if parts else None
        state = parts[1] if len(parts) > 1 else None
        return Location(city=city, state=state)

    @staticmethod
    def _parse_salary(salary_str: str) -> Compensation | None:
        if not salary_str or salary_str == "None":
            return None
        try:
            cleaned = salary_str.replace("K", "000").replace("k", "000")
            nums    = re.findall(r"[\d,]+\.?\d*", cleaned)
            if not nums:
                return None
            mn       = float(nums[0].replace(",", ""))
            mx       = float(nums[1].replace(",", "")) if len(nums) > 1 else mn
            interval = (
                CompensationInterval.HOURLY  if "/hr" in salary_str.lower() else
                CompensationInterval.MONTHLY if "/mo" in salary_str.lower() else
                CompensationInterval.YEARLY
            )
            return Compensation(interval=interval, min_amount=mn, max_amount=mx, currency="USD")
        except Exception:
            return None

    @staticmethod
    def _parse_date(date_str: str):
        if not date_str or date_str == "None":
            return None
        for fmt in (
            "%Y-%m-%d %H:%M:%S",       # JobRight primary format
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(date_str[:len(fmt)], fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_relative_date(text: str):
        if not text:
            return None
        now  = datetime.now()
        text = text.lower()
        m    = re.search(r"(\d+)\s*(minute|hour|day|week|month)", text)
        if not m:
            return now.date()
        n, unit = int(m.group(1)), m.group(2)
        delta   = {
            "minute": timedelta(minutes=n),
            "hour":   timedelta(hours=n),
            "day":    timedelta(days=n),
            "week":   timedelta(weeks=n),
            "month":  timedelta(days=n * 30),
        }.get(unit, timedelta(0))
        return (now - delta).date()