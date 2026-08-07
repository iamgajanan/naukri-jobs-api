from playwright.sync_api import sync_playwright


class BrowserManager:
    """Playwright wrapper using an ephemeral anonymous browser context.

    No Naukri credentials, cookies, or persistent browser profile are loaded.
    Each collector run starts with a fresh browser context.
    """

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def launch(self, headless=True):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
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
