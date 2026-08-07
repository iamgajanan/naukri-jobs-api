import asyncio
import re
from typing import List, Tuple

from app.schemas.jobs import Job, SearchQuery
from app.services.browser import BrowserManager
from app.utils.normalizers import (
    experience_matches, freshness_matches, normalize_employment_type,
    normalize_experience, normalize_salary, normalize_work_mode,
)

CARD_SELECTORS = ["div.srp-jobtuple-wrapper", "div.cust-job-tuple", "article.jobTuple", "div.jobTuple", "div[data-job-id]"]
TITLE_SELECTORS = ["a.title", "a[title][href*='job-listings']", "a[href*='job-listings']", ".title.ellipsis"]
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
    MAX_PAGES = 10
    FILTER_SCAN_PAGES = 4
    NAUKRI_PAGE_SIZE = 20
    MAX_LIMIT = 100

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
        values, seen = [], set()
        for selector in selectors:
            try:
                locator = card.locator(selector)
                for index in range(locator.count()):
                    text = (locator.nth(index).text_content(timeout=500) or "").strip()
                    key = text.lower()
                    if text and key not in seen:
                        seen.add(key); values.append(text)
                if values:
                    break
            except Exception:
                continue
        return values

    @staticmethod
    def _page_snapshot(page):
        try: title = page.title() or ""
        except Exception: title = ""
        try: body = " ".join((page.locator("body").inner_text(timeout=2000) or "").split())[:1200]
        except Exception: body = ""
        try: links = page.locator("a[href*='job-listings']").count()
        except Exception: links = -1
        return "url={} | title={} | job_links={} | body={}".format(page.url, title, links, body)

    @staticmethod
    def _detect_challenge(page):
        url = (page.url or "").lower()
        if "/nlogin" in url or "/login" in url:
            raise NaukriUpstreamError("Naukri requested authentication; anonymous collection unavailable", response_preview=NaukriService._page_snapshot(page))
        try: text = ((page.title() or "") + "\n" + (page.locator("body").inner_text(timeout=1500) or "")).lower()
        except Exception: text = ""
        if any(marker in text for marker in ("captcha", "recaptcha", "verify you are human", "security verification", "unusual activity")):
            raise NaukriUpstreamError("Naukri CAPTCHA/challenge detected; collector will not bypass it", response_preview=NaukriService._page_snapshot(page))

    @staticmethod
    def _page_url(base_path, page_num):
        return base_path if page_num == 1 else "{}-{}".format(base_path, page_num)

    @staticmethod
    def _find_cards(page):
        for selector in CARD_SELECTORS:
            try:
                candidate = page.locator(selector)
                if candidate.count() > 0: return candidate
            except Exception: continue
        try:
            links = page.locator("a[href*='job-listings']")
            if links.count() > 0:
                containers = links.locator("xpath=ancestor::*[@data-job-id or self::article or contains(@class,'jobTuple')][1]")
                if containers.count() > 0: return containers
        except Exception: pass
        return None

    @staticmethod
    def _effective_keyword(query):
        # Zero years means fresher/entry-level intent. A broad query such as
        # "developer" otherwise scans mostly experienced jobs before our local
        # experience filter can find matches. Narrow the public search first,
        # then still validate every returned experience range below.
        if query.experience == 0:
            lowered = query.keyword.lower()
            if "fresher" not in lowered and "entry level" not in lowered:
                return "{} fresher".format(query.keyword)
        return query.keyword

    def _search_sync(self, query):
        browser = BrowserManager(); jobs = []; seen = set()
        try:
            page = browser.launch()
            keyword_slug = self._slugify(self._effective_keyword(query))
            location_slug = self._slugify(query.location)
            if not keyword_slug: raise NaukriUpstreamError("keyword is required")
            base_path = "https://www.naukri.com/{}-jobs-in-{}".format(keyword_slug, location_slug) if location_slug else "https://www.naukri.com/{}-jobs".format(keyword_slug)
            target = max(1, min(query.limit, self.MAX_LIMIT)); start_page = max(query.page, 1)
            minimum_pages = max(1, (target + self.NAUKRI_PAGE_SIZE - 1) // self.NAUKRI_PAGE_SIZE)
            filtered = query.experience is not None or query.freshness is not None or query.work_mode is not None
            # Previously every filtered request scanned 10 pages (~200 cards),
            # producing 20-23s latency for rare work modes. Bound small filtered
            # searches to four pages; large limits still get the pages they need.
            pages_to_scan = min(max(minimum_pages, self.FILTER_SCAN_PAGES if filtered else minimum_pages), self.MAX_PAGES)

            for page_num in range(start_page, start_page + pages_to_scan):
                response = page.goto(self._page_url(base_path, page_num), wait_until="domcontentloaded", timeout=30000)
                if response is not None and response.status >= 400:
                    raise NaukriUpstreamError("Naukri search page returned HTTP {}".format(response.status), status_code=response.status, response_preview=self._page_snapshot(page))
                try: page.wait_for_function("() => document.querySelectorAll(\"a[href*='job-listings']\").length > 0", timeout=6000)
                except Exception: page.wait_for_timeout(1000)
                self._detect_challenge(page)
                cards = self._find_cards(page)
                if cards is None or cards.count() == 0:
                    if jobs: break
                    raise NaukriUpstreamError("Naukri returned no recognizable job cards", response_preview=self._page_snapshot(page))

                for index in range(cards.count()):
                    if len(jobs) >= target: break
                    card = cards.nth(index); title = self._first_match(card, TITLE_SELECTORS)
                    if not title: continue
                    company = self._first_match(card, COMPANY_SELECTORS)
                    location = self._first_match(card, LOCATION_SELECTORS) or query.location
                    experience_text = self._first_match(card, EXPERIENCE_SELECTORS)
                    salary_text = self._first_match(card, SALARY_SELECTORS)
                    posted = self._first_match(card, POSTED_SELECTORS)
                    description = self._first_match(card, DESCRIPTION_SELECTORS)
                    experience = normalize_experience(experience_text)
                    if not experience_matches(experience, query.experience) or not freshness_matches(posted, query.freshness): continue
                    link = ""
                    try:
                        title_link = card.locator("a[href*='job-listings']")
                        if title_link.count() > 0: link = title_link.first.get_attribute("href", timeout=1000) or ""
                    except Exception: pass
                    if not link: continue
                    if link.startswith("/"): link = "https://www.naukri.com" + link
                    job_id = card.get_attribute("data-job-id") or ""
                    if not job_id:
                        match = re.search(r"-(\d{6,})(?:\?|$)", link); job_id = match.group(1) if match else link
                    dedupe_key = str(job_id or link).strip().lower()
                    if dedupe_key in seen: continue
                    text_blob = card.text_content() or ""; work_mode = normalize_work_mode(text_blob)
                    if query.work_mode and work_mode != query.work_mode: continue
                    seen.add(dedupe_key)
                    jobs.append(Job(id=str(job_id), title=title, company=company, location=location, experience=experience,
                        salary=normalize_salary(salary_text), work_mode=work_mode, employment_type=normalize_employment_type(text_blob),
                        skills=self._all_text(card, SKILL_SELECTORS), description=description, posted_at=posted, job_url=link))
                if len(jobs) >= target: break
            return jobs[:target], min(len(jobs), target)
        finally: browser.close()

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int]:
        return await asyncio.to_thread(self._search_sync, query)
