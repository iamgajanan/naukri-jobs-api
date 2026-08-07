import os

from playwright.sync_api import sync_playwright


class BrowserManager:
    """Playwright wrapper using an ephemeral anonymous browser context.

    The collector only needs the search-result DOM. Production therefore blocks
    heavyweight assets and uses conservative Chromium flags to reduce Railway
    memory/CPU pressure without changing the returned job data.
    """

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    @staticmethod
    def configured_headless(default=True):
        value = os.getenv("NAUKRI_HEADLESS")
        if value is None:
            return default
        return value.strip().lower() not in {"0", "false", "no", "off"}

    def launch(self, headless=None):
        if headless is None:
            headless = self.configured_headless(default=True)

        self.playwright = sync_playwright().start()
        launch_options = {
            "headless": headless,
            "args": [
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--no-first-run",
                "--no-sandbox",
            ],
        }
        executable_path = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
        if executable_path:
            launch_options["executable_path"] = executable_path

        self.browser = self.playwright.chromium.launch(**launch_options)
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="Asia/Kolkata",
            service_workers="block",
        )

        # Search cards are text/DOM driven. Images, fonts and media add network,
        # memory and decode cost but are not used by the parser.
        self.context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )

        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page.set_default_navigation_timeout(20000)
        return self.page

    def close(self):
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
