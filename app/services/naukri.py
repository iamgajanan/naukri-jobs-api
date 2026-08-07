import asyncio
import re
from typing import List, Tuple

from app.schemas.jobs import Job, SearchQuery
from app.services.browser import BrowserManager
from app.utils.normalizers import normalize_experience, normalize_salary, normalize_work_mode

CARD_SELECTORS = [
    "div.srp-jobtuple-wrapper",
    "div.cust-job-tuple",
    "article.jobTuple",
]
TITLE_SELECTORS = ["a.title", ".title.ellipsis"]
COMPANY_SELECTORS = ["a.comp-name", ".comp-name", ".subTitle"]
LOCATION_SELECTORS = ["span.locWdth", ".loc-wrap span", ".location"]
EXPERIENCE_SELECTORS = ["span.expwdth", ".exp-wrap span", ".experience"]
SALARY_SELECTORS = ["span.sal-wrap span", ".sal", ".salary"]
POSTED_SELECTORS = ["span.job-post-day", ".job-post-day"]
DESCRIPTION_SELECTORS = ["span.job-desc", ".job-description"]


class NaukriUpstreamError(Exception):
    def __init__(self, message, status_code=None, response_preview=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_preview = response_preview


class NaukriService:
    """Browser-backed Naukri public-search scraper.

    This intentionally does not solve or bypass CAPTCHA. If Naukri presents a
    challenge/login page, the request fails explicitly instead of pretending
    that zero jobs were found.
    """

    MAX_PAGES = 6

    @staticmethod
    def _slugify(value):
        value = (value or "").strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        return value.strip("-")

    @staticmethod
    def _first_match(card, selectors):
        for selector in selectors:
            try:
                locator = card.locator(selector)
                if locator.count() > 0:
                    text = (locator.first.text_content(timeout=1000) or "").strip()
                    if text:
                        return text
            except Exception:
                continue
        return None

    @staticmethod
    def _detect_challenge(page):
        url = (page.url or "").lower()
        if "/nlogin" in url or "/login" in url:
            raise NaukriUpstreamError("Naukri requires login/session verification")
        try:
            text = ((page.title() or "") + "\n" + (page.locator("body").inner_text(timeout=1500) or "")).lower()
        except Exception:
            text = ""
        markers = ("captcha", "recaptcha", "verify you are human", "security verification", "unusual activity")
        if any(marker in text for marker in markers):
            raise NaukriUpstreamError("Naukri CAPTCHA/challenge detected")

    def _search_sync(self, query):
        browser = BrowserManager(profile_name="browser-data-naukri")
        jobs = []
        seen = set()
        try:
            page = browser.launch(headless=True)
            keyword_slug = self._slugify(query.keyword)
            location_slug = self._slugify(query.location)
            if not keyword_slug:
                raise NaukriUpstreamError("keyword is required")

            if location_slug:
                base_path = "https://www.naukri.com/{}-jobs-in-{}".format(keyword_slug, location_slug)
            else:
                base_path = "https://www.naukri.com/{}-jobs".format(keyword_slug)

            target = min(query.limit, 50)
            start_page = max(query.page, 1)
            last_page = min(start_page + self.MAX_PAGES - 1, start_page + ((target - 1) // 20))

            for page_num in range(start_page, last_page + 1):
                url = base_path if page_num == 1 else "{}-{}".format(base_path, page_num)
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response is not None and response.status >= 400:
                    raise NaukriUpstreamError(
                        "Naukri search page returned HTTP {}".format(response.status),
                        status_code=response.status,
                    )
                page.wait_for_timeout(2500)
                self._detect_challenge(page)

                cards = None
                for selector in CARD_SELECTORS:
                    candidate = page.locator(selector)
                    if candidate.count() > 0:
                        cards = candidate
                        break
                if cards is None or cards.count() == 0:
                    break

                page_new = 0
                for index in range(cards.count()):
                    if len(jobs) >= target:
                        break
                    card = cards.nth(index)
                    title = self._first_match(card, TITLE_SELECTORS)
                    if not title:
                        continue
                    company = self._first_match(card, COMPANY_SELECTORS)
                    location = self._first_match(card, LOCATION_SELECTORS) or query.location
                    experience_text = self._first_match(card, EXPERIENCE_SELECTORS)
                    salary_text = self._first_match(card, SALARY_SELECTORS)
                    posted = self._first_match(card, POSTED_SELECTORS)
                    description = self._first_match(card, DESCRIPTION_SELECTORS)

                    link = ""
                    try:
                        title_link = card.locator("a.title")
                        if title_link.count() > 0:
                            link = title_link.first.get_attribute("href", timeout=1000) or ""
                    except Exception:
                        pass
                    if not link:
                        try:
                            anchors = card.locator("a")
                            if anchors.count() > 0:
                                link = anchors.first.get_attribute("href", timeout=1000) or ""
                        except Exception:
                            pass
                    if link.startswith("/"):
                        link = "https://www.naukri.com" + link
                    if not link:
                        continue

                    job_id = card.get_attribute("data-job-id") or ""
                    if not job_id:
                        match = re.search(r"-(\d{6,})(?:\?|$)", link)
                        job_id = match.group(1) if match else link
                    if job_id in seen:
                        continue
                    seen.add(job_id)

                    text_blob = (card.text_content() or "").lower()
                    work_mode = normalize_work_mode(text_blob)
                    if query.work_mode and work_mode != query.work_mode:
                        continue

                    jobs.append(Job(
                        id=str(job_id),
                        title=title,
                        company=company,
                        location=location,
                        experience=normalize_experience(experience_text),
                        salary=normalize_salary(salary_text),
                        work_mode=work_mode,
                        skills=[],
                        description=description,
                        posted_at=posted,
                        job_url=link,
                    ))
                    page_new += 1

                if len(jobs) >= target or page_new == 0:
                    break

            return jobs, len(jobs)
        finally:
            browser.close()

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int]:
        return await asyncio.to_thread(self._search_sync, query)
