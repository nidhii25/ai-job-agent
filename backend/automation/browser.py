"""Playwright browser lifecycle for application runs."""

import os
from contextlib import contextmanager

from playwright.sync_api import sync_playwright


def env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@contextmanager
def open_browser_page():
    """Open a persistent browser profile, yield a page, and always close it.

    A persistent profile lets the user sign in manually once (including any
    email/OTP step). The agent never reads or automates the code. Visible mode
    is the default so the user can watch the agent work and complete manual
    verification when needed.
    """
    headless = env_bool("BROWSER_HEADLESS", False)
    slow_mo = env_int("BROWSER_SLOW_MO_MS", 0)
    close_delay = env_int("BROWSER_CLOSE_DELAY_SECONDS", 5)
    timeout = env_int("BROWSER_TIMEOUT_MS", 15000)
    profile_dir = os.getenv(
        "BROWSER_PROFILE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "browser_profile"),
    )
    os.makedirs(profile_dir, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            slow_mo=slow_mo,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(timeout)
        page.set_default_navigation_timeout(env_int("NAVIGATION_TIMEOUT_MS", 30000))
        try:
            yield page
        finally:
            # Leave the final page on screen briefly for observation.
            if close_delay > 0 and not page.is_closed():
                try:
                    page.wait_for_timeout(close_delay * 1000)
                except Exception:
                    pass
            try:
                context.close()
            except Exception:
                pass
