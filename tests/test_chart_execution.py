from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from tossbot import autopilot, chart_execution as policy, quant, sim


NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def setup_bars():
    # A prior swing low, confirmed resistance, then three distinct later candles.
    closes = [70 + i * .4 for i in range(60)]
    closes[42:50] = [87, 85, 83, 80, 83, 85, 87, 90]
    closes[50:60] = [92, 96, 94, 93, 92, 95, 98, 97, 96, 95]
    rows = []
    for i, c in enumerate(closes):
        rows.append({"time": (NOW - timedelta(days=63-i)).date().isoformat(),
                     "open": c-.3, "high": c+1, "low": c-1, "close": c, "volume": 1000})
    # High 99 confirmed at index 59; ATR width ~0.6; breakout then test then follow-through.
    for o, h, l, c, v in [(100, 102, 99.8, 101, 1000), (100, 101.5, 99, 100.5, 1000), (102, 104, 101, 103, 1800)]:
        rows.append({"time": (NOW - timedelta(days=63-len(rows))).date().isoformat(),
                     "open": o, "high": h, "low": l, "close": c, "volume": v})
    return rows


def plan():
    return {"policy": policy.VERSION, "signalId": "test:confirmed:005930", "confirmedAt": "2026-10-02",
            "expiresAt": (datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
            "stop": 95, "target": 120, "entryLow": 99, "entryHigh": 104}


def test_requires_distinct_completed_breakout_retest_and_followthrough():
    rows = setup_bars()
    assert not policy.timing("005930", rows[:-2], NOW)["eligible"]
    assert not policy.timing("005930", rows[:-1], NOW)["eligible"]
    result = policy.timing("005930", rows, NOW)
    assert result["eligible"], result
    assert result["plan"]["stop"] < 99 < 103 < result["plan"]["target"]
    assert result["plan"]["confirmedAt"] == rows[-1]["time"]


def test_unclosed_future_candle_cannot_change_signal_plan():
    rows = setup_bars()
    before = policy.timing("005930", rows, NOW)
    assert before["eligible"]
    future = {"time": NOW.date().isoformat(), "open": 500, "high": 900, "low": 1, "close": 800, "volume": 1e8}
    after = policy.timing("005930", rows+[future], NOW)
    assert after["plan"] == before["plan"]
    assert after["quality"]["unclosed"] == 1


def test_measured_plan_uses_only_levels_known_at_confirmation():
    rows = setup_bars()
    before = policy.timing("005930", rows, NOW)
    future = {"time": NOW.date().isoformat(), "open": 103, "high": 104, "low": 102, "close": 103, "volume": 1000}
    after = policy.timing("005930", rows+[future], NOW+timedelta(days=1))
    assert before["plan"] == after["plan"]


@pytest.mark.parametrize("bad", ["duplicate", "nan", "old", "low_volume", "invalidated"])
def test_rejects_bad_stale_unconfirmed_or_invalidated_data(bad):
    rows = setup_bars()
    now = NOW
    if bad == "duplicate":
        rows.append(dict(rows[-1]))
    elif bad == "nan":
        rows[-1]["close"] = float("nan")
    elif bad == "old":
        now += timedelta(days=10)
    elif bad == "low_volume":
        rows[-1]["volume"] = 100
    else:
        rows.append({"time": NOW.date().isoformat(), "open": 96, "high": 97, "low": 94, "close": 95, "volume": 1000})
        now += timedelta(days=1)
    assert not policy.timing("005930", rows, now)["eligible"]


def test_sizing_matches_sim_cash_and_realized_stop_loss():
    p = plan()
    sized = policy.entry_size(p, 100, 10000, 10000, 10000, .5, 1.5)
    sim.reset(10000)
    sim.order("005930", "BUY", sized["qty"], 100, execution_plan=p)
    sim.order("005930", "SELL", sized["qty"], p["stop"])
    loss = 10000 - sim.get_state()["cash"]
    assert sized["qty"] > 0 and loss <= 50
    assert loss == pytest.approx(sized["riskKrw"], abs=1)


@pytest.mark.parametrize("patch,price,fx,reason", [
    ({"target": 101}, 100, 1, "순손익비"), ({}, 110, 1, "진입 범위"),
    ({}, 100, float("nan"), "확인 불가"),
    ({"expiresAt": "2026-01-01T00:00:00+00:00"}, 100, 1, "만료"),
    ({"expiresAt": "2026-01-01"}, 100, 1, "불충족")])
def test_entry_gate_rejects_low_rr_gap_unknown_fx_expired_plan(patch, price, fx, reason):
    sized = policy.entry_size({**plan(), **patch}, price, 10000, 10000, 10000, fx=fx)
    assert sized["qty"] == 0 and reason in sized["reason"]


def test_cash_fee_and_combined_position_risk_caps():
    p = plan()
    sized = policy.entry_size(p, 100, 100, 1000000, 100)
    assert sized["qty"] == 0  # One share plus fee exceeds cash/budget.
    sized = policy.entry_size(p, 100, 1000000, 1000000, 1000000, open_risk=15000)
    assert sized["qty"] == 0  # 0.5% x three positions is fully used.


def test_missing_held_quote_cannot_use_average_price_for_entry_risk(monkeypatch):
    sim.order("000660", "BUY", 1, 100)
    order = Mock()
    monkeypatch.setattr(sim, "order", order)
    pick = {"symbol": "005930", "currency": "KRW", "timing": {"eligible": True, "plan": plan()}}
    autopilot._try_chart_entries([pick], {"005930": 100}, 3, 100000)
    order.assert_not_called()
    assert "현재가 확인 실패" in pick["timing"]["entryReason"]


def test_persisted_plan_and_same_signal_reentry_guard_survive_reload(monkeypatch):
    sim.reset()
    p = plan()
    sim.order("005930", "BUY", 2, 100, execution_plan=p)
    sim._cache_key = sim._cache_state = None
    assert sim.execution_plans()["005930"] == p
    monkeypatch.setattr(autopilot, "_entry_plans", {})
    autopilot._try_exits({"005930": {"plan": {"stop": 80, "target": 200}}}, {"005930": 94}, 3)
    assert not sim.held_symbols()
    before = Path(sim.STATE_FILE).read_bytes()
    with pytest.raises(sim.SimError, match="사용한 차트 신호"):
        sim.order("005930", "BUY", 2, 100, execution_plan=p)
    assert before == Path(sim.STATE_FILE).read_bytes()
    assert sim.signal_used(p["signalId"])


def test_start_restores_saved_plan_without_launching_execution(monkeypatch):
    p = plan()
    sim.order("005930", "BUY", 1, 100, execution_plan=p)
    thread = Mock()
    thread.is_alive.return_value = False
    monkeypatch.setattr(autopilot, "_thread", None)
    monkeypatch.setattr(autopilot.threading, "Thread", Mock(return_value=thread))
    monkeypatch.setattr(autopilot, "_entry_plans", {})
    snapshot = autopilot.start(Mock(), strategy="chart_confirmed", risk_pct=.4, min_rr=2)
    assert snapshot["plans"]["005930"] == p
    assert snapshot["settings"]["strategy"] == "chart_confirmed"
    assert snapshot["settings"]["account"] == "default"
    assert sim.held_symbols() == ["005930"]


def test_policy_uses_pinned_account_and_skips_used_signals(monkeypatch):
    second = sim.create_account("second")
    sim.select_account("default")
    p = plan()
    pick = {"symbol": "005930", "currency": "KRW", "timing": {"eligible": True, "plan": p}}
    monkeypatch.setattr(autopilot, "_entry_plans", {})
    autopilot._try_chart_entries([pick], {"005930": 100}, 3, 100000, account=second)
    assert sim.held_symbols(account=second) == ["005930"]
    assert sim.held_symbols(account="default") == []
    autopilot._try_exits({}, {"005930": 94}, 3, account=second)
    autopilot._try_chart_entries([pick], {"005930": 100}, 3, 100000, account=second)
    assert sim.held_symbols(account=second) == []
    assert "사용한" in pick["timing"]["entryReason"]


def test_unknown_fx_never_buys_with_fallback(monkeypatch):
    client = Mock()
    client.exchange_rate.return_value = None
    assert autopilot._get_usd_fx(client, strict=True) is None
    assert autopilot._get_usd_fx(client) == 1300
    order = Mock()
    monkeypatch.setattr(sim, "order", order)
    autopilot._try_chart_entries([{"symbol": "AAPL", "currency": "USD", "timing": {"eligible": True, "plan": plan()}}], {"AAPL": 100}, 3, 100000, None)
    order.assert_not_called()


def test_loop_routes_to_chart_policy_with_fresh_prices(monkeypatch):
    p = plan()
    pick = {"symbol": "005930", "name": "QA", "currency": "KRW", "timing": {"eligible": True, "plan": p}, "plan": p, "action": "BUY"}
    client = Mock()
    client.prices.return_value = [{"symbol": "005930", "lastPrice": 100}]
    monkeypatch.setattr(quant, "screen", Mock(return_value={"picks": [pick]}))
    monkeypatch.setattr(autopilot, "_entry_plans", {})
    event = Mock()
    event.is_set.return_value = False
    event.wait.side_effect = lambda delay: setattr(event.is_set, "return_value", True)
    monkeypatch.setattr(autopilot, "_stop_event", event)
    autopilot._run(client, 60, 3, 100000, 10, 300, regime_guard=False, account="default", strategy="chart_confirmed")
    assert quant.screen.call_args.kwargs["strategy"] == "chart_confirmed"
    assert sim.execution_plans()["005930"]["signalId"] == p["signalId"]
    assert len(sim.get_state()["history"]) == 1


def test_stop_during_fill_notification_prevents_the_next_entry(monkeypatch):
    event = Mock()
    event.is_set.return_value = False
    monkeypatch.setattr(autopilot, "_stop_event", event)
    monkeypatch.setattr(autopilot, "_notify_fill", lambda *args, **kwargs: setattr(event.is_set, "return_value", True))
    picks = [{"symbol": symbol, "currency": "KRW", "timing": {"eligible": True,
               "plan": {**plan(), "signalId": symbol}}} for symbol in ("005930", "000660")]
    autopilot._try_chart_entries(picks, {"005930": 100, "000660": 100}, 3, 100000, check_stop=True)
    assert sim.held_symbols() == ["005930"]


def test_strict_regime_rejects_missing_or_stale_components(monkeypatch):
    value = {"stage": "STABLE", "score": 0, "components": [{"key": k, "value": 10} for k in ("vix", "vvix", "spx", "tlt", "uup", "hyg")]}
    monkeypatch.setattr(autopilot.regime, "get_regime", lambda client: value)
    assert autopilot._update_regime(Mock(), strict=True) == "STABLE"
    value["components"][0]["value"] = None
    assert autopilot._update_regime(Mock(), strict=True) is None
    value["components"][0]["value"] = 10
    value["stale"] = True
    assert autopilot._update_regime(Mock(), strict=True) is None


def test_chart_screen_ranks_confirmed_candidates_before_top_n_without_refetch(monkeypatch):
    monkeypatch.setattr(policy, "timing", lambda sym, raw: {"eligible": sym == "B", "exitSignal": False, "plan": plan() if sym == "B" else None})
    monkeypatch.setattr(quant, "_analyze_cached", lambda c, s, n: {"symbol": s, "chartCandles": [], "chartInterval": "1d"})
    monkeypatch.setattr(quant, "extract_factors", lambda f: {})
    monkeypatch.setattr(quant, "trade_plan", lambda f: {})
    monkeypatch.setattr(quant, "quant_score", lambda f, fs: 99 if f["symbol"] == "A" else 10)
    monkeypatch.setattr(quant, "build_reasons", lambda *args: [])
    monkeypatch.setattr(quant, "flow_alert", lambda *args: None)
    client = Mock()
    result = quant.screen(client, universe=["A", "B"], top_n=1, strategy="chart_confirmed")
    assert result["picks"][0]["symbol"] == "B"
    held = quant.screen(client, universe=["A", "B"], top_n=1, strategy="chart_confirmed", include_symbols=["A"])
    assert [p["symbol"] for p in held["picks"]] == ["B", "A"]
    client.candles.assert_not_called()


def test_api_validates_policy_and_passes_settings_without_starting_thread(api, monkeypatch):
    http, module = api
    start = Mock(return_value={"running": False})
    monkeypatch.setattr(module.autopilot, "start", start)
    for bad in ({"strategy": "unknown"}, {"riskPct": 0}, {"minRR": 0}, {"riskPct": "NaN"}):
        assert http.post("/api/autopilot/start", json=bad).status_code == 422
    assert http.post("/api/autopilot/start", json={"strategy": "chart_confirmed", "riskPct": .4, "minRR": 2}).status_code == 200
    assert start.call_args.kwargs["strategy"] == "chart_confirmed"
    assert start.call_args.kwargs["risk_pct"] == .4
    response = http.get("/api/chart-timing/005930")
    assert response.status_code == 200 and response.json()["phase"] == "blocked"
    assert not sim.held_symbols()
