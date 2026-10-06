from __future__ import annotations

import html
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
from jobspy.util import create_logger, create_session, markdown_converter, plain_converter

log = create_logger("Greenhouse")


class Greenhouse(Scraper):
    """Scrapes my.greenhouse.io's cross-company job search — the personal,
    login-gated search Greenhouse gives job seekers across every company
    that hosts its board on Greenhouse. Unlike a single company's public
    board (boards-api.greenhouse.io, used here only for descriptions), this
    search has no anonymous API: it requires a real logged-in session,
    supplied via ScraperInput.greenhouse_cookie (the browser's Cookie header).
    """

    base_url = "https://my.greenhouse.io"
    boards_api_url = "https://boards-api.greenhouse.io/v1/boards"
    geocode_url = "https://api-geocode-earth-proxy.greenhouse.io/v1/autocomplete"
    geocode_api_key = "ge-39f1178289d5d0c5"  # public client key, embedded in every my.greenhouse.io page load

    # Only date_posted buckets confirmed from the app's own UI; anything
    # longer is left unfiltered server-side and relies on the client-side
    # cutoff in _process_job instead.
    _DATE_POSTED_BUCKETS = [
        (24, "past_day"),
        (72, "past_three_days"),
        (120, "past_five_days"),
        (240, "past_ten_days"),
        (720, "past_month"),
    ]

    _version_cache: str | None = None
    _version_cached_at: float = 0
    _VERSION_TTL = 1800  # seconds
    _location_cache: dict = {}

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        super().__init__(Site.GREENHOUSE, proxies=proxies, ca_cert=ca_cert)
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        if not scraper_input.greenhouse_cookie:
            log.error(
                "Greenhouse: no greenhouse_cookie configured — log into my.greenhouse.io in a browser, "
                "copy the Cookie request header from a /jobs/search call, and set it in config"
            )
            return JobResponse(jobs=[])

        self.session = create_session(proxies=self.proxies, ca_cert=self.ca_cert, is_tls=True)
        self.session.headers.update(
            {"accept": "text/html, application/xhtml+xml", "x-requested-with": "XMLHttpRequest"}
        )
        for pair in scraper_input.greenhouse_cookie.split(";"):
            name, _, value = pair.strip().partition("=")
            if name and value:
                self.session.cookies.set(name, value, domain="my.greenhouse.io")

        location_params = self._resolve_location(scraper_input.location) if scraper_input.location else {}
        date_posted = self._date_posted_bucket(scraper_input.hours_old)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=scraper_input.hours_old)
            if scraper_input.hours_old
            else None
        )
        results_wanted = scraper_input.results_wanted or 15

        job_list: list[JobPost] = []
        seen_ids: set[str] = set()
        page = 1
        max_pages = 25  # ponytail: hard cap in case moreResultsAvailable never flips
        while len(job_list) < results_wanted and page <= max_pages:
            params = {"query": scraper_input.search_term or "", "page": page, **location_params}
            if date_posted:
                params["date_posted"] = date_posted
            result = self._fetch_page(params)
            if not result:
                break
            hits, more_available = result

            for hit in hits:
                job_post = self._process_job(hit, cutoff, scraper_input.description_format)
                if job_post and job_post.id not in seen_ids:
                    seen_ids.add(job_post.id)
                    job_list.append(job_post)
                    if len(job_list) >= results_wanted:
                        break
            if not more_available or not hits:
                break
            page += 1

        return JobResponse(jobs=job_list[:results_wanted])

    def _get_version(self, force: bool = False) -> str | None:
        now = time.time()
        if not force and Greenhouse._version_cache and now - Greenhouse._version_cached_at < Greenhouse._VERSION_TTL:
            return Greenhouse._version_cache

        # Greenhouse redirects a bare /jobs/search to the user's last-run
        # search — tls_client doesn't follow redirects unless told to.
        resp = self.session.get(f"{self.base_url}/jobs/search", allow_redirects=True)
        if not resp.ok:
            log.error(f"Greenhouse: could not load search page - status {resp.status_code}")
            return None
        if "/users/sign_in" in resp.url:
            log.error("Greenhouse: not logged in - greenhouse_cookie is missing or expired")
            return None
        match = re.search(r"&quot;version&quot;:&quot;(.*?)&quot;", resp.text)
        version = match.group(1) if match else None
        if version:
            Greenhouse._version_cache = version
            Greenhouse._version_cached_at = now
        return version

    def _csrf_token(self) -> str | None:
        return self.session.cookies.get("MYGREENHOUSE-XSRF-TOKEN")

    def _fetch_page(self, params: dict) -> tuple[list, bool] | None:
        version = self._get_version()
        if not version:
            return None

        headers = {
            "x-inertia": "true",
            "x-inertia-partial-component": "jobs",
            "x-inertia-partial-data": "jobPosts,moreResultsAvailable,page",
            "x-inertia-version": version,
            "x-csrf-token": self._csrf_token(),
        }
        resp = self.session.get(f"{self.base_url}/jobs/search", params=params, headers=headers, allow_redirects=True)
        if resp.status_code == 409:
            # Inertia asset version went stale between our cached copy and the server — the
            # protocol's own signal to refetch it and retry the request once.
            version = self._get_version(force=True)
            if not version:
                return None
            headers["x-inertia-version"] = version
            headers["x-csrf-token"] = self._csrf_token()
            resp = self.session.get(f"{self.base_url}/jobs/search", params=params, headers=headers, allow_redirects=True)

        if "/users/sign_in" in resp.url:
            log.error("Greenhouse: session expired - refresh greenhouse_cookie from a logged-in browser")
            return None
        if not resp.ok:
            log.error(f"Greenhouse: search request failed - status {resp.status_code}")
            return None
        try:
            props = resp.json().get("props", {})
            return props.get("jobPosts", []), bool(props.get("moreResultsAvailable"))
        except Exception as e:
            log.error(f"Greenhouse: error parsing search response - {str(e)}")
            return None

    def _resolve_location(self, location: str) -> dict:
        cached = Greenhouse._location_cache.get(location)
        if cached is not None:
            return cached or {}

        params = {}
        try:
            resp = self.session.get(
                self.geocode_url,
                params={"api_key": self.geocode_api_key, "text": location, "layers": "locality,region,country", "size": 1},
                allow_redirects=True,
            )
            features = resp.json().get("features", []) if resp.ok else []
        except Exception as e:
            log.error(f"Greenhouse: geocode request failed for '{location}' - {str(e)}")
            features = []

        if features:
            props_ = features[0]["properties"]
            lon, lat = features[0]["geometry"]["coordinates"]
            params = {"location": location, "lat": lat, "lon": lon, "location_type": props_.get("layer")}
            if props_.get("country_code"):
                params["country_short_name"] = props_["country_code"]
            if props_.get("region_a"):
                params["state_short_name"] = props_["region_a"]
        else:
            log.warning(f"Greenhouse: could not resolve location '{location}', searching without a location filter")

        Greenhouse._location_cache[location] = params or False
        return params

    def _fetch_description(self, url_token: str | None, job_id, description_format: DescriptionFormat) -> str | None:
        if not url_token or not job_id:
            return None
        try:
            resp = self.session.get(f"{self.boards_api_url}/{url_token}/jobs/{job_id}", allow_redirects=True)
        except Exception as e:
            log.error(f"Greenhouse: description request failed for {job_id} - {str(e)}")
            return None
        if not resp.ok:
            return None
        try:
            content = resp.json().get("content")
        except Exception as e:
            log.error(f"Greenhouse: error parsing description for {job_id} - {str(e)}")
            return None
        if not content:
            return None
        # boards-api returns the content double HTML-encoded (literal "&lt;p&gt;"
        # text, not real tags) — one unescape gets back real markup to convert.
        content = html.unescape(content)
        if description_format == DescriptionFormat.MARKDOWN:
            return markdown_converter(content)
        if description_format == DescriptionFormat.PLAIN:
            return plain_converter(content)
        return content

    def _process_job(
        self, hit: dict, cutoff: datetime | None, description_format: DescriptionFormat
    ) -> JobPost | None:
        job_id = hit.get("id")
        title = hit.get("title")
        job_url = hit.get("publicUrl")
        if not job_id or not title or not job_url:
            return None

        publish_dt = None
        first_published = hit.get("firstPublished")
        if first_published:
            try:
                publish_dt = datetime.fromisoformat(first_published.replace("Z", "+00:00"))
            except ValueError:
                publish_dt = None
        if cutoff and publish_dt and publish_dt < cutoff:
            return None

        description = self._fetch_description(hit.get("urlToken"), job_id, description_format)

        return JobPost(
            id=str(job_id),
            title=title,
            company_name=hit.get("companyName"),
            job_url=job_url,
            job_url_direct=job_url,
            location=self._parse_location(hit.get("locations") or []),
            description=description or hit.get("summary"),
            compensation=self._parse_compensation(hit.get("payRanges")),
            date_posted=publish_dt.date() if publish_dt else None,
            is_remote=hit.get("workType") == "remote",
        )

    @staticmethod
    def _parse_location(locations: list[str]) -> Location | None:
        if not locations:
            return None
        parts = [p.strip() for p in locations[0].split(",")]
        city = state = country = None
        if len(parts) >= 3:
            city, state, country = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            city, state = parts[0], parts[1]
        else:
            country = parts[0]

        country_value: Country | str | None = None
        if country:
            try:
                country_value = Country.from_string(country)
            except ValueError:
                country_value = country
        return Location(city=city, state=state, country=country_value)

    @staticmethod
    def _parse_compensation(pay_range: str | None) -> Compensation | None:
        if not pay_range:
            return None
        numbers = re.findall(r"[\d,]+(?:\.\d+)?", pay_range)
        if len(numbers) < 2:
            return None
        currency = "CAD" if "CA$" in pay_range or "C$" in pay_range else "USD"
        return Compensation(
            interval=CompensationInterval.YEARLY,
            min_amount=float(numbers[0].replace(",", "")),
            max_amount=float(numbers[1].replace(",", "")),
            currency=currency,
        )

    @classmethod
    def _date_posted_bucket(cls, hours_old: int | None) -> str | None:
        if not hours_old:
            return None
        for max_hours, bucket in cls._DATE_POSTED_BUCKETS:
            if hours_old <= max_hours:
                return bucket
        return None


def _demo():
    sample_hit = {
        "id": 4717460006,
        "title": "206436 - Developer",
        "companyName": "Orion Innovation",
        "publicUrl": "https://www.orioninc.com/careers/job/?gh_jid=4717460006",
        "urlToken": "orioninnovation",
        "firstPublished": "2026-09-29T15:37:19Z",
        "locations": ["Mississauga, ON"],
        "workType": "hybrid",
        "payRanges": "$170,000 - $231,000",
        "summary": None,
    }
    scraper = Greenhouse.__new__(Greenhouse)
    scraper._fetch_description = lambda url_token, job_id, fmt: None  # skip network in the self-check
    job = scraper._process_job(sample_hit, None, DescriptionFormat.MARKDOWN)
    assert job is not None
    assert job.id == "4717460006"
    assert job.title == "206436 - Developer"
    assert job.company_name == "Orion Innovation"
    assert job.location.city == "Mississauga"
    assert job.location.state == "ON"
    assert job.compensation.min_amount == 170000
    assert job.compensation.max_amount == 231000
    assert job.is_remote is False

    assert Greenhouse._date_posted_bucket(12) == "past_day"
    assert Greenhouse._date_posted_bucket(96) == "past_five_days"
    assert Greenhouse._date_posted_bucket(10000) is None
    assert Greenhouse._date_posted_bucket(None) is None

    cutoff_job = Greenhouse._process_job(
        scraper, sample_hit, datetime.now(timezone.utc) + timedelta(days=1), DescriptionFormat.MARKDOWN
    )
    assert cutoff_job is None  # firstPublished is before the (future) cutoff

    print("greenhouse _process_job / _date_posted_bucket self-check passed")


if __name__ == "__main__":
    _demo()
