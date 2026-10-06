import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    from tossbot import config, sim

    monkeypatch.setattr(sim, "STATE_FILE", str(tmp_path / "sim.json"))
    monkeypatch.setattr(sim, "_cache_key", None)
    monkeypatch.setattr(sim, "_cache_state", None)
    monkeypatch.setattr(config, "PAPER_STATE_FILE", str(tmp_path / "paper.json"))
    monkeypatch.setattr(config, "BROKER_STATE_FILE", str(tmp_path / "broker.json"))
    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(config, "CLIENT_ID", "offline-test")
    monkeypatch.setattr(config, "CLIENT_SECRET", "offline-test")
    monkeypatch.setattr("urllib.request.urlopen", Mock(side_effect=AssertionError("External network disabled")))
    monkeypatch.setattr("tossbot.notify.send", Mock())
    yield


@pytest.fixture
def api(monkeypatch):
    from fastapi.testclient import TestClient
    from selftest import gen_candles

    module = importlib.import_module("server.app")

    class Market:
        dry_run = True

        def candles(self, symbol, interval="1d", count=200, **kwargs):
            rows = gen_candles(count, start=100, seed=2)
            for i, row in enumerate(reversed(rows)):
                row["timestamp"] = f"2026-01-01T00:{i // 60:02}:{i % 60:02}+09:00" if interval == "1m" else f"2026-{1 + i // 28:02}-{1 + i % 28:02}T00:00:00+09:00"
                row["currency"] = "KRW" if symbol.isdigit() else "USD"
            return {"candles": rows}

        def prices(self, symbols):
            return [{"symbol": s, "lastPrice": "100", "currency": "KRW" if s.isdigit() else "USD"} for s in symbols]

        def orderbook(self, symbol):
            return {"bids": [], "asks": []}

        def stocks(self, symbols):
            return [{"symbol": s, "name": s, "market": "US"} for s in symbols]

        def exchange_rate(self, *args):
            return 1300

    monkeypatch.setattr(module, "_client", Market())
    monkeypatch.setattr(module, "ACCESS_TOKEN", "")
    monkeypatch.setattr(module, "_public_ip", lambda: None)
    monkeypatch.setattr(module.secrets_store, "status", lambda: {"available": True, "has_id": False, "has_secret": False})
    module._cache.clear()
    yield TestClient(module.app), module
    module._cache.clear()
