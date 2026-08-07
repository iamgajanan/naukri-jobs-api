from pathlib import Path

from playwright.sync_api import sync_playwright


class BrowserManager:
    """Small Playwright wrapper for public Naukri search pages."""

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, profile_name="browser-data-naukri"):
        self.profile_name = profile_name
        self.playwright = None
        self.context = None
        self.page = None

    def launch(self, headless=True):
        profile = Path.cwd() / self.profile_name
        profile.mkdir(parents=True, exist_ok=True)
        self.playwright = sync_playwright().start()

        kwargs = dict(
            user_data_dir=str(profile),
            headless=headless,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="Asia/Kolkata",
            user_agent=self.USER_AGENT,
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                channel="chrome", **kwargs
            )
        except Exception:
            self.context = self.playwright.chromium.launch_persistent_context(**kwargs)

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(10000)
        self.page.set_default_navigation_timeout(30000)
        return self.page

    def close(self):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
