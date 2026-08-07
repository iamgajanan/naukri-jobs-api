import os

from playwright.sync_api import sync_playwright


class BrowserManager:
    """Playwright wrapper using an ephemeral anonymous browser context.

    No Naukri credentials, cookies, storage state, or persistent browser profile
    are loaded. Set NAUKRI_HEADLESS=false only for local diagnostic runs where
    you want to visibly inspect the page Naukri returns.
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

        launch_options = {"headless": headless}
        executable_path = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
        if executable_path:
            launch_options["executable_path"] = executable_path

        self.browser = self.playwright.chromium.launch(**launch_options)
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.page.set_default_navigation_timeout(30000)
        return self.page

    def close(self):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
