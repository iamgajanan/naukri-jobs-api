from app.services.browser import BrowserManager


def main():
    browser = BrowserManager(profile_name="browser-data-naukri")
    try:
        page = browser.launch(headless=False)
        page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=30000)
        print("Complete Naukri login/OTP/CAPTCHA manually in the opened browser.")
        input("After the Naukri home page is usable, press Enter here to save the session and close Chrome...")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
