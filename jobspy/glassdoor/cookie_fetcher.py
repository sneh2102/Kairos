from playwright.sync_api import sync_playwright
import re
import json

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def get_glassdoor_location(location_term: str) -> tuple[int | None, str | None]:
    """Uses Playwright to call the location API from inside a real browser."""
    result = {"id": None, "type": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Intercept the location API response
        def handle_response(response):
            if "findPopularLocationAjax" in response.url:
                try:
                    data = response.json()
                    if data:
                        raw_type = data[0]["locationType"]
                        result["id"]   = data[0]["locationId"]
                        result["type"] = {"C": "CITY", "S": "STATE", "N": "COUNTRY"}.get(raw_type, raw_type)
                        print(f"  [Playwright] OK Location: id={result['id']}, type={result['type']}, name={data[0].get('locationName','?')}")
                except Exception as e:
                    print(f"  [Playwright] Location parse error: {e}")

        page.on("response", handle_response)

        # Load Glassdoor homepage first (gets cf_clearance)
        page.goto("https://www.glassdoor.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Now call the location API via fetch() from inside the browser
        page.evaluate(f"""
            fetch('/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={location_term}', {{
                headers: {{ 'accept': 'application/json' }}
            }})
        """)
        page.wait_for_timeout(3000)
        browser.close()

    return result["id"], result["type"]


def get_glassdoor_cookies_and_token() -> tuple[dict, str | None, str]:
    cookies_dict = {}
    token = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-US")
        page = context.new_page()

        print("  [Playwright] Loading Glassdoor homepage...")
        page.goto("https://www.glassdoor.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        print("  [Playwright] Loading jobs page for CSRF token...")
        page.goto("https://www.glassdoor.com/Job/computer-science-jobs.htm", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        html = page.content()
        matches = re.findall(r'"token":\s*"([^"]+)"', html)
        if matches:
            token = matches[0]
            print(f"  [Playwright] OK CSRF token: {token[:40]}...")
        else:
            print("  [Playwright] NO CSRF token found, will use fallback")

        cookies = context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in cookies}
        print(f"  [Playwright] Got {len(cookies_dict)} cookies")
        browser.close()

    return cookies_dict, token, USER_AGENT