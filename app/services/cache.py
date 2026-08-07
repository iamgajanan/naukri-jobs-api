import copy
import threading
import time
from typing import Dict, Optional, Tuple

from app.schemas.jobs import SearchQuery


class SearchCache:
    """Small in-process TTL cache for v1.

    It keeps the public API independent from Redis while avoiding a browser
    scrape for every repeated query. Redis can replace this implementation
    later without changing the jobs endpoint.
    """

    def __init__(self, ttl_seconds: int = 300, stale_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = stale_seconds
        self._items = {}  # type: Dict[str, Tuple[float, object]]
        self._lock = threading.Lock()

    @staticmethod
    def key(query: SearchQuery) -> str:
        return "|".join([
            query.keyword.strip().lower(),
            (query.location or "").strip().lower(),
            str(query.experience if query.experience is not None else ""),
            str(query.freshness if query.freshness is not None else ""),
            str(query.work_mode or ""),
            str(query.page),
            str(query.limit),
        ])

    def get(self, query: SearchQuery, allow_stale: bool = False):
        cache_key = self.key(query)
        with self._lock:
            item = self._items.get(cache_key)
            if not item:
                return None
            created_at, value = item
            age = time.time() - created_at
            max_age = self.stale_seconds if allow_stale else self.ttl_seconds
            if age > max_age:
                if age > self.stale_seconds:
                    self._items.pop(cache_key, None)
                return None
            return copy.deepcopy(value)

    def set(self, query: SearchQuery, value) -> None:
        with self._lock:
            self._items[self.key(query)] = (time.time(), copy.deepcopy(value))

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


search_cache = SearchCache()
