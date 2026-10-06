"""Experimental daily long policy. Pure signal/size calculations; sim execution only.

Thresholds are engineering defaults, not calibrated probabilities or performance claims.
Manual drawings, IV assumptions and document success rates never enter this policy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from .chart_study import completed_bars, pivots, retest, study
from .indicators import atr, ema_series
from .sim import FEE_RATE, TAX_RATE

VERSION = "chart-confirmed-v1"


def normalize(rows):
    out = []
    for row in rows:
        try:
            out.append({"time": row["timestamp"][:10],
                        **{k: float(row[src]) for k, src in (
                            ("open", "openPrice"), ("high", "highPrice"),
                            ("low", "lowPrice"), ("close", "closePrice"), ("volume", "volume"))}})
        except (KeyError, TypeError, ValueError, OverflowError):
            out.append({})  # Retain evidence of rejected input; never silently trade it.
    return out


def timing(symbol, rows, now=None):
    now = now or datetime.now(timezone.utc)
    bars, quality = completed_bars(rows, "1d", now)
    result = {"version": VERSION, "symbol": symbol, "phase": "waiting", "eligible": False, "exitSignal": False,
              "reason": "돌파·리테스트·후속 종가 확인 대기", "quality": quality, "plan": None}
    if quality["stale"] or quality["rejected"] or quality["duplicates"] or len(bars) < 60:
        return {**result, "phase": "blocked", "reason": "일봉 부족·지연·오류·중복 데이터"}
    ps = pivots(bars, 3, "wick")
    candidates = []
    for p in [p for p in ps if p["side"] == "high"][-12:]:
        end = p["confirmedIndex"] + 1
        a = atr([b["high"] for b in bars[:end]], [b["low"] for b in bars[:end]],
                [b["close"] for b in bars[:end]])
        if not a or a <= 0:
            continue
        zone = retest(bars, p, a * .25)
        result["phase"] = zone["state"]
        if zone["state"] != "confirmed":
            continue
        conf = next(e["time"] for e in reversed(zone["events"]) if e["state"] == "confirmed")
        ci = next(i for i, b in enumerate(bars) if b["time"] == conf)
        if len(bars) - 1 - ci > 2 or now - datetime.fromisoformat(conf).replace(tzinfo=timezone.utc) > timedelta(days=4):
            result.update(phase="expired", reason="확인 신호 유효 기간 만료")
            continue
        known = [x for x in ps if x["confirmedIndex"] <= ci]
        prior_lows = [x for x in known if x["side"] == "low" and x["index"] < p["index"]]
        if not prior_lows:
            continue
        # Measured swing height, capped by an overhead high known at confirmation.
        target = p["price"] + p["price"] - prior_lows[-1]["price"]
        overhead = [x["price"] for x in known if x["side"] == "high" and x["price"] > bars[ci]["close"]]
        if overhead:
            target = min(target, min(overhead))
        ri = zone["retestIndex"]
        stop = min(bars[ri]["low"], zone["lower"]) - a * .25
        closes = [b["close"] for b in bars[:ci+1]]
        if len(closes) < 50:
            continue
        e20, e50 = ema_series(closes, 20)[-1], ema_series(closes, 50)[-1]
        baseline = sum(b["volume"] for b in bars[ci-20:ci]) / 20
        rvol = bars[ci]["volume"] / baseline if baseline > 0 else 0
        if not (e20 and e50 and closes[-1] > e20 > e50 and rvol >= 1.2 and 0 < stop < closes[-1] < target):
            result.update(phase="filtered", reason="추세 정렬·확인봉 거래량·목표/손절 조건 미달")
            continue
        if any(b["low"] <= stop or b["high"] >= target for b in bars[ci+1:]):
            result.update(phase="invalidated", reason="확인 이후 목표·손절에 이미 도달")
            continue  # Setup has already stopped out or reached its target before entry.
        plan = {"policy": VERSION, "signalId": f"{VERSION}:{symbol}:{conf}", "pivotTime": p["time"],
                "confirmedAt": conf, "expiresAt": (datetime.fromisoformat(conf).replace(tzinfo=timezone.utc) + timedelta(days=4)).isoformat(),
                "stop": stop, "target": target, "entryLow": zone["upper"],
                "entryHigh": closes[-1] + a * .5, "confirmationClose": closes[-1],
                "rvol": rvol, "targetRule": "확인 전 스윙 높이 투영 / 알려진 상단 피벗으로 제한"}
        candidates.append((ci, p["confirmedIndex"], plan))
    view = study(rows, now=now)
    if view["structure"] in ("downtrend", "broken") or any(
            d.get("direction") == "bearish" and not d.get("invalidatedAt") for d in view["divergences"]):
        return {**result, "phase": "blocked", "exitSignal": view["structure"] in ("downtrend", "broken"),
                "reason": "하락 구조·구조 이탈·약세 다이버전스"}
    if not candidates:
        if result["phase"] == "confirmed":
            result.update(phase="filtered", reason="확인 전 스윙 저점·목표 계산 조건 부족")
        return result
    plan = max(candidates, key=lambda x: (x[0], x[1]))[2]
    return {**result, "phase": "confirmed", "eligible": True,
            "reason": "일봉 리테스트 확인 + EMA20/50 상승 정렬 + 확인봉 RVOL ≥ 1.2", "plan": plan}


def entry_size(plan, price, cash, equity, budget, risk_pct=.5, min_rr=1.5, fx=1.0, now=None, open_risk=0, max_positions=3):
    """Net stop loss and target gain use exactly the current sim cost model."""
    now = now or datetime.now(timezone.utc)
    result = {"qty": 0, "reason": "진입 조건 불충족", "netRR": None}
    numbers = (price, cash, equity, budget, risk_pct, min_rr, fx, open_risk)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in numbers):
        return {**result, "reason": "가격·잔고·환율 확인 불가"}
    if min(price, cash, equity, budget, risk_pct, min_rr, fx) <= 0 or open_risk < 0:
        return result
    try:
        expiry = datetime.fromisoformat(plan["expiresAt"])
        if expiry.tzinfo is None:
            raise ValueError("expiry timezone required")
        stop, target, lo, hi = (float(plan[k]) for k in ("stop", "target", "entryLow", "entryHigh"))
    except (KeyError, TypeError, ValueError, OverflowError):
        return result
    if not all(math.isfinite(x) for x in (stop, target, lo, hi)) or now >= expiry:
        return {**result, "reason": "확인 신호 만료·잘못된 계획"}
    if not (0 < stop < price < target and lo <= price <= hi):
        return {**result, "reason": "현재가가 진입 범위 밖 / 목표·손절 도달"}
    cost = price * (1 + FEE_RATE) * fx
    loss = cost - stop * (1 - FEE_RATE - TAX_RATE) * fx
    gain = target * (1 - FEE_RATE - TAX_RATE) * fx - cost
    rr = gain / loss
    if rr < min_rr:
        return {**result, "reason": "비용 반영 순손익비 미달", "netRR": rr}
    per_trade = equity * risk_pct / 100
    risk_budget = min(per_trade, max(0, per_trade * max_positions - open_risk))
    qty = math.floor(min(cash / cost, budget / cost, risk_budget / loss))
    return {"qty": qty, "netRR": rr, "riskKrw": qty * loss,
            "reason": "차트 확인 진입" if qty > 0 else "현금·예산·손절 위험 한도 부족"}
