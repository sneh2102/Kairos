from __future__ import annotations

import math
import re
import time
from datetime import datetime, date as date_cls, timedelta

from jobspy.util import extract_emails_from_text, markdown_converter, create_logger
from jobspy.model import (
    JobPost, Compensation, Location, JobResponse,
    Country, DescriptionFormat, Scraper, ScraperInput, Site,
    CompensationInterval,
)
from jobspy.ziprecruiter.util import get_job_type_enum

log = create_logger("ZipRecruiter")


class ZipRecruiter(Scraper):
    base_url      = "https://www.ziprecruiter.com"
    jobs_per_page = 20

    def __init__(self, proxies=None, ca_cert=None, user_agent=None):
        super().__init__(Site.ZIP_RECRUITER, proxies=proxies)
        self.scraper_input = None
        self.seen_urls     = set()
        self.delay         = 3

    # ── public ────────────────────────────────────────────────────────────────
    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        job_list  = []
        max_pages = math.ceil(scraper_input.results_wanted / self.jobs_per_page)

        for page in range(1, max_pages + 1):
            if len(job_list) >= scraper_input.results_wanted:
                break
            log.info(f"ZipRecruiter: search page {page} / {max_pages}")
            jobs = self._scrape_page_playwright(scraper_input, page)
            if not jobs:
                log.info("ZipRecruiter: no jobs on page %d — stopping", page)
                break
            job_list.extend(jobs)
            if page < max_pages:
                time.sleep(self.delay)

        return JobResponse(jobs=job_list[: scraper_input.results_wanted])

    # ── playwright scraper ────────────────────────────────────────────────────
    def _scrape_page_playwright(self, scraper_input: ScraperInput, page: int) -> list[JobPost]:
        from playwright.sync_api import sync_playwright

        jobs     = []
        search   = scraper_input.search_term or ""
        location = scraper_input.location    or ""

        # Build search URL — ZipRecruiter supports US and Canada only
        country = scraper_input.country
        country_param = ""
        if country == Country.CANADA:
            country_param = "&country=CA"
        elif country not in (Country.USA, Country.US_CANADA, None):
            # ZipRecruiter only serves US/CA — for other countries return empty
            log.warning("ZipRecruiter only supports US/Canada. Skipping location: %s", location)
            return []

        url = (
            f"{self.base_url}/jobs-search"
            f"?search={search.replace(' ', '+')}"
            f"&location={location.replace(' ', '+')}"
            f"{country_param}"
        )
        if scraper_input.hours_old:
            days = max(1, math.ceil(scraper_input.hours_old / 24))
            url += f"&days={days}"
        if scraper_input.is_remote:
            url += "&remote=true"
        if page > 1:
            url += f"&page={page}"

        try:
            with sync_playwright() as p:
                # headless=False lets Cloudflare see a real visible browser,
                # bypassing the "Just a moment…" JS challenge that blocks headless mode
                browser = p.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-infobars",
                        "--window-position=0,0",
                        "--ignore-certificate-errors",
                    ],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                    timezone_id="America/Toronto",
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                web_page = context.new_page()

                log.info(f"ZipRecruiter: loading {url}")
                web_page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Wait for Cloudflare JS challenge to clear — polls until title changes
                try:
                    web_page.wait_for_function(
                        "document.title && document.title !== 'Just a moment...'",
                        timeout=20000,
                    )
                except Exception:
                    pass
                web_page.wait_for_timeout(2000)

                log.info(f"ZipRecruiter: page title = '{web_page.title()}'")

                # ── Save debug artifacts on first page ────────────────
                if page == 1:
                    try:
                        web_page.screenshot(path="ziprecruiter_debug.png")
                    except Exception:
                        pass

                # ── Strategy 1: article-based extraction with full field scraping ─
                # ZipRecruiter job results are <article> elements; each has a
                # /co/ link (company page + uuid identifying the job).
                raw_cards = web_page.evaluate("""
                    () => {
                        const cards = [];
                        const seen  = new Set();

                        const getText = (el, ...selectors) => {
                            for (const sel of selectors) {
                                const found = el.querySelector(sel);
                                if (found) {
                                    const t = (found.innerText || found.textContent || '').trim();
                                    if (t) return t;
                                }
                            }
                            return null;
                        };

                        document.querySelectorAll('article').forEach(article => {
                            try {
                                // Job link — ZipRecruiter uses /co/CompanyName/Jobs/-in-City?uuid=
                                const a = article.querySelector('a[href*="/co/"]') ||
                                          article.querySelector('a[href*="/jobs/"]') ||
                                          article.querySelector('a');
                                if (!a) return;

                                const href = a.href || '';
                                if (!href.includes('ziprecruiter.com')) return;
                                if (seen.has(href)) return;
                                seen.add(href);

                                // Title — ZipRecruiter wraps it in h2 inside the article
                                const title = getText(article,
                                    'h2', 'h3', 'h4',
                                    '[class*="title"]',
                                    '[data-testid*="title"]',
                                    '.job_title'
                                ) || a.innerText.trim() || null;

                                // Company — shown in a <p> or span after the title
                                const company = getText(article,
                                    '[class*="company"]',
                                    '[class*="employer"]',
                                    '[data-testid*="company"]',
                                    'p[class*="name"]'
                                );

                                // Location
                                const location = getText(article,
                                    '[class*="location"]',
                                    '[data-testid*="location"]',
                                    '[class*="city"]'
                                );

                                // Salary
                                const salary = getText(article,
                                    '[class*="salary"]',
                                    '[class*="pay"]',
                                    '[data-testid*="salary"]'
                                );

                                // Date
                                const date = getText(article,
                                    'time', '[class*="date"]',
                                    '[data-testid*="date"]', '[datetime]'
                                );

                                cards.push({
                                    url:      href,
                                    title:    title,
                                    company:  company,
                                    location: location,
                                    salary:   salary,
                                    date:     date,
                                });
                            } catch(e) {}
                        });

                        return cards;
                    }
                """)

                log.info(f"ZipRecruiter: Strategy 1 found {len(raw_cards)} cards")

                # ── Strategy 2: fallback — any ZipRecruiter link with uuid ──
                if not raw_cards:
                    log.warning("Strategy 1 failed — trying uuid-link fallback")
                    raw_cards = web_page.evaluate("""
                        () => {
                            const cards = [];
                            const seen  = new Set();
                            document.querySelectorAll('a[href*="uuid"]').forEach(a => {
                                try {
                                    const href = a.href || '';
                                    if (!href.includes('ziprecruiter.com')) return;
                                    if (seen.has(href)) return;
                                    seen.add(href);
                                    cards.push({
                                        url:      href,
                                        title:    a.innerText.trim() || null,
                                        company:  null,
                                        location: null,
                                        salary:   null,
                                        date:     null,
                                    });
                                } catch(e) {}
                            });
                            return cards;
                        }
                    """)
                    log.info(f"ZipRecruiter: Strategy 2 found {len(raw_cards)} cards")

                # ── Strategy 3: JSON-LD structured data ───────────────
                if not raw_cards:
                    log.warning("Strategy 2 failed — trying JSON-LD")
                    raw_cards = web_page.evaluate("""
                        () => {
                            const jobs = [];
                            document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                                try {
                                    const d     = JSON.parse(s.textContent);
                                    const items = d['@graph'] || (Array.isArray(d) ? d : [d]);
                                    items.forEach(item => {
                                        if (item['@type'] === 'JobPosting') {
                                            jobs.push({
                                                title:    item.title           || null,
                                                company:  item.hiringOrganization?.name || null,
                                                location: item.jobLocation?.address?.addressLocality || null,
                                                url:      item.url             || null,
                                                salary:   null,
                                                date:     item.datePosted      || null,
                                            });
                                        }
                                    });
                                } catch(e) {}
                            });
                            return jobs;
                        }
                    """)
                    log.info(f"ZipRecruiter: Strategy 3 (JSON-LD) found {len(raw_cards)} jobs")

                # ── Strategy 4: log all hrefs for debugging ───────────
                if not raw_cards:
                    log.warning("All strategies failed — logging sample hrefs for debug")
                    sample = web_page.evaluate("""
                        () => [...document.querySelectorAll('a')]
                              .map(a => a.href)
                              .filter(h => h && h.includes('ziprecruiter'))
                              .slice(0, 10)
                    """)
                    log.info("Sample hrefs on page: %s", sample)

                # Parse cards first (without descriptions)
                raw_jobs = []
                for card in raw_cards:
                    job = self._parse_card(card)
                    if job:
                        raw_jobs.append(job)

                # Only fetch descriptions for as many jobs as actually needed
                needed = scraper_input.results_wanted - len(jobs)
                raw_jobs = raw_jobs[:max(needed, 0)]

                # Fetch descriptions sequentially in the same thread — Playwright
                # sync API is not thread-safe so ThreadPoolExecutor cannot be used.
                # The same browser context already passed Cloudflare.
                log.info(f"ZipRecruiter: fetching descriptions for {len(raw_jobs)} jobs...")
                url_to_desc: dict[str, str | None] = {}

                for job in raw_jobs:
                    pg = context.new_page()
                    try:
                        # Step 1: load the /co/ company page (already Cloudflare-cleared)
                        pg.goto(job.job_url, wait_until="domcontentloaded", timeout=20000)
                        pg.wait_for_timeout(2000)

                        # Step 2: find the /c/?jid= detail link for this specific job
                        # by matching the article title against our job title
                        title_key = (job.title or "")[:30]
                        detail_url = pg.evaluate(f"""
                            () => {{
                                const titleKey = {repr(title_key)}.toLowerCase();
                                // Try to find the article whose heading contains our title
                                for (const article of document.querySelectorAll('article')) {{
                                    const heading = article.querySelector('h2,h3,h4,[class*="title"]');
                                    if (heading && heading.innerText.toLowerCase().includes(titleKey)) {{
                                        const link = article.querySelector('a[href*="/c/"][href*="jid="]');
                                        if (link) return link.href;
                                    }}
                                }}
                                // Fallback: first /c/?jid= link on the page
                                const fallback = document.querySelector('a[href*="/c/"][href*="jid="]');
                                return fallback ? fallback.href : null;
                            }}
                        """)

                        desc = None
                        if detail_url:
                            # Step 3: navigate to the real job detail page
                            pg.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
                            pg.wait_for_timeout(1500)
                            desc = pg.evaluate("""
                                () => {
                                    // ── Helper: does this text look like real prose? ──────────
                                    // Rejects "Similar Job Titles" lists (many short lines, no
                                    // sentences) and login-wall text.
                                    const isProse = (t) => {
                                        if (!t || t.length < 150) return false;
                                        const lines = t.split('\\n').filter(l => l.trim().length > 0);
                                        if (lines.length === 0) return false;
                                        const avgLen = t.length / lines.length;
                                        // Title lists have very short lines (< 35 chars avg)
                                        if (avgLen < 35) return false;
                                        // Login walls contain these phrases
                                        if (/sign in|create an account|join now|log in to/i.test(t.substring(0, 300))) return false;
                                        return true;
                                    };

                                    // ── 1. JSON-LD structured data (most reliable) ────────────
                                    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                                        try {
                                            const d = JSON.parse(s.textContent);
                                            const items = Array.isArray(d) ? d : [d];
                                            for (const item of items) {
                                                const raw = item.description || '';
                                                // Strip HTML tags from JSON-LD description
                                                const stripped = raw.replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ').trim();
                                                if (isProse(stripped)) return stripped;
                                            }
                                        } catch(e) {}
                                    }

                                    // ── 2. Named description containers ──────────────────────
                                    const named = [
                                        '[class*="jobDescription"]', '[class*="job_description"]',
                                        '[class*="jobDesc"]',        '[id*="jobDesc"]',
                                        '[data-testid="job-description"]',
                                        'section[class*="description"]',
                                        'div[class*="description"]',
                                        '[class*="job-detail"]',     '[class*="jobDetail"]',
                                    ];
                                    for (const sel of named) {
                                        const el = document.querySelector(sel);
                                        if (el) {
                                            const t = (el.innerText || '').trim();
                                            if (isProse(t)) return t;
                                        }
                                    }

                                    // ── 3. Collect p / ul / li prose blocks (ZipRecruiter uses
                                    //       bare Tailwind elements with no semantic class names)
                                    const skipParentSel = [
                                        '[class*="share"]', '[class*="social"]', '[class*="similar"]',
                                        '[class*="recommend"]', 'nav', 'header', 'footer',
                                        '[class*="cookie"]', '[class*="banner"]',
                                    ].join(',');

                                    const seen = new Set();
                                    const blocks = [];
                                    document.querySelectorAll('p, ul, li').forEach(el => {
                                        // Skip if inside chrome UI areas
                                        for (const sel of skipParentSel.split(',')) {
                                            if (el.closest(sel.trim())) return;
                                        }
                                        // Only leaf-ish elements (not containers of other p/ul)
                                        if (el.tagName === 'UL' && el.querySelector('ul')) return;
                                        const t = (el.innerText || '').trim();
                                        if (t.length < 20 || seen.has(t)) return;
                                        seen.add(t);
                                        blocks.push(t);
                                    });

                                    if (blocks.length > 0) {
                                        const joined = blocks.join('\\n');
                                        if (isProse(joined)) return joined;
                                    }

                                    // ── 4. Last resort: largest single prose block ────────────
                                    let best = null;
                                    document.querySelectorAll('div, section').forEach(el => {
                                        if (el.children.length > 20) return;
                                        const cls = (el.className || '').toLowerCase();
                                        if (/similar|recommend|header|nav|footer|sidebar|cookie|share|social/i.test(cls)) return;
                                        const t = (el.innerText || '').trim();
                                        if (isProse(t) && t.length > (best ? best.length : 300)) best = t;
                                    });
                                    return best;
                                }
                            """)
                            # Update the stored job URL to the canonical /c/ URL
                            if detail_url not in self.seen_urls:
                                job.job_url = detail_url

                        url_to_desc[job.job_url] = desc
                        log.info("ZipRecruiter desc: %s -> %d chars", job.title, len(desc) if desc else 0)
                    except Exception as e:
                        log.warning("ZipRecruiter desc fetch error for %s: %s", job.job_url, e)
                        url_to_desc[job.job_url] = None
                    finally:
                        try:
                            pg.close()
                        except Exception:
                            pass

                browser.close()

                for job in raw_jobs:
                    desc = url_to_desc.get(job.job_url)
                    if desc:
                        if (self.scraper_input and
                                self.scraper_input.description_format == DescriptionFormat.MARKDOWN):
                            desc = markdown_converter(desc)
                        job.description = desc
                        job.emails = extract_emails_from_text(desc)
                    jobs.append(job)

        except Exception as e:
            log.error(f"ZipRecruiter Playwright error: {e}")

        return jobs

    # ── card parser ───────────────────────────────────────────────────────────
    def _parse_card(self, card: dict) -> JobPost | None:
        try:
            job_url = (card.get("url") or "").strip()
            if not job_url:
                return None

            # Clean up URL — remove tracking params but keep the path
            # Real ZipRecruiter job URLs look like:
            # https://www.ziprecruiter.com/jobs/Company-Name/Job-Title/hash
            # https://www.ziprecruiter.com/k/l/search?...  ← search pages, skip
            if any(x in job_url for x in [
                "/jobs-search", "/candidate/", "/login",
                "/signup", "/privacy", "/terms", "?search=",
            ]):
                return None

            # Strip UTM/tracking params
            if "?" in job_url:
                base = job_url.split("?")[0]
                # Keep only if it's a job detail page
                if "/jobs/" in base or "/k/" in base:
                    job_url = base
                # Otherwise keep full URL
                else:
                    job_url = job_url

            if job_url in self.seen_urls:
                return None
            self.seen_urls.add(job_url)

            title   = (card.get("title") or "N/A").strip()
            company = card.get("company")
            loc_str = (card.get("location") or "").strip()

            # Parse location
            city = state = None
            if "," in loc_str:
                parts = [p.strip() for p in loc_str.split(",")]
                city  = parts[0]
                state = parts[1] if len(parts) > 1 else None
            elif loc_str:
                city = loc_str

            # Detect country — fall back to the scraper's configured country when
            # the location string doesn't carry province/country signals
            country_enum = Country.USA
            ca_indicators = [
                "Canada", ",ON", ", ON", ",BC", ", BC", ",AB", ", AB",
                ",QC", ", QC", ",NS", ", NS", ",NB", ", NB", ",MB", ", MB",
                ",SK", ", SK", ",PE", ", PE", ",NL", ", NL", ",NT", ", NT",
                ",YT", ", YT", ",NU", ", NU",
            ]
            if any(x in loc_str for x in ca_indicators):
                country_enum = Country.CANADA
            elif self.scraper_input and self.scraper_input.country in (
                Country.CANADA, Country.US_CANADA
            ):
                country_enum = Country.CANADA

            # Parse date
            date_posted = None
            raw_date    = card.get("date")
            if raw_date:
                for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y"):
                    try:
                        date_posted = datetime.strptime(raw_date[:10], fmt[:10]).date()
                        break
                    except Exception:
                        continue

            # Post-filter: drop jobs older than hours_old (safety net — the &days= URL
            # param already filters server-side but can be imprecise by a few hours)
            if date_posted and self.scraper_input and self.scraper_input.hours_old:
                cutoff = date_cls.today() - timedelta(hours=self.scraper_input.hours_old)
                if date_posted < cutoff:
                    return None

            is_remote = (
                "remote" in loc_str.lower() or
                "remote" in title.lower()
            )

            return JobPost(
                id=f"zr-{abs(hash(job_url))}",
                title=title,
                company_name=company,
                location=Location(city=city, state=state, country=country_enum),
                job_url=job_url,
                date_posted=date_posted,
                compensation=self._parse_salary(card.get("salary")),
                is_remote=is_remote,
            )

        except Exception as e:
            log.warning(f"ZipRecruiter card parse error: {e}")
            return None

    # ── salary parser ─────────────────────────────────────────────────────────
    @staticmethod
    def _parse_salary(salary_str: str | None) -> Compensation | None:
        if not salary_str:
            return None
        try:
            nums = re.findall(r"[\d,]+", salary_str)
            if len(nums) < 2:
                return None
            mn = int(nums[0].replace(",", ""))
            mx = int(nums[1].replace(",", ""))
            if salary_str.lower().count("hour") > 0:
                interval = CompensationInterval.HOURLY
            elif salary_str.lower().count("month") > 0:
                interval = CompensationInterval.MONTHLY
            elif salary_str.lower().count("week") > 0:
                interval = CompensationInterval.WEEKLY
            else:
                interval = CompensationInterval.YEARLY
            return Compensation(
                interval=interval, min_amount=mn, max_amount=mx, currency="USD"
            )
        except Exception:
            return None