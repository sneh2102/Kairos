"""Persisted JobRight login: the user logs in once in a visible browser and the
Playwright storage_state (cookies + localStorage) is saved to disk, then reloaded
by the headless scraper — same idea as the Greenhouse connect flow."""
import time
from pathlib import Path

LOGIN_URL = "https://jobright.ai/"
_PROBE = """async () => {
    try {
        const r = await fetch('/swan/recommend/list/jobs?refresh=false&sortCondition=0&position=0&count=1&syncRerank=false',
                              {credentials: 'include'});
        if (!r.ok) return false;
        const j = await r.json();
        return !!(j.result && j.result.jobList && j.result.jobList.length);
    } catch (e) { return false; }
}"""


def state_path() -> Path:
    import config  # lazy: repo-root module, avoids import cycles at jobspy import time
    return config.DATA_DIR / ".jobright_state.json"


def login_and_save(timeout_seconds: int = 300) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # Google blocks sign-in from Playwright's bundled Chromium ("browser may not be secure"):
        # use the real installed Chrome, drop the automation banner/flag, keep a persistent profile.
        context = p.chromium.launch_persistent_context(
            str(state_path().with_name(".jobright_browser_profile")),
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        try:
            page = context.new_page()
            page.goto(LOGIN_URL)
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                page.wait_for_timeout(3000)
                # ponytail: probing the personalised-jobs API; swap for a cookie check if it ever changes
                if page.url.startswith(LOGIN_URL) and page.evaluate(_PROBE):
                    context.storage_state(path=str(state_path()))
                    return
            raise RuntimeError("Timed out waiting for you to finish logging into JobRight")
        finally:
            context.close()
