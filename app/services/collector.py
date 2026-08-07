import asyncio
import threading
from typing import List, Tuple

from app.schemas.jobs import Job, SearchQuery
from app.services.cache import search_cache
from app.services.naukri import NaukriService, NaukriUpstreamError


class CollectionService:
    """Coordinates cached results and the Naukri collection worker.

    Fresh cache is returned immediately. On a miss, one collection is allowed
    per query key. If collection fails for any reason, recently indexed stale
    results are returned when available instead of taking the whole API down.
    """

    def __init__(self) -> None:
        self.naukri = NaukriService()
        self._locks = {}  # type: dict
        self._locks_guard = threading.Lock()

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

            try:
                jobs, total = self.naukri._search_sync(query)
                search_cache.set(query, (jobs, total))
                return jobs, total, "live"
            except Exception:
                # Browser/Playwright cleanup and transient collector failures are
                # just as recoverable as explicit upstream errors. Prefer a
                # recently indexed response when one exists, then re-raise the
                # original exception for correct diagnostics if it does not.
                stale = search_cache.get(query, allow_stale=True)
                if stale is not None:
                    jobs, total = stale
                    return jobs, total, "stale-cache"
                raise

    async def search(self, query: SearchQuery) -> Tuple[List[Job], int, str]:
        return await asyncio.to_thread(self._collect_sync, query)


collection_service = CollectionService()
