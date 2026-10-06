from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import Mock

import pytest

from tossbot.cache import CacheBusy, TTLCache
from tossbot import quant
from selftest import FakeClient


def test_concurrent_readers_build_once():
    cache = TTLCache()
    started, release = threading.Event(), threading.Event()
    calls = []
    def build():
        calls.append(1)
        started.set()
        assert release.wait(3)
        return {"value": 42}
    with ThreadPoolExecutor(max_workers=8) as pool:
        first = pool.submit(cache.get_or_create, "key", 60, build)
        assert started.wait(3)
        rest = [pool.submit(cache.get_or_create, "key", 60, build) for _ in range(7)]
        release.set()
        assert first.result()["value"] == 42
        assert all(f.result()["value"] == 42 for f in rest)
    assert len(calls) == 1


def test_invalidation_during_build_cannot_repopulate_stale_data():
    cache = TTLCache()
    started, release = threading.Event(), threading.Event()
    def build():
        started.set()
        assert release.wait(3)
        return "old"
    with ThreadPoolExecutor(max_workers=1) as pool:
        old = pool.submit(cache.get_or_create, "key", 60, build)
        assert started.wait(3)
        cache.clear()
        assert cache.get_or_create("key", 60, lambda: "new") == "new"
        release.set()
        assert old.result() == "old"
    assert cache.get_or_create("key", 60, lambda: "wrong") == "new"


def test_cache_is_bounded_and_failures_have_a_separate_ttl():
    cache = TTLCache(maxsize=3, negative_ttl=0)
    fail = Mock(side_effect=ValueError("temporary"))
    with pytest.raises(ValueError):
        cache.get_or_create("error", 100, fail)
    assert cache.get_or_create("error", 100, lambda: "recovered") == "recovered"
    for i in range(10):
        assert cache.get_or_create(str(i), 60, lambda: i) == i
    assert len(cache) == 3


def test_heavy_requests_do_not_wait_on_a_build():
    cache = TTLCache()
    started, release = threading.Event(), threading.Event()
    def build():
        started.set()
        assert release.wait(3)
        return "done"
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(cache.get_or_create, "screen", 30, build)
        assert started.wait(3)
        try:
            with pytest.raises(CacheBusy):
                cache.get_or_create("screen", 30, lambda: "wrong", wait=False)
        finally:
            release.set()
        assert first.result() == "done"


def test_quant_concurrency_reuses_scan_and_returns_isolated_results(monkeypatch):
    client = FakeClient()
    candles = Mock(wraps=client.candles)
    monkeypatch.setattr(client, "candles", candles)
    monkeypatch.setattr(quant.config, "KOSPI_UNIVERSE", [("TST001", "test")])
    quant.clear_caches()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outputs = list(pool.map(lambda _: quant.screen(client), range(6)))
    assert candles.call_count == 1
    assert len(outputs[0]["picks"]) == 1
    outputs[0]["picks"][0]["name"] = "mutated"
    assert all(o["picks"][0]["name"] == "test" for o in outputs[1:])
    assert quant.screen(client)["picks"][0]["name"] == "test"


def test_feature_cache_does_not_cross_client_or_name_boundaries():
    first, second = FakeClient(), FakeClient()
    quant.clear_caches()
    a = quant.screen(first, [("TST001", "first")])
    b = quant.screen(second, [("TST001", "second")])
    assert a["picks"][0]["name"] == "first"
    assert b["picks"][0]["name"] == "second"
