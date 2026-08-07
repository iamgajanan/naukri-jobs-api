import asyncio
import os
import threading
from typing import List, Tuple

from app.schemas.jobs import Job, SearchQuery
from app.services.cache import search_cache
from app.services.naukri import NaukriService


class CollectionService:
    """Coordinates cache, single-flight requests and bounded browser work."""

    def __init__(self) -> None:
        self.naukri = NaukriService()
        self._locks = {}
        self._locks_guard = threading.Lock()
        # Multiple Chromium instances are a common source of Hobby-container
        # instability. Default to one live collector; cache hits never wait.
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

            # If another live collection is already consuming Chromium, prefer
            # stale data for this query rather than queueing a customer behind it.
            if not self._live_slots.acquire(blocking=False):
                stale = search_cache.get(query, allow_stale=True)
                if stale is not None:
                    jobs, total = stale
                    return jobs, total, "stale-cache"
                # No prior data exists, so wait for the one bounded slot instead
                # of launching another browser and risking container exhaustion.
                self._live_slots.acquire()
            try:
                # A previous waiter may have populated this exact query.
                cached = search_cache.get(query)
                if cached is not None:
                    jobs, total = cached
                    return jobs, total, "cache"
                try:
                    jobs, total = self.naukri._search_sync(query)
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
