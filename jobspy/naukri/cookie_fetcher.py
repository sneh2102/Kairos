from playwright.sync_api import sync_playwright
import json as _json
import re as _re


def get_naukri_headers() -> tuple[dict, dict, dict, str]:
    """
    Returns (headers, job_descriptions, cookies, captured_sid).

    - headers:          request headers including nkparam token
    - job_descriptions: {job_id: html} pre-cached from browser clicks
    - cookies:          {name: value} all browser cookies (required for requests session)
    - captured_sid:     sid from a real job-detail URL (may be empty)

    WHY cookies matter:
        Naukri validates nkparam against the browser session cookies server-side.
        Copying just the headers into requests doesn't work — you must also copy
        the cookies into the requests session's cookie jar.
    """
    search_headers   = {}
    nkparam_headers  = {}
    job_descriptions = {}
    captured_urls    = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        # ── Monitor ALL pages/tabs (Naukri opens jobs in new tab) ────────
        def on_request(request):
            url  = request.url
            hdrs = dict(request.headers)
            if "jobapi/v3/search" in url or "jobapi/v4/search" in url:
                search_headers.update(hdrs)
                print(f"[+] Captured API request to: {url}")
            elif "jobapi" in url and "/job/" in url:
                nkparam_headers.update(hdrs)
                captured_urls.append(url)
                print(f"[+] Captured job detail request (nkparam={'nkparam' in hdrs}): {url[:90]}")

        def on_response(response):
            url = response.url
            if "jobapi" not in url or "/job/" not in url:
                return
            try:
                text = response.text()
                data = _json.loads(text)
                # Confirmed key: data["jobDetails"]["description"]
                desc = (
                    data.get("jobDetails", {}).get("description") or
                    data.get("jobDetails", {}).get("jobDescription") or ""
                )
                job_id = url.split("/job/")[1].split("?")[0].strip("/")
                if desc and len(desc) > 100:
                    job_descriptions[job_id] = desc
                    print(f"[+] Pre-cached description for job {job_id} ({len(desc)} chars)")
            except Exception:
                pass

        context.on("request",  on_request)
        context.on("response", on_response)

        page = context.new_page()
        page.goto(
            "https://www.naukri.com/software-engineer-jobs",
            wait_until="networkidle",
            timeout=40000,
        )
        page.wait_for_timeout(2000)

        # Click 1-2 jobs to capture nkparam token + pre-cache descriptions
        print("[*] Clicking job listings to capture nkparam + cookies...")
        for sel in [
            ".srp-jobtuple-wrapper a.title",
            "article.jobTuple a.title",
            '[class*="jobTuple"] a[title]',
            'a[href*="job-listings"]',
        ]:
            els = page.query_selector_all(sel)
            clicked = 0
            for el in els[:3]:
                try:
                    el.click()
                    page.wait_for_timeout(4000)
                    clicked += 1
                    print(f"[+] Clicked job {clicked} via: {sel}")
                    if clicked >= 2:
                        break
                except Exception:
                    pass
            if clicked > 0:
                break

        page.wait_for_timeout(1500)

        # Capture ALL browser cookies — required for requests session
        all_cookies  = context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in all_cookies}
        print(f"[+] Captured {len(cookies_dict)} browser cookies")

        browser.close()

    # Extract sid from a captured job-detail URL
    captured_sid = ""
    for url in captured_urls:
        m = _re.search(r'[?&]sid=(\d+)', url)
        if m:
            captured_sid = m.group(1)
            break

    # Merge: nkparam_headers has everything search_headers has + the nkparam token
    merged = {**search_headers, **nkparam_headers}
    # Remove cookie from headers — cookies go into requests session separately
    merged.pop("cookie", None)
    merged.pop("Cookie", None)

    print(
        f"[Summary] headers={len(merged)} | "
        f"nkparam={'✓' if 'nkparam' in merged else '✗'} | "
        f"cookies={len(cookies_dict)} | "
        f"pre-cached={len(job_descriptions)} | "
        f"sid={captured_sid or 'none'}"
    )
    return merged, job_descriptions, cookies_dict, captured_sid