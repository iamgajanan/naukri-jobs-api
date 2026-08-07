import asyncio
import logging
import os
import threading
import time
from typing import List, Tuple

from playwright.sync_api import Error as PlaywrightError

from app.schemas.jobs import Job, SearchQuery
from app.services.cache import search_cache
from app.services.naukri import NaukriService, NaukriUpstreamError

logger = logging.getLogger(__name__)


class CollectionService:
    """Coordinates cache, single-flight requests and bounded browser work."""

    def __init__(self) -> None:
        self.naukri = NaukriService()
        self._locks = {}
        self._locks_guard = threading.Lock()
        self._live_slots = threading.BoundedSemaphore(
            max(1, int(os.getenv("MAX_LIVE_COLLECTORS", "1")))
        )
        self.browser_retries = max(0, int(os.getenv("COLLECTOR_BROWSER_RETRIES", "2")))

    def _lock_for(self, query: SearchQuery) -> threading.Lock:
        key = search_cache.key(query)
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    @staticmethod
    def _retryable_upstream_error(exc: NaukriUpstreamError) -> bool:
        """Only retry transient/blank upstream responses.

        Authentication, CAPTCHA/challenge and explicit client-block responses are
        intentionally not retried. A blank/empty Railway response is transient in
        practice and benefits from a completely fresh browser/context.
        """
        message = str(exc).lower()
        if "captcha" in message or "challenge" in message or "authentication" in message:
            return False
        if exc.status_code is not None:
            return exc.status_code >= 500 or exc.status_code in {408, 429}
        return "no recognizable job cards" in message

    def _run_live_with_retry(self, query: SearchQuery):
        """Retry transient browser and blank-upstream failures with fresh Chromium."""
        last_error = None
        for attempt in range(self.browser_retries + 1):
            try:
                return self.naukri._search_sync(query)
            except NaukriUpstreamError as exc:
                last_error = exc
                if not self._retryable_upstream_error(exc) or attempt >= self.browser_retries:
                    raise
                logger.warning(
                    "Transient Naukri upstream failure attempt=%s/%s query=%s: %s preview=%s",
                    attempt + 1,
                    self.browser_retries + 1,
                    query,
                    exc,
                    exc.response_preview,
                )
            except PlaywrightError as exc:
                last_error = exc
                logger.warning(
                    "Transient Playwright collector failure attempt=%s/%s query=%s: %s",
                    attempt + 1,
                    self.browser_retries + 1,
                    query,
                    exc,
                )
                if attempt >= self.browser_retries:
                    raise
            time.sleep(0.35 * (attempt + 1))
        raise last_error  # pragma: no cover

    def _collect_sync(self, query: SearchQuery) -> Tuple[List[Job], int, str]:
        cached = search_cache.get(query)
        if cached is not None:
            jobs, total = cached
            return jobs, total, "cache"

        lock = self._lock_for(query)
        with lock:
            cached = search_cache.get(query)
            if cached is not None:
                jobs, total = cached
                return jobs, total, "cache"

            if not self._live_slots.acquire(blocking=False):
                stale = search_cache.get(query, allow_stale=True)
                if stale is not None:
                    jobs, total = stale
                    return jobs, total, "stale-cache"
                self._live_slots.acquire()
            try:
                cached = search_cache.get(query)
                if cached is not None:
                    jobs, total = cached
                    return jobs, total, "cache"
                try:
                    jobs, total = self._run_live_with_retry(query)
                    search_cache.set(query, (jobs, total))
                    return jobs, total, "live"
                except Exception:
                    stale = search_cache.get(query, allow_stale=True)
                    if stale is not None:
                        jobs, total = stale
                        return jobs, total, "stale-cache"
                    raise
            finally:
                self._live_slots.release()

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int, str]:
        return await asyncio.to_thread(self._collect_sync, query)


collection_service = CollectionService()
