import asyncio
import re
from typing import List, Tuple

from app.schemas.jobs import Job, SearchQuery
from app.services.browser import BrowserManager
from app.utils.normalizers import (
    experience_matches,
    freshness_matches,
    normalize_employment_type,
    normalize_experience,
    normalize_salary,
    normalize_work_mode,
)

CARD_SELECTORS = ["div.srp-jobtuple-wrapper", "div.cust-job-tuple", "article.jobTuple"]
TITLE_SELECTORS = ["a.title", ".title.ellipsis"]
COMPANY_SELECTORS = ["a.comp-name", ".comp-name", ".subTitle"]
LOCATION_SELECTORS = ["span.locWdth", ".loc-wrap span", ".location"]
EXPERIENCE_SELECTORS = ["span.expwdth", ".exp-wrap span", ".experience"]
SALARY_SELECTORS = ["span.sal-wrap span", ".sal", ".salary"]
POSTED_SELECTORS = ["span.job-post-day", ".job-post-day"]
DESCRIPTION_SELECTORS = ["span.job-desc", ".job-description"]
SKILL_SELECTORS = [".tags-gt .tag-li", ".tags-gt li", ".jobTupleFooter .tag-li", ".key-skill"]


class NaukriUpstreamError(Exception):
    def __init__(self, message, status_code=None, response_preview=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_preview = response_preview


class NaukriService:
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
    def _all_text(card, selectors):
        values = []
        seen = set()
        for selector in selectors:
            try:
                locator = card.locator(selector)
                for index in range(locator.count()):
                    text = (locator.nth(index).text_content(timeout=500) or "").strip()
                    key = text.lower()
                    if text and key not in seen:
                        seen.add(key)
                        values.append(text)
                if values:
                    break
            except Exception:
                continue
        return values

    @staticmethod
    def _detect_challenge(page):
        url = (page.url or "").lower()
        if "/nlogin" in url or "/login" in url:
            raise NaukriUpstreamError("Naukri requested authentication; anonymous collection unavailable")
        try:
            text = ((page.title() or "") + "\n" + (page.locator("body").inner_text(timeout=1500) or "")).lower()
        except Exception:
            text = ""
        markers = ("captcha", "recaptcha", "verify you are human", "security verification", "unusual activity")
        if any(marker in text for marker in markers):
            raise NaukriUpstreamError("Naukri CAPTCHA/challenge detected; collector will not bypass it")

    def _search_sync(self, query):
        browser = BrowserManager()
        jobs = []  # type: List[Job]
        seen = set()
        try:
            page = browser.launch()
            keyword_slug = self._slugify(query.keyword)
            location_slug = self._slugify(query.location)
            if not keyword_slug:
                raise NaukriUpstreamError("keyword is required")

            base_path = (
                "https://www.naukri.com/{}-jobs-in-{}".format(keyword_slug, location_slug)
                if location_slug else "https://www.naukri.com/{}-jobs".format(keyword_slug)
            )
            target = min(query.limit, 50)
            start_page = max(query.page, 1)
            # Filters can remove cards, so inspect a few extra pages to fill the requested limit.
            pages_to_scan = 1 if not (query.experience or query.freshness or query.work_mode) else self.MAX_PAGES
            last_page = start_page + pages_to_scan - 1

            for page_num in range(start_page, last_page + 1):
                url = base_path if page_num == 1 else "{}-{}".format(base_path, page_num)
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response is not None and response.status >= 400:
                    preview = None
                    try:
                        preview = (page.locator("body").inner_text(timeout=1500) or "")[:500]
                    except Exception:
                        pass
                    raise NaukriUpstreamError(
                        "Naukri search page returned HTTP {}".format(response.status),
                        status_code=response.status, response_preview=preview,
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
                    raise NaukriUpstreamError("Naukri returned no recognizable job cards; page structure may have changed")

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
                    experience = normalize_experience(experience_text)

                    if not experience_matches(experience, query.experience):
                        continue
                    if not freshness_matches(posted, query.freshness):
                        continue

                    link = ""
                    try:
                        title_link = card.locator("a.title")
                        if title_link.count() > 0:
                            link = title_link.first.get_attribute("href", timeout=1000) or ""
                    except Exception:
                        pass
                    if not link:
                        continue
                    if link.startswith("/"):
                        link = "https://www.naukri.com" + link

                    job_id = card.get_attribute("data-job-id") or ""
                    if not job_id:
                        match = re.search(r"-(\d{6,})(?:\?|$)", link)
                        job_id = match.group(1) if match else link
                    if job_id in seen:
                        continue

                    text_blob = card.text_content() or ""
                    work_mode = normalize_work_mode(text_blob)
                    if query.work_mode and work_mode != query.work_mode:
                        continue

                    seen.add(job_id)
                    jobs.append(Job(
                        id=str(job_id), title=title, company=company, location=location,
                        experience=experience, salary=normalize_salary(salary_text),
                        work_mode=work_mode,
                        employment_type=normalize_employment_type(text_blob),
                        skills=self._all_text(card, SKILL_SELECTORS),
                        description=description, posted_at=posted, job_url=link,
                    ))

                if len(jobs) >= target:
                    break

            # A valid filtered search may legitimately have zero matches.
            return jobs, len(jobs)
        finally:
            browser.close()

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int]:
        return await asyncio.to_thread(self._search_sync, query)
