"""Captures a my.greenhouse.io session cookie via a real, visible browser —
so the user logs in once (Google OAuth, 2FA, whatever their account needs)
instead of opening DevTools and copy-pasting a Cookie header by hand.

Greenhouse itself sets a `_session_id` cookie for anonymous visitors too (it's
just Rails' session cookie), so its mere presence can't signal a completed
login — only the page navigating away from /users/sign_in (through Google's
auth flow and back) does.
"""
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SIGN_IN_URL = "https://my.greenhouse.io/users/sign_in"
SEARCH_URL = "https://my.greenhouse.io/jobs/search"


def get_greenhouse_cookie(timeout_seconds: int = 300, profile_dir: str | None = None) -> str:
    """profile_dir, if given, is a persistent Chromium profile directory —
    Google's own sign-in stays remembered there across calls, so only the
    very first connect needs a full login; later reconnects (e.g. once the
    session cookie expires) usually just bounce straight through."""
    with sync_playwright() as p:
        browser = None
        if profile_dir:
            context = p.chromium.launch_persistent_context(profile_dir, headless=False)
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
        try:
            page = context.new_page()
            page.goto(SIGN_IN_URL)

            try:
                page.wait_for_url(
                    lambda url: "my.greenhouse.io" in url and "/users/sign_in" not in url,
                    timeout=timeout_seconds * 1000,
                )
            except PlaywrightTimeoutError:
                raise RuntimeError("Timed out waiting for you to finish logging into Greenhouse")

            # Load the search page itself so the cookie jar matches exactly what
            # the scraper will send (the CSRF cookie rotates on this response).
            page.goto(SEARCH_URL)
            page.wait_for_load_state("domcontentloaded")
            if "/users/sign_in" in page.url:
                raise RuntimeError("Greenhouse login did not complete")

            cookies = context.cookies("https://my.greenhouse.io")
        finally:
            context.close()
            if browser:
                browser.close()

    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    if "_session_id" not in cookie_header:
        raise RuntimeError("No session cookie captured — try connecting again")
    return cookie_header
