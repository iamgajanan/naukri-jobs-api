import asyncio
import logging
import os
import threading
from typing import List, Tuple

from app.schemas.jobs import Job, SearchQuery
from app.services.cache import search_cache
from app.services.naukri import NaukriService

logger = logging.getLogger(__name__)


class CollectionService:
    """Coordinates cache, single-flight requests and bounded browser work.

    Naukri starts throttling when a verification suite opens many anonymous
    Chromium sessions back-to-back. Keep one live collector at a time, avoid
    retry storms, and serve a recent successful result when the upstream has a
    transient failure.
    """

    def __init__(self) -> None:
        self.naukri = NaukriService()
        self._locks = {}
        self._locks_guard = threading.Lock()
        self._live_slots = threading.BoundedSemaphore(
            max(1, int(os.getenv("MAX_LIVE_COLLECTORS", "1")))
        )

    def _lock_for(self, query: SearchQuery) -> threading.Lock:
        key = search_cache.key(query)
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

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

            # Do not run multiple anonymous browsers concurrently. If another
            # request owns the browser, wait for it rather than creating a
            # burst that makes Naukri throttle the Railway IP.
            self._live_slots.acquire()
            try:
                cached = search_cache.get(query)
                if cached is not None:
                    jobs, total = cached
                    return jobs, total, "cache"
                try:
                    jobs, total = self.naukri._search_sync(query)
                    search_cache.set(query, (jobs, total))
                    return jobs, total, "live"
                except Exception:
                    # Availability is more useful than turning a transient
                    # upstream block into a public 503. Redis retains entries
                    # for the stale window specifically for this case.
                    stale = search_cache.get(query, allow_stale=True)
                    if stale is not None:
                        jobs, total = stale
                        logger.warning("Serving stale cache after live collector failure query=%s", query)
                        return jobs, total, "stale-cache"
                    raise
            finally:
                self._live_slots.release()

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int, str]:
        return await asyncio.to_thread(self._collect_sync, query)


collection_service = CollectionService()
