import copy
import json
import os
import threading
import time
from typing import Dict, Tuple

from app.schemas.jobs import Job, SearchQuery

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class SearchCache:
    """Search cache with fresh/stale semantics for Redis and memory."""

    PREFIX = "naukri:search:v2:"

    def __init__(self, ttl_seconds=None, stale_seconds=None) -> None:
        self.ttl_seconds = ttl_seconds or int(os.getenv("CACHE_TTL_SECONDS", "600"))
        self.stale_seconds = stale_seconds or int(os.getenv("CACHE_STALE_SECONDS", "3600"))
        self._items = {}  # type: Dict[str, Tuple[float, object]]
        self._lock = threading.Lock()
        self.redis_url = os.getenv("REDIS_URL")
        self._redis = None
        if self.redis_url and redis is not None:
            try:
                client = redis.Redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    @staticmethod
    def key(query: SearchQuery) -> str:
        return "|".join([
            query.keyword.strip().lower(), (query.location or "").strip().lower(),
            str(query.experience if query.experience is not None else ""),
            str(query.freshness if query.freshness is not None else ""), str(query.work_mode or ""),
            str(query.page), str(query.limit),
        ])

    def _redis_key(self, query):
        return self.PREFIX + self.key(query)

    @staticmethod
    def _serialize(value, created_at):
        jobs, total = value
        return json.dumps({
            "created_at": created_at,
            "jobs": [job.model_dump(mode="json") for job in jobs],
            "total": total,
        })

    @staticmethod
    def _deserialize(raw):
        payload = json.loads(raw)
        value = ([Job.model_validate(item) for item in payload["jobs"]], int(payload["total"]))
        return float(payload.get("created_at", time.time())), value

    @property
    def backend(self):
        return "redis" if self._redis is not None else "memory"

    def get(self, query: SearchQuery, allow_stale: bool = False):
        max_age = self.stale_seconds if allow_stale else self.ttl_seconds
        if self._redis is not None:
            try:
                raw = self._redis.get(self._redis_key(query))
                if raw:
                    created_at, value = self._deserialize(raw)
                    if time.time() - created_at <= max_age:
                        return value
            except Exception:
                pass

        cache_key = self.key(query)
        with self._lock:
            item = self._items.get(cache_key)
            if not item:
                return None
            created_at, value = item
            age = time.time() - created_at
            if age > max_age:
                if age > self.stale_seconds:
                    self._items.pop(cache_key, None)
                return None
            return copy.deepcopy(value)

    def set(self, query: SearchQuery, value) -> None:
        created_at = time.time()
        with self._lock:
            self._items[self.key(query)] = (created_at, copy.deepcopy(value))
        if self._redis is not None:
            try:
                # Redis keeps the entry for the complete stale window. get()
                # decides whether it is fresh enough for a normal cache hit.
                self._redis.setex(
                    self._redis_key(query),
                    max(self.stale_seconds, self.ttl_seconds),
                    self._serialize(value, created_at),
                )
            except Exception:
                pass

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
        if self._redis is not None:
            try:
                for key in self._redis.scan_iter(match=self.PREFIX + "*"):
                    self._redis.delete(key)
            except Exception:
                pass


search_cache = SearchCache()
