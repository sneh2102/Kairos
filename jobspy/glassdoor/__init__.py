from __future__ import annotations

import re
import json
import requests
from typing import Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from jobspy.glassdoor.cookie_fetcher import get_glassdoor_cookies_and_token
from jobspy.glassdoor.cookie_fetcher import get_glassdoor_cookies_and_token, get_glassdoor_location
from jobspy.glassdoor.constant import fallback_token, query_template, headers
from jobspy.glassdoor.util import (
    get_cursor_for_page,
    parse_compensation,
    parse_location,
)
from jobspy.util import (
    extract_emails_from_text,
    create_logger,
    create_session,
    markdown_converter,
)
from jobspy.exception import GlassdoorException
from jobspy.model import (
    JobPost,
    JobResponse,
    DescriptionFormat,
    Scraper,
    ScraperInput,
    Site,
)

log = create_logger("Glassdoor")
KNOWN_LOCATIONS = {
    # ── Canada (country ID verified via GraphQL test) ────────────────
    "canada":               (3,        "COUNTRY"),
    "toronto":              (2281069,  "CITY"),
    "vancouver":            (2278756,  "CITY"),
    "halifax":              (2290928,  "CITY"),
    "dartmouth":            (2290928,  "CITY"),   # same metro as Halifax
    "montreal":             (2296722,  "CITY"),
    "calgary":              (2275123,  "CITY"),
    "ottawa":               (2286068,  "CITY"),
    "edmonton":             (2276227,  "CITY"),
    "winnipeg":             (2283271,  "CITY"),
    "nova scotia":          (3,        "COUNTRY"),  # province-level not exposed; fall back to Canada
    "new brunswick":        (3,        "COUNTRY"),
    "ontario":              (3,        "COUNTRY"),
    "british columbia":     (3,        "COUNTRY"),
    "alberta":              (3,        "COUNTRY"),
    "quebec":               (3,        "COUNTRY"),
    "prince edward island": (3,        "COUNTRY"),
    "pei":                  (3,        "COUNTRY"),
    "newfoundland":         (3,        "COUNTRY"),
    "saskatchewan":         (3,        "COUNTRY"),
    "manitoba":             (3,        "COUNTRY"),

    # ── United Kingdom (verified) ────────────────────────────────────
    "united kingdom":       (2,        "COUNTRY"),
    "uk":                   (2,        "COUNTRY"),

    # ── Australia (verified) ─────────────────────────────────────────
    "australia":            (16,       "COUNTRY"),

    # ── India (country + city metro IDs verified via GraphQL scan) ──
    "india":                (115,      "COUNTRY"),
    "bangalore":            (1091,     "METRO"),
    "bengaluru":            (1091,     "METRO"),
    "mumbai":               (1070,     "METRO"),
    "pune":                 (1072,     "METRO"),
    "hyderabad":            (1076,     "METRO"),
    "chennai":              (1067,     "METRO"),
    "delhi":                (1093,     "METRO"),
    "new delhi":            (1093,     "METRO"),
    "noida":                (1083,     "METRO"),
    "ncr":                  (1083,     "METRO"),
    "ahmedabad":            (1090,     "METRO"),
    "kolkata":              (115,      "COUNTRY"),   # metro ID not found, fall back to country
    "gurgaon":              (115,      "COUNTRY"),
    "gurugram":             (115,      "COUNTRY"),

    # ── Germany (verified) ───────────────────────────────────────────
    "germany":              (96,       "COUNTRY"),

    # ── UAE / Gulf ───────────────────────────────────────────────────
    "uae":                  (6,        "COUNTRY"),
    "dubai":                (6,        "COUNTRY"),
    "united arab emirates": (6,        "COUNTRY"),

    # ── USA (verified) ───────────────────────────────────────────────
    "usa":                  (1,        "COUNTRY"),
    "united states":        (1,        "COUNTRY"),
    "new york":             (1132348,  "CITY"),
    "san francisco":        (1147401,  "CITY"),
    "seattle":              (1150505,  "CITY"),
    "chicago":              (1128808,  "CITY"),
    "austin":               (1139761,  "CITY"),

    # ── Remote ───────────────────────────────────────────────────────
    "remote":               (11047,    "STATE"),
}
class Glassdoor(Scraper):
    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes GlassdoorScraper with the Glassdoor job search url
        """
        site = Site(Site.GLASSDOOR)
        super().__init__(site, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)

        self.base_url = None
        self.country = None
        self.session = None
        self.scraper_input = None
        self.jobs_per_page = 30
        self.max_pages = 30
        self.seen_urls = set()





    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.scraper_input.results_wanted = min(900, scraper_input.results_wanted)
        # Always use .com for API calls — cookies from the browser session are from
        # www.glassdoor.com and cf_clearance is domain-specific. Location filtering
        # is done entirely through the locationId in the GraphQL payload, not the domain.
        self.base_url = "https://www.glassdoor.com"

        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, has_retry=True, is_tls=False
        )

        log.info("Fetching Glassdoor cookies via browser...")
        try:
            cookies, token, ua = get_glassdoor_cookies_and_token()
            self.session.cookies.update(cookies)
            # CRITICAL: use same UA as browser so cf_clearance validates
            headers["user-agent"] = ua
            headers["gd-csrf-token"] = token if token else fallback_token
            log.info(f"Got {len(cookies)} cookies, token: {'found' if token else 'fallback'}")
        except Exception as e:
            log.warning(f"Browser fetch failed: {e}")
            headers["gd-csrf-token"] = fallback_token

        if self.user_agent:
            headers["user-agent"] = self.user_agent
        self.session.headers.update(headers)

        location_id, location_type = self._get_location(
            scraper_input.location, scraper_input.is_remote
        )
        if location_type is None:
            log.error("Glassdoor: location not parsed")
            return JobResponse(jobs=[])

        job_list: list[JobPost] = []
        cursor = None
        range_start = 1 + (scraper_input.offset // self.jobs_per_page)
        tot_pages = (scraper_input.results_wanted // self.jobs_per_page) + 2
        range_end = min(tot_pages, self.max_pages + 1)

        for page in range(range_start, range_end):
            log.info(f"search page: {page} / {range_end - 1}")
            try:
                jobs, cursor = self._fetch_jobs_page(
                    scraper_input, location_id, location_type, page, cursor
                )
                job_list.extend(jobs)
                if not jobs or len(job_list) >= scraper_input.results_wanted:
                    job_list = job_list[: scraper_input.results_wanted]
                    break
            except Exception as e:
                log.error(f"Glassdoor: {str(e)}")
                break

        return JobResponse(jobs=job_list)

    def _fetch_jobs_page(self, scraper_input, location_id, location_type, page_num, cursor):
        jobs = []
        self.scraper_input = scraper_input
        try:
            payload = self._add_payload(location_id, location_type, page_num, cursor)
            response = self.session.post(
                f"{self.base_url}/graph",
                timeout=15,
                data=payload,
            )
            if response.status_code != 200:
                raise GlassdoorException(f"bad response status code: {response.status_code}")
            res_json = response.json()[0]
            if "errors" in res_json:
                # Only fail on critical errors — seoData errors are non-critical
                critical = [
                    e for e in res_json["errors"]
                    if "jobsPageSeoData" not in str(e.get("path", []))
                    and "jobSerpJobOutlook" not in str(e.get("path", []))
                ]
                if critical:
                    raise ValueError(f"Critical API errors: {critical}")
                else:
                    log.warning(f"Non-critical API errors ignored: {[e['path'] for e in res_json['errors']]}")
        except (requests.exceptions.ReadTimeout, GlassdoorException, ValueError, Exception) as e:
            log.error(f"Glassdoor: {str(e)}")
            return jobs, None

        jobs_data = res_json["data"]["jobListings"]["jobListings"]
        with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
            future_to_job_data = {executor.submit(self._process_job, job): job for job in jobs_data}
            for future in as_completed(future_to_job_data):
                try:
                    job_post = future.result()
                    if job_post:
                        jobs.append(job_post)
                except Exception as exc:
                    raise GlassdoorException(f"Glassdoor generated an exception: {exc}")

        return jobs, get_cursor_for_page(
            res_json["data"]["jobListings"]["paginationCursors"], page_num + 1
        )
    
    def _get_csrf_token(self):
        """
        Fetches csrf token needed for API by visiting a generic page
        """
        res = self.session.get(f"{self.base_url}/Job/computer-science-jobs.htm")
        pattern = r'"token":\s*"([^"]+)"'
        matches = re.findall(pattern, res.text)
        token = None
        if matches:
            token = matches[0]
        return token

    def _process_job(self, job_data):
        """
        Processes a single job and fetches its description.
        """
        job_id = job_data["jobview"]["job"]["listingId"]
        job_url = f"{self.base_url}/job-listing/j?jl={job_id}"
        if job_url in self.seen_urls:
            return None
        self.seen_urls.add(job_url)
        job = job_data["jobview"]
        title = job["job"]["jobTitleText"]
        company_name = job["header"]["employerNameFromSearch"]
        company_id = job_data["jobview"]["header"]["employer"]["id"]
        location_name = job["header"].get("locationName", "")
        location_type = job["header"].get("locationType", "")
        age_in_days = job["header"].get("ageInDays")
        is_remote, location = False, None
        date_diff = (datetime.now() - timedelta(days=age_in_days)).date()
        date_posted = date_diff if age_in_days is not None else None

        if location_type == "S":
            is_remote = True
        else:
            location = parse_location(location_name)

        compensation = parse_compensation(job["header"])
        try:
            description = self._fetch_job_description(job_id)
        except:
            description = None
        company_url = f"{self.base_url}/Overview/W-EI_IE{company_id}.htm"
        company_logo = (
            job_data["jobview"].get("overview", {}).get("squareLogoUrl", None)
        )
        listing_type = (
            job_data["jobview"]
            .get("header", {})
            .get("adOrderSponsorshipLevel", "")
            .lower()
        )
        return JobPost(
            id=f"gd-{job_id}",
            title=title,
            company_url=company_url if company_id else None,
            company_name=company_name,
            date_posted=date_posted,
            job_url=job_url,
            location=location,
            compensation=compensation,
            is_remote=is_remote,
            description=description,
            emails=extract_emails_from_text(description) if description else None,
            company_logo=company_logo,
            listing_type=listing_type,
        )

    def _fetch_job_description(self, job_id):
        """
        Fetches the job description for a single job ID.
        """
        url = f"{self.base_url}/graph"
        body = [
            {
                "operationName": "JobDetailQuery",
                "variables": {
                    "jl": job_id,
                    "queryString": "q",
                    "pageTypeEnum": "SERP",
                },
                "query": """
                query JobDetailQuery($jl: Long!, $queryString: String, $pageTypeEnum: PageTypeEnum) {
                    jobview: jobView(
                        listingId: $jl
                        contextHolder: {queryString: $queryString, pageTypeEnum: $pageTypeEnum}
                    ) {
                        job {
                            description
                            __typename
                        }
                        __typename
                    }
                }
                """,
            }
        ]
        res = self.session.post(url, json=body, headers=headers)
        if res.status_code != 200:
            return None
        data = res.json()[0]
        desc = data["data"]["jobview"]["job"]["description"]
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            desc = markdown_converter(desc)
        return desc


# Known Glassdoor location IDs — bypasses the blocked location lookup endpoint
    

    def _get_location(self, location: str, is_remote: bool) -> tuple:
        if is_remote:
            return 11047, "STATE"   # Glassdoor "Remote" pseudo-state (US-hosted but returns remote globally)

        key = location.strip().lower() if location else ""

        # 1. Exact match in hardcoded table
        if key in KNOWN_LOCATIONS:
            loc_id, loc_type = KNOWN_LOCATIONS[key]
            log.info(f"Glassdoor: exact match '{key}' -> id={loc_id}, type={loc_type}")
            return loc_id, loc_type

        # 2. Partial match — e.g. "Halifax, Nova Scotia, Canada" contains "halifax"
        for known_key, (loc_id, loc_type) in KNOWN_LOCATIONS.items():
            if known_key in key:
                log.info(f"Glassdoor: partial match '{known_key}' -> id={loc_id}, type={loc_type}")
                return loc_id, loc_type

        # 3. Live endpoint (may be Cloudflare-blocked but worth trying)
        if key:
            url = f"{self.base_url}/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={location}"
            try:
                res = self.session.get(url, timeout=10)
                if res.status_code == 200:
                    items = res.json()
                    if items:
                        raw_type = items[0]["locationType"]
                        loc_type = {"C": "CITY", "S": "STATE", "N": "COUNTRY"}.get(raw_type, raw_type)
                        loc_id   = int(items[0]["locationId"])
                        log.info(f"Glassdoor: live lookup '{location}' -> id={loc_id}, type={loc_type}")
                        return loc_id, loc_type
            except Exception as e:
                log.warning(f"Glassdoor live location lookup failed: {e}")

        # 4. No location given or lookup failed — fall back to the scraper's country
        country = self.scraper_input.country
        country_key = country.value[0].split(",")[0].strip().lower() if country else ""
        if country_key in KNOWN_LOCATIONS:
            loc_id, loc_type = KNOWN_LOCATIONS[country_key]
            log.info(f"Glassdoor: no location given, using country fallback '{country_key}' -> id={loc_id}, type={loc_type}")
            return loc_id, loc_type

        log.error(f"Glassdoor: could not resolve location '{location}' — returning None")
        return None, None

    def _add_payload(self, location_id, location_type, page_num, cursor=None):
        fromage = None
        if self.scraper_input.hours_old:
            fromage = max(self.scraper_input.hours_old // 24, 1)

        filter_params = []
        if self.scraper_input.easy_apply:
            filter_params.append({"filterKey": "applicationType", "values": "1"})
        if fromage:
            filter_params.append({"filterKey": "fromAge", "values": str(fromage)})

        # ✅ Correct Glassdoor location type codes
        type_code_map = {
            "CITY":    "IC",
            "STATE":   "IS",
            "COUNTRY": "IN",
            "METRO":   "IM",
        }
        type_code = type_code_map.get(location_type, "IC")

        payload = {
            "operationName": "JobSearchResultsQuery",
            "variables": {
                "excludeJobListingIds": [],
                "filterParams":        filter_params,
                "keyword":             self.scraper_input.search_term,
                "numJobsToShow":       30,
                "locationType":        location_type,
                "locationId":          int(location_id),
                "parameterUrlInput":   f"IL.0,12_{type_code}{location_id}",  # ✅ fixed
                "pageNumber":          page_num,
                "pageCursor":          cursor,
                "fromage":             fromage,
                "sort":                "date",
            },
            "query": query_template,
        }
        if self.scraper_input.job_type:
            payload["variables"]["filterParams"].append(
                {"filterKey": "jobType", "values": self.scraper_input.job_type.value[0]}
            )
        return json.dumps([payload])