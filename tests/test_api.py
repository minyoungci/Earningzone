import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tossbot import config, sim
from tossbot.client import TossAPIError, TossClient
from tossbot.features import build_features
from tossbot.analysis import aggregate
from tossbot.strategies.base import SignalList, buy
from tossbot.kis import KISClient, KISError


@pytest.mark.parametrize("route", ["/api/health", "/api/auth", "/api/selftest", "/api/watchlist", "/api/watchlist?market=us", "/api/analyze/005930", "/api/candles/005930", "/api/intraday/005930", "/api/backtest/005930", "/api/backtest/005930/compare", "/api/screener", "/api/sim/state", "/api/sim/accounts", "/api/journal", "/api/autopilot", "/api/settings/keys", "/api/search?q=삼전", "/api/quant?market=kr", "/api/quant/plan/005930", "/api/broker", "/api/notify", "/api/regime", "/api/macro", "/api/news", "/api/calendar"])
def test_read_routes_return_valid_json(api, route):
    http, _ = api
    response = http.get(route)
    assert response.status_code == 200, response.text
    json.dumps(response.json(), allow_nan=False)


def test_write_token_and_request_origin_guards(api, monkeypatch):
    http, module = api
    monkeypatch.setattr(module, "ACCESS_TOKEN", "test-control")
    body = {"symbol": "005930", "side": "BUY", "qty": 1}
    assert http.post("/api/sim/order", json=body).status_code == 401
    assert http.post("/api/sim/order", json=body, headers={"X-Access-Token": "test-control", "Origin": "https://unrelated.example"}).status_code == 403
    assert http.post("/api/sim/order", json=body, headers={"X-Access-Token": "test-control", "Origin": "http://localhost:5173"}).status_code == 200
    assert http.patch("/api/unknown").status_code == 401


def test_account_crud_is_isolated_and_validated(api):
    http, _ = api
    created = http.post("/api/sim/accounts", json={"name": "second", "cash": 200_000}).json()
    acc = created["newId"]
    assert http.post("/api/sim/accounts/select", json={"id": acc}).status_code == 200
    assert http.post("/api/sim/order", json={"symbol": "005930", "side": "BUY", "qty": 1}).status_code == 200
    assert http.get("/api/sim/state").json()["positions"]
    assert http.post("/api/sim/accounts/select", json={"id": "default"}).status_code == 200
    assert http.get("/api/sim/state").json()["positions"] == []
    assert http.get("/api/journal").json()["recent"] == []
    assert http.delete(f"/api/sim/accounts/{acc}").status_code == 200
    assert http.delete("/api/sim/accounts/default").status_code == 400


def test_corrupt_state_is_reported_as_an_error(api):
    http, _ = api
    Path(sim.STATE_FILE).write_text("{broken", encoding="utf-8")
    assert http.get("/api/sim/state").status_code == 400


def test_auth_failure_is_502_and_missing_stock_is_404(api, monkeypatch):
    http, module = api
    monkeypatch.setattr(module._client, "candles", Mock(side_effect=TossAPIError(401, "invalid-token", "bad token")))
    assert http.get("/api/analyze/FAIL").status_code == 502
    monkeypatch.setattr(module._client, "candles", Mock(side_effect=TossAPIError(404, "stock-not-found", "missing")))
    assert http.get("/api/analyze/MISSING").status_code == 404


def test_key_replacement_clears_all_analysis_caches(api, monkeypatch):
    http, module = api
    monkeypatch.setattr(module.secrets_store, "save", Mock())
    module.cached("an:old", 60, lambda: {"value": "old"})
    assert http.post("/api/settings/keys", json={"client_id": "replacement", "client_secret": "replacement"}).status_code == 200
    assert len(module._cache) == 0


def test_key_replacement_requires_stopping_autopilot(api, monkeypatch):
    http, module = api
    save = Mock()
    monkeypatch.setattr(module.secrets_store, "save", save)
    monkeypatch.setattr(module.autopilot, "status", lambda: {"running": True})
    assert http.post("/api/settings/keys", json={"client_id": "replacement", "client_secret": "replacement"}).status_code == 409
    save.assert_not_called()


def test_strategy_failure_cannot_produce_a_buy():
    signals = SignalList([buy("test", "trend", 1, "test") for _ in range(10)])
    signals.errors = [{"strategy": "failed", "msg": "error"}]
    assert aggregate(signals)["action"] == "HOLD"


def test_running_autopilot_account_cannot_be_reset_or_deleted(api, monkeypatch):
    http, module = api
    created = http.post("/api/sim/accounts", json={"name": "running", "cash": 200_000}).json()
    account = created["newId"]
    assert http.post("/api/sim/accounts/select", json={"id": account}).status_code == 200
    before = Path(sim.STATE_FILE).read_bytes()
    monkeypatch.setattr(module.autopilot, "status", lambda: {"running": True, "account": account})
    assert http.post("/api/sim/reset", json={"cash": 300_000}).status_code == 409
    assert http.delete(f"/api/sim/accounts/{account}").status_code == 409
    assert Path(sim.STATE_FILE).read_bytes() == before
    assert http.post("/api/sim/accounts/select", json={"id": "default"}).status_code == 200
    assert http.post("/api/sim/reset", json={"cash": 300_000}).status_code == 200


def test_quant_reports_upstream_auth_failure(api, monkeypatch):
    from tossbot import quant
    http, module = api
    quant.clear_caches()
    monkeypatch.setattr(module._client, "candles", Mock(side_effect=TossAPIError(401, "invalid-token", "bad token")))
    assert http.get("/api/quant").status_code == 502


def test_quant_reports_network_failure(api, monkeypatch):
    from urllib.error import URLError
    from tossbot import quant
    http, module = api
    quant.clear_caches()
    monkeypatch.setattr(module._client, "candles", Mock(side_effect=URLError("offline")))
    assert http.get("/api/quant").status_code == 502


def test_invalid_last_quote_falls_back_to_valid_close():
    from selftest import gen_candles
    features = build_features("TEST", "test", gen_candles(), last_price=float("nan"))
    assert features["price"] == features["lastClose"]
    json.dumps(features, allow_nan=False)


def test_order_id_is_generated_once_for_each_submission(monkeypatch):
    client = TossClient("fake", "fake", dry_run=False)
    request = Mock(return_value={"orderId": "fake"})
    monkeypatch.setattr(client, "_request", request)
    client.place_order("005930", "BUY", "LIMIT", quantity=1, price=100)
    first = request.call_args.kwargs["body"]["clientOrderId"]
    client.place_order("005930", "BUY", "LIMIT", quantity=1, price=100)
    second = request.call_args.kwargs["body"]["clientOrderId"]
    assert first != second and len(first) == 36


@pytest.mark.parametrize("symbol,side,qty", [("AAPL", "BUY", 1), ("005930", "OTHER", 1), ("005930", "BUY", 1.5)])
def test_kis_rejects_unsupported_orders_without_sending(symbol, side, qty):
    with pytest.raises(KISError):
        KISClient().place_order(symbol, side, qty)
