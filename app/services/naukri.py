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
    EMPTY_PAGE_RETRIES = 1

    @staticmethod
    def _slugify(value):
        value = (value or "").strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        return value.strip("-")

    @staticmethod
    def _page_snapshot(page):
        try: title = page.title() or ""
        except Exception: title = ""
        try: body = " ".join((page.locator("body").inner_text(timeout=1000) or "").split())[:600]
        except Exception: body = ""
        try: links = page.locator("a[href*='job-listings']").count()
        except Exception: links = -1
        return "url={} | title={} | job_links={} | body={}".format(page.url, title, links, body)

    @staticmethod
    def _detect_challenge(page):
        url = (page.url or "").lower()
        if "/nlogin" in url or "/login" in url:
            raise NaukriUpstreamError("Naukri requested authentication; anonymous collection unavailable", response_preview=NaukriService._page_snapshot(page))
        try:
            text = ((page.title() or "") + "\n" + (page.locator("body").inner_text(timeout=1000) or "")).lower()
        except Exception:
            text = ""
        if any(marker in text for marker in ("captcha", "recaptcha", "verify you are human", "security verification", "unusual activity")):
            raise NaukriUpstreamError("Naukri CAPTCHA/challenge detected; collector will not bypass it", response_preview=NaukriService._page_snapshot(page))

    @staticmethod
    def _page_url(base_path, page_num):
        return base_path if page_num == 1 else "{}-{}".format(base_path, page_num)

    @staticmethod
    def _effective_keyword(query):
        keyword = query.keyword.strip()
        lowered = keyword.lower()
        if query.experience == 0 and "fresher" not in lowered and "entry level" not in lowered:
            keyword = "{} fresher".format(keyword)
            lowered = keyword.lower()
        mode_terms = {
            "remote": ("remote", ("remote", "work from home", "wfh")),
            "hybrid": ("hybrid", ("hybrid",)),
            "onsite": ("work from office", ("onsite", "on-site", "work from office", "wfo")),
        }
        if query.work_mode in mode_terms:
            search_term, aliases = mode_terms[query.work_mode]
            if not any(alias in lowered for alias in aliases):
                keyword = "{} {}".format(keyword, search_term)
        return keyword

    @staticmethod
    def _extract_cards(page):
        """Extract card fields in one browser->Python round trip.

        The old parser made many locator/count/text calls per card. On Railway
        those IPC round trips dominated filtered and 50/100-result requests.
        """
        return page.evaluate("""
        (selectors) => {
          const pick = (root, sels) => {
            for (const s of sels) {
              const el = root.querySelector(s);
              const t = el && (el.textContent || '').trim();
              if (t) return t;
            }
            return null;
          };
          const pickAll = (root, sels) => {
            for (const s of sels) {
              const vals = [...root.querySelectorAll(s)].map(e => (e.textContent || '').trim()).filter(Boolean);
              if (vals.length) return [...new Set(vals)];
            }
            return [];
          };
          let cards = [];
          for (const s of selectors) {
            cards = [...document.querySelectorAll(s)];
            if (cards.length) break;
          }
          return cards.map(card => {
            const linkEl = card.querySelector("a[href*='job-listings']");
            return {
              id: card.getAttribute('data-job-id') || '',
              title: pick(card, ["a.title", "a[title][href*='job-listings']", "a[href*='job-listings']", ".title.ellipsis"]),
              company: pick(card, ["a.comp-name", ".comp-name", ".subTitle"]),
              location: pick(card, ["span.locWdth", ".loc-wrap span", ".location"]),
              experience: pick(card, ["span.expwdth", ".exp-wrap span", ".experience"]),
              salary: pick(card, ["span.sal-wrap span", ".sal", ".salary"]),
              posted: pick(card, ["span.job-post-day", ".job-post-day"]),
              description: pick(card, ["span.job-desc", ".job-description"]),
              skills: pickAll(card, [".tags-gt .tag-li", ".tags-gt li", ".jobTupleFooter .tag-li", ".key-skill"]),
              link: linkEl ? (linkEl.href || linkEl.getAttribute('href') || '') : '',
              text: (card.textContent || '').trim()
            };
          });
        }
        """, CARD_SELECTORS)

    def _navigate_cards(self, page, url):
        last_preview = None
        for attempt in range(self.EMPTY_PAGE_RETRIES + 1):
            response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if response is not None and response.status >= 400:
                raise NaukriUpstreamError("Naukri search page returned HTTP {}".format(response.status), status_code=response.status, response_preview=self._page_snapshot(page))
            try:
                page.wait_for_function("() => document.querySelectorAll(\"a[href*='job-listings']\").length > 0", timeout=4500)
            except Exception:
                pass
            self._detect_challenge(page)
            cards = self._extract_cards(page)
            if cards:
                return cards
            last_preview = self._page_snapshot(page)
            if attempt < self.EMPTY_PAGE_RETRIES:
                page.wait_for_timeout(350)
        raise NaukriUpstreamError("Naukri returned no recognizable job cards", response_preview=last_preview)

    def _search_sync(self, query):
        browser = BrowserManager(); jobs = []; seen = set()
        try:
            page = browser.launch()
            keyword_slug = self._slugify(self._effective_keyword(query))
            location_slug = self._slugify(query.location)
            if not keyword_slug:
                raise NaukriUpstreamError("keyword is required")
            base_path = "https://www.naukri.com/{}-jobs-in-{}".format(keyword_slug, location_slug) if location_slug else "https://www.naukri.com/{}-jobs".format(keyword_slug)
            target = max(1, min(query.limit, self.MAX_LIMIT))
            start_page = max(query.page, 1)
            minimum_pages = max(1, (target + self.NAUKRI_PAGE_SIZE - 1) // self.NAUKRI_PAGE_SIZE)
            filtered = query.experience is not None or query.freshness is not None or query.work_mode is not None
            pages_to_scan = min(max(minimum_pages, self.FILTER_SCAN_PAGES if filtered else minimum_pages), self.MAX_PAGES)

            for page_num in range(start_page, start_page + pages_to_scan):
                try:
                    raw_cards = self._navigate_cards(page, self._page_url(base_path, page_num))
                except NaukriUpstreamError:
                    if jobs:
                        break
                    raise

                for raw in raw_cards:
                    if len(jobs) >= target:
                        break
                    title = (raw.get("title") or "").strip()
                    link = (raw.get("link") or "").strip()
                    if not title or not link:
                        continue
                    if link.startswith("/"):
                        link = "https://www.naukri.com" + link
                    experience = normalize_experience(raw.get("experience"))
                    if not experience_matches(experience, query.experience):
                        continue
                    if not freshness_matches(raw.get("posted"), query.freshness):
                        continue
                    text_blob = raw.get("text") or ""
                    work_mode = normalize_work_mode(text_blob)
                    if query.work_mode and work_mode != query.work_mode:
                        continue
                    job_id = raw.get("id") or ""
                    if not job_id:
                        match = re.search(r"-(\d{6,})(?:\?|$)", link)
                        job_id = match.group(1) if match else link
                    dedupe_key = str(job_id or link).strip().lower()
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    jobs.append(Job(
                        id=str(job_id), title=title, company=raw.get("company"),
                        location=raw.get("location") or query.location, experience=experience,
                        salary=normalize_salary(raw.get("salary")), work_mode=work_mode,
                        employment_type=normalize_employment_type(text_blob),
                        skills=raw.get("skills") or [], description=raw.get("description"),
                        posted_at=raw.get("posted"), job_url=link,
                    ))
                if len(jobs) >= target:
                    break
            return jobs[:target], min(len(jobs), target)
        finally:
            browser.close()

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int]:
        return await asyncio.to_thread(self._search_sync, query)
