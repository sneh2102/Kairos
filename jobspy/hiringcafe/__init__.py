from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timedelta, timezone

from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    Location,
    Country,
    Compensation,
    CompensationInterval,
    DescriptionFormat,
)
from jobspy.util import (
    create_logger,
    create_session,
    get_enum_from_value,
    markdown_converter,
    plain_converter,
)

log = create_logger("HiringCafe")


class HiringCafe(Scraper):
    base_url = "https://hiringcafe.com"

    # Shared across instances/search terms in the same process — jobspy builds
    # a fresh HiringCafe() per site call, so an instance-level cache would
    # still re-fetch the build id (and description-fetch volume alone is
    # enough to trip Cloudflare's rate limit) on every search term otherwise.
    _build_id_cache: str | None = None
    _build_id_cached_at: float = 0
    _BUILD_ID_TTL = 1800  # seconds
    _location_cache: dict = {}

    # hiring.cafe's own UI (ADD_LOCATION handler) defaults a freshly-picked
    # country/state to flexible_regions: ["anywhere_in_continent",
    # "anywhere_in_world"] — i.e. its own default is NOT restricted to that
    # country, it's opted in to continent- and world-wide matches too (this
    # is exactly the shape in the curl the user captured). That's why a
    # "Canada" search was still returning USA/UK/Mexico-only postings.
    # Leaving flexible_regions off entirely restricts results to listings
    # that actually include the picked place — verified live: 0/93 results
    # lacked "CA" in workplace_countries once flexible_regions was dropped.
    _LOCATION_OPTIONS_BY_TYPE = {
        "locality": {"radius": 50, "radius_unit": "miles", "ignore_radius": False},
        "postal_code": {"radius": 50, "radius_unit": "miles", "ignore_radius": False},
    }

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        super().__init__(Site.HIRINGCAFE, proxies=proxies, ca_cert=ca_cert)
        self.session = None
        self._preferred_country_code: str | None = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.session = create_session(proxies=self.proxies, ca_cert=self.ca_cert, is_tls=True)
        self.session.headers.update(
            {
                "accept": "*/*",
                "referer": f"{self.base_url}/",
                "x-nextjs-data": "1",
            }
        )
        build_id = self._get_build_id()
        if not build_id:
            log.error("HiringCafe: could not resolve Next.js build id")
            return JobResponse(jobs=[])

        results_wanted = scraper_input.results_wanted or 15
        search_state = {"searchQuery": scraper_input.search_term or ""}
        if scraper_input.hours_old:
            # Server-side pre-filter only — it's keyed on when hiring.cafe
            # crawled/re-indexed the listing, not when the employer posted
            # it, so a job can match this and still be weeks old. The real
            # cutoff is enforced client-side in _process_job below.
            search_state["dateFetchedPastNDays"] = max(1, math.ceil(scraper_input.hours_old / 24))
            search_state["sortBy"] = "date"
        if scraper_input.is_remote:
            search_state["workplaceTypes"] = ["Remote"]
        if scraper_input.location:
            location_entry = self._resolve_location(scraper_input.location)
            if location_entry:
                search_state["locations"] = [location_entry]
                country_component = next(
                    (
                        c
                        for c in location_entry.get("address_components", [])
                        if "country" in (c.get("types") or [])
                    ),
                    None,
                )
                if country_component:
                    self._preferred_country_code = country_component.get("short_name")
            else:
                log.warning(
                    f"HiringCafe: could not resolve location '{scraper_input.location}', searching worldwide"
                )

        job_list: list[JobPost] = []
        seen_ids: set[str] = set()
        page = 0
        max_pages = 25  # ponytail: hard cap in case ssrIsLastPage never flips
        while len(job_list) < results_wanted and page < max_pages:
            result = self._fetch_page(build_id, search_state, page)
            if not result:
                break
            hits, is_last_page = result

            for hit in hits:
                job_post = self._process_job(hit, scraper_input)
                if job_post and job_post.id not in seen_ids:
                    seen_ids.add(job_post.id)
                    job_list.append(job_post)
                    if len(job_list) >= results_wanted:
                        break
            if is_last_page or not hits:
                break
            page += 1

        return JobResponse(jobs=job_list[:results_wanted])

    def _get(self, url: str, params: dict | None = None, retries: int = 4):
        """GET with backoff on 429 — hiring.cafe's Cloudflare rate limit trips
        easily once per-job description fetches are in play, and can stay
        tripped for tens of seconds."""
        for attempt in range(retries + 1):
            try:
                resp = self.session.get(url, params=params)
            except Exception as e:
                log.error(f"HiringCafe: request error for {url} - {str(e)}")
                return None
            if resp.ok:
                return resp
            if resp.status_code == 429 and attempt < retries:
                time.sleep(3 * (2**attempt))
                continue
            log.error(f"HiringCafe: request to {url} failed - status {resp.status_code}")
            return None
        return None

    def _get_build_id(self) -> str | None:
        now = time.time()
        if self._build_id_cache and now - HiringCafe._build_id_cached_at < self._BUILD_ID_TTL:
            return HiringCafe._build_id_cache

        resp = self._get(self.base_url)
        if not resp:
            return None
        match = re.search(r'"buildId":"(.*?)"', resp.text)
        build_id = match.group(1) if match else None
        if build_id:
            HiringCafe._build_id_cache = build_id
            HiringCafe._build_id_cached_at = now
        return build_id

    def _fetch_page(self, build_id: str, search_state: dict, page: int) -> tuple[list, bool] | None:
        url = f"{self.base_url}/_next/data/{build_id}/index.json"
        params = {"searchState": json.dumps(search_state), "page": str(page)}
        resp = self._get(url, params=params)
        if not resp:
            return None
        try:
            page_props = resp.json().get("pageProps", {})
            return page_props.get("ssrHits", []), bool(page_props.get("ssrIsLastPage"))
        except Exception as e:
            log.error(f"HiringCafe: error parsing page {page} - {str(e)}")
            return None

    def _resolve_location(self, location: str) -> dict | None:
        cached = HiringCafe._location_cache.get(location)
        if cached is not None:
            return cached or None

        resp = self._get(f"{self.base_url}/api/searchLocation", params={"query": location})
        results = None
        if resp:
            try:
                results = resp.json()
            except Exception as e:
                log.error(f"HiringCafe: error parsing location search for '{location}' - {str(e)}")

        entry = None
        if results:
            match = next(
                (r for r in results if str(r.get("label", "")).strip().lower() == location.strip().lower()),
                results[0],
            )
            place = match.get("placeDetail")
            if place:
                place_type = (place.get("types") or [None])[0]
                options = self._LOCATION_OPTIONS_BY_TYPE.get(place_type, {})
                entry = {**place, "workplace_types": [], "options": options}

        HiringCafe._location_cache[location] = entry or False
        return entry

    def _fetch_description(self, job_id: str, description_format: DescriptionFormat) -> str | None:
        time.sleep(0.15)  # ponytail: flat throttle, tune if the rate limit still trips
        resp = self._get(f"{self.base_url}/api/job-description", params={"id": job_id})
        if not resp:
            return None
        try:
            desc = resp.json().get("job", {}).get("job_information", {}).get("description")
        except Exception as e:
            log.error(f"HiringCafe: error parsing description for {job_id} - {str(e)}")
            return None
        if not desc:
            return None
        if description_format == DescriptionFormat.MARKDOWN:
            return markdown_converter(desc)
        if description_format == DescriptionFormat.PLAIN:
            return plain_converter(desc)
        return desc

    def _process_job(self, hit: dict, scraper_input: ScraperInput) -> JobPost | None:
        job_id = hit.get("id")
        v5 = hit.get("v5_processed_job_data") or {}
        job_info = hit.get("job_information") or {}
        title = v5.get("core_job_title") or job_info.get("title") or job_info.get("job_title_raw")
        job_url = hit.get("apply_url")
        if not job_id or not title or not job_url:
            return None

        is_remote = v5.get("workplace_type") == "Remote"
        if scraper_input.is_remote and not is_remote:
            return None

        job_type = None
        commitment = v5.get("commitment") or []
        if commitment:
            try:
                job_type = [get_enum_from_value(commitment[0].lower().replace(" ", ""))]
            except Exception:
                job_type = None

        location = self._parse_location(v5, self._preferred_country_code)

        compensation = None
        min_amount = v5.get("yearly_min_compensation")
        max_amount = v5.get("yearly_max_compensation")
        if min_amount and max_amount:
            interval = None
            try:
                interval = CompensationInterval(v5.get("listed_compensation_frequency", "").lower())
            except ValueError:
                interval = CompensationInterval.YEARLY
            compensation = Compensation(
                interval=interval,
                min_amount=min_amount,
                max_amount=max_amount,
                currency=v5.get("listed_compensation_currency", "USD"),
            )

        publish_dt = None
        publish_millis = v5.get("estimated_publish_date_millis")
        if publish_millis:
            publish_dt = datetime.fromtimestamp(publish_millis / 1000, tz=timezone.utc)

        if scraper_input.hours_old and publish_dt:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=scraper_input.hours_old)
            if publish_dt < cutoff:
                return None
        date_posted = publish_dt.date() if publish_dt else None

        description = self._fetch_description(job_id, scraper_input.description_format)
        if not description:
            description = v5.get("requirements_summary")

        return JobPost(
            id=job_id,
            title=title,
            company_name=v5.get("company_name"),
            job_url=job_url,
            job_url_direct=job_url,
            location=location,
            description=description,
            company_url=self._normalize_company_url(v5.get("company_website")),
            job_type=job_type,
            compensation=compensation,
            date_posted=date_posted,
            is_remote=is_remote,
        )

    @staticmethod
    def _normalize_company_url(website: str | None) -> str | None:
        if not website:
            return None
        return website if website.startswith("http") else f"https://{website}"

    @staticmethod
    def _parse_location(v5: dict, preferred_country: str | None = None) -> Location | None:
        # Builds the *display* Location for a result row from its own
        # workplace_* fields. Search-by-location (the query-side filter) is
        # handled separately by _resolve_location, via hiring.cafe's
        # /api/searchLocation geocoder. Jobs can list multiple eligible
        # countries (e.g. ["US", "CA"]) — when the caller searched a
        # specific country, prefer showing that one instead of whichever
        # happens to be listed first.
        cities = v5.get("workplace_cities") or []
        countries = v5.get("workplace_countries") or []
        if not cities and not countries:
            return None

        chosen_city = cities[0] if cities else None
        if preferred_country and cities:
            match = next(
                (c for c in cities if c.split(",")[-1].strip().upper() == preferred_country.upper()),
                None,
            )
            if match:
                chosen_city = match

        city = state = country = None
        if chosen_city:
            parts = [p.strip() for p in chosen_city.split(",")]
            if len(parts) >= 3:
                city, state, country = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                city, country = parts[0], parts[1]
            else:
                city = parts[0]
        elif countries:
            country = preferred_country if preferred_country in countries else countries[0]

        country_value: Country | str | None = None
        if country:
            try:
                country_value = Country.from_string(country)
            except ValueError:
                country_value = country

        return Location(city=city, state=state, country=country_value)


def _demo():
    sample_hit = {
        "id": "ashby___hiive___ef18ebc7",
        "apply_url": "https://jobs.ashbyhq.com/hiive/ef18ebc7",
        "job_information": {"title": "Developer Experience Engineer"},
        "v5_processed_job_data": {
            "core_job_title": "Developer Experience Engineer",
            "company_name": "Hiive",
            "company_website": "hiive.com",
            "workplace_type": "Hybrid",
            "commitment": ["Full Time"],
            "workplace_cities": ["Vancouver, British Columbia, CA"],
            "yearly_min_compensation": 160000,
            "yearly_max_compensation": 220000,
            "listed_compensation_currency": "CAD",
            "listed_compensation_frequency": "Yearly",
            "estimated_publish_date_millis": 1786465241003,
            "requirements_summary": "Strong programming ability.",
        },
    }
    scraper = HiringCafe.__new__(HiringCafe)
    scraper._preferred_country_code = None
    scraper._fetch_description = lambda job_id, fmt: None  # skip network in the self-check
    job = scraper._process_job(sample_hit, ScraperInput(site_type=[Site.HIRINGCAFE]))
    assert job is not None
    assert job.title == "Developer Experience Engineer"
    assert job.company_name == "Hiive"
    assert job.job_url == "https://jobs.ashbyhq.com/hiive/ef18ebc7"
    assert job.location.city == "Vancouver"
    assert job.location.state == "British Columbia"
    assert job.compensation.min_amount == 160000
    assert job.compensation.currency == "CAD"
    assert job.job_type == [get_enum_from_value("fulltime")]
    assert job.is_remote is False
    print("hiringcafe _process_job self-check passed")


if __name__ == "__main__":
    _demo()
