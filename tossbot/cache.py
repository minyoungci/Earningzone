"""Bounded, thread-safe TTL cache with one build per key and generation."""
from collections import OrderedDict
from concurrent.futures import Future
import threading
import time


class CacheBusy(RuntimeError):
    pass


class TTLCache:
    def __init__(self, maxsize=512, max_inflight=128, negative_ttl=10):
        self.maxsize = maxsize
        self.max_inflight = max_inflight
        self.negative_ttl = negative_ttl
        self._lock = threading.Lock()
        self._entries = OrderedDict()
        self._inflight = {}
        self._generation = 0

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._generation += 1

    def pop(self, key, default=None):
        with self._lock:
            hit = self._entries.pop(key, None)
            self._generation += 1
            return hit[1] if hit else default

    def invalidate_prefix(self, prefix):
        with self._lock:
            for key in list(self._entries):
                if isinstance(key, str) and key.startswith(prefix):
                    del self._entries[key]
            self._generation += 1

    def get_or_create(self, key, ttl, build, *, wait=True):
        now = time.monotonic()
        with self._lock:
            generation = self._generation
            hit = self._entries.get(key)
            if hit and now < hit[0]:
                self._entries.move_to_end(key)
                if hit[2] is not None:
                    raise hit[2]
                return hit[1]
            pending = self._inflight.get(key)
            owner = pending is None or pending[0] != generation
            if owner:
                if len(self._inflight) >= self.max_inflight:
                    raise CacheBusy("요청 처리 중입니다 — 잠시 후 다시 시도하세요")
                future = Future()
                self._inflight[key] = (generation, future)
            else:
                future = pending[1]
                if not wait:
                    # Short stale window keeps an existing screen visible while rebuilding.
                    if hit and hit[2] is None and now < hit[0] + max(ttl, 30):
                        return hit[1]
                    raise CacheBusy("스크리닝 생성 중입니다 — 잠시 후 다시 시도하세요")
        if not owner:
            return future.result()
        data, error = None, None
        try:
            data = build()
        except BaseException as exc:
            error = exc
        with self._lock:
            if generation == self._generation and isinstance(error, (Exception, type(None))):
                expiry = time.monotonic() + (self.negative_ttl if error else ttl)
                self._entries[key] = (expiry, data, error)
                self._entries.move_to_end(key)
                while len(self._entries) > self.maxsize:
                    self._entries.popitem(last=False)
            if self._inflight.get(key) == (generation, future):
                del self._inflight[key]
        if error is not None:
            future.set_exception(error)
            raise error
        future.set_result(data)
        return data
