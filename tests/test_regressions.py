import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tossbot import autopilot, backtest, sim
from tossbot.analysis import analyze
from tossbot.client import TossAPIError
from tossbot.risk import RiskManager
from tossbot.trader import Trader


@pytest.mark.parametrize("price,fx", [(float("nan"), 1), (float("inf"), 1), (100, float("nan")), (100, -1)])
def test_invalid_quote_never_changes_ledger(price, fx):
    sim.reset()
    before = Path(sim.STATE_FILE).read_bytes()
    with pytest.raises(sim.SimError):
        sim.order("AAPL", "BUY", 1, price, currency="USD", fx=fx)
    assert Path(sim.STATE_FILE).read_bytes() == before


def test_corrupt_ledger_cannot_be_overwritten_as_empty():
    path = Path(sim.STATE_FILE)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(sim.SimError):
        sim.order("005930", "BUY", 1, 100)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_failed_save_does_not_keep_uncommitted_balance(monkeypatch):
    sim.reset()
    before = sim.get_state()
    monkeypatch.setattr(sim.os, "replace", Mock(side_effect=OSError("disk unavailable")))
    with pytest.raises((OSError, sim.SimError)):
        sim.order("005930", "BUY", 1, 100)
    assert sim.get_state() == before


def test_negative_reset_is_rejected():
    with pytest.raises(sim.SimError):
        sim.reset(-100)


def test_currency_cannot_change_existing_position():
    sim.order("AAPL", "BUY", 1, 100, currency="USD", fx=1300)
    before = Path(sim.STATE_FILE).read_bytes()
    with pytest.raises(sim.SimError):
        sim.order("AAPL", "SELL", 1, 100, currency="KRW")
    assert Path(sim.STATE_FILE).read_bytes() == before


def test_pending_order_never_changes_positions_or_resubmits():
    portfolio = Mock()
    broker = Mock(name="fake-broker")
    broker.name = "offline"
    broker.place_order.return_value = {"status": "PENDING", "filledQty": 0}
    trader = Trader(Mock(), portfolio=portfolio, broker=broker)
    assert trader._execute_buy("005930", "test", 100, 1) is None
    assert trader._execute_buy("005930", "test", 100, 1) is None
    portfolio.open.assert_not_called()
    assert broker.place_order.call_count == 1


def test_loss_guard_blocks_entries_when_valuation_fails():
    portfolio = Mock()
    portfolio.daily_pnl.side_effect = RuntimeError("missing valuation")
    assert RiskManager().daily_loss_kill(portfolio) is True


def test_regime_guard_blocks_new_entries_when_data_missing():
    assert autopilot._guard_params(None, 100_000)[0] is False


@pytest.mark.parametrize("operation", [analyze, backtest.backtest])
def test_upstream_failure_is_not_reported_as_missing_stock(operation):
    client = Mock()
    client.candles.side_effect = TossAPIError(503, "upstream-unavailable", "service unavailable")
    with pytest.raises(TossAPIError):
        operation(client, "005930")


def test_invalid_order_is_rejected_before_quote_lookup(api, monkeypatch):
    http, module = api
    prices = Mock(side_effect=AssertionError("Must validate before quote lookup"))
    monkeypatch.setattr(module._client, "prices", prices)
    response = http.post("/api/sim/order", json={"symbol": "005930", "side": "BUY", "qty": 0})
    assert response.status_code == 422
    prices.assert_not_called()


def test_api_backtest_rejects_invalid_capital(api):
    http, _ = api
    assert http.get("/api/backtest/005930?capital=-1").status_code in (400, 422)


def test_sim_order_invalidates_journal_cache(api):
    http, _ = api
    assert http.get("/api/journal").status_code == 200
    assert http.post("/api/sim/order", json={"symbol": "005930", "side": "BUY", "qty": 1}).status_code == 200
    assert http.post("/api/sim/order", json={"symbol": "005930", "side": "SELL", "qty": 1}).status_code == 200
    stats = http.get("/api/journal").json()
    assert stats["trades"] == 1


def test_intraday_strategies_do_not_change_daily_registry():
    from tossbot.strategies import REGISTRY, for_interval
    assert len(REGISTRY) == 94
    assert len(for_interval("1m")) == 99
    assert len(for_interval("1d")) == 94


def test_resetting_logs_preserves_protective_plans(monkeypatch):
    plans = {"005930": {"stop": 90, "target": 120}}
    monkeypatch.setattr(autopilot, "_entry_plans", plans)
    autopilot.reset_logs()
    assert plans["005930"]["stop"] == 90


def test_autopilot_does_not_buy_a_missing_current_quote(monkeypatch):
    monkeypatch.setattr(autopilot.sim, "held_symbols", lambda **kwargs: [])
    order = Mock()
    monkeypatch.setattr(autopilot.sim, "order", order)
    autopilot._try_entries([{"symbol": "005930", "price": 100, "action": "BUY", "quantScore": 99, "plan": {"inZone": True, "entryLow": 90, "entryHigh": 110}}], {}, 3, 100_000)
    order.assert_not_called()


def test_existing_stop_does_not_move_with_a_new_screen(monkeypatch):
    sim.order("005930", "BUY", 1, 100)
    monkeypatch.setattr(autopilot, "_entry_plans", {"005930": {"stop": 95, "target": 120}})
    autopilot._try_exits({"005930": {"plan": {"stop": 80, "target": 130}}}, {"005930": 90}, 3)
    assert sim.get_state()["positions"] == []


def test_paper_mode_never_sends_live_orders(monkeypatch):
    from tossbot.brokers import TossBroker
    client = Mock(dry_run=False)
    portfolio = Mock()
    trader = Trader(client, portfolio=portfolio, broker=TossBroker(client))
    assert trader._execute_buy("005930", "test", 100, 1) is None
    client.place_order.assert_not_called()
    portfolio.open.assert_not_called()


def test_paper_save_failure_is_not_silently_accepted(monkeypatch):
    from tossbot.portfolio import Portfolio
    p = Portfolio()
    monkeypatch.setattr("tossbot.portfolio.os.replace", Mock(side_effect=OSError("disk error")))
    with pytest.raises(RuntimeError):
        p.open("005930", 1, 100)


def test_launcher_chooses_another_port_when_preferred_port_is_busy():
    import socket
    from server.launch import available_port
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        occupied = sock.getsockname()[1]
        assert available_port(occupied) != occupied
