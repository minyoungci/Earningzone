"""Causal OHLCV chart studies. Pure calculations, no orders."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from statistics import stdev

from .indicators import atr, ema_series, macd_series, rsi_series

VERSION = "financial-study-v1"


def _stamp(value, interval):
    if not isinstance(value, str):
        raise ValueError("time must be ISO text")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if interval == "1d":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        raise ValueError("minute timezone missing")
    return dt.astimezone(timezone.utc)


def completed_bars(rows, interval="1d", now=None):
    """Daily: date strictly before UTC today; minute: timestamp + 1 min <= now.

    Provider has no completed flag. Same-date daily bars are conservatively omitted,
    even after an exchange closes. Unknown minute timezones are rejected.
    """
    now = now or datetime.now(timezone.utc)
    unique, rejected = {}, 0
    for row in rows:
        try:
            stamp = _stamp(row["time"], interval)
            values = {k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}
            if not all(math.isfinite(v) for v in values.values()):
                raise ValueError("nonfinite")
            o, h, l, c, v = (values[k] for k in ("open", "high", "low", "close", "volume"))
            if min(o, h, l, c) <= 0 or v < 0 or not l <= min(o, c) <= max(o, c) <= h:
                raise ValueError("invalid OHLCV")
            unique[stamp] = {"time": stamp.date().isoformat() if interval == "1d" else stamp.isoformat(), **values}
        except (ValueError, TypeError, KeyError, OverflowError):
            rejected += 1
    duration = timedelta(days=1) if interval == "1d" else timedelta(minutes=1)
    closed = [r for t, r in sorted(unique.items()) if t + duration <= now]
    excluded = len(unique) - len(closed)
    last = _stamp(closed[-1]["time"], interval) if closed else None
    stale = last is None or now - last > (timedelta(days=7) if interval == "1d" else timedelta(minutes=15))
    return closed, {"received": len(rows), "valid": len(unique), "closed": len(closed),
                    "rejected": rejected, "duplicates": len(rows) - rejected - len(unique),
                    "unclosed": excluded, "stale": stale, "asOf": now.isoformat(),
                    "closurePolicy": "이전 UTC 날짜의 일봉 / 시간대가 있는 분봉의 시작 시각 + 1분"}


def pivots(bars, span=3, basis="wick"):
    out, last = [], {}
    highs = [b["high"] if basis == "wick" else max(b["open"], b["close"]) for b in bars]
    lows = [b["low"] if basis == "wick" else min(b["open"], b["close"]) for b in bars]
    for i in range(span, len(bars) - span):
        for side, values in (("high", highs), ("low", lows)):
            others = values[i-span:i] + values[i+1:i+span+1]
            is_pivot = all(values[i] > v for v in others) if side == "high" else all(values[i] < v for v in others)
            if not is_pivot:
                continue
            old = last.get(side)
            label = "H" if side == "high" else "L"
            if old is not None:
                label = ("HH" if values[i] > old else "LH" if values[i] < old else "EH") if side == "high" else ("HL" if values[i] > old else "LL" if values[i] < old else "EL")
            out.append({"index": i, "side": side, "price": values[i], "label": label,
                        "time": bars[i]["time"], "confirmedAt": bars[i+span]["time"], "confirmedIndex": i+span})
            last[side] = values[i]
    return out


def retest(bars, pivot, width):
    """Fixed zone established at pivot confirmation; distinct later-bar stages."""
    up = pivot["side"] == "high"
    level = pivot["price"]
    lower, upper = level - width, level + width
    first = bars[pivot["confirmedIndex"]]
    state, events, touches, touching = "watching", [], 0, first["low"] <= upper and first["high"] >= lower
    breakout_i, retest_i = None, None
    for i in range(pivot["confirmedIndex"] + 1, len(bars)):
        b, prev = bars[i], bars[i-1]
        touch = b["low"] <= upper and b["high"] >= lower
        if touch and not touching:
            touches += 1
        touching = touch
        beyond = b["close"] > upper if up else b["close"] < lower
        failed = b["close"] < lower if up else b["close"] > upper
        crossed = beyond and (prev["close"] <= upper if up else prev["close"] >= lower)
        if state in ("watching", "invalidated", "expired") and crossed:
            state, breakout_i, retest_i = "breakout", i, None
        elif state in ("breakout", "retest", "confirmed"):
            if failed:
                state = "invalidated"
            elif state != "confirmed" and i - breakout_i > 20:
                state = "expired"
            elif state == "breakout" and touch and beyond:
                state, retest_i = "retest", i
            elif state == "retest" and beyond and (b["close"] > bars[retest_i]["high"] if up else b["close"] < bars[retest_i]["low"]):
                state = "confirmed"
            else:
                continue
        else:
            continue
        events.append({"state": state, "time": b["time"]})
    return {"lower": lower, "upper": upper, "price": level, "direction": "up" if up else "down",
            "state": state, "events": events[-8:], "independentTouches": touches,
            "breakoutIndex": breakout_i, "retestIndex": retest_i,
            "establishedAt": pivot["confirmedAt"], "pivotTime": pivot["time"],
            "width": width, "widthRule": "확인 시점 ATR14 × 0.25 (반폭)"}


def study(rows, interval="1d", span=3, basis="wick", now=None):
    if interval not in ("1d", "1m") or basis not in ("wick", "body") or not 2 <= span <= 10:
        raise ValueError("unsupported study parameter")
    bars, quality = completed_bars(rows, interval, now)
    result = {"version": VERSION, "interval": interval, "basis": basis, "span": span,
              "quality": quality, "candles": bars, "pivots": [], "zones": [], "overlays": [],
              "structure": "insufficient", "divergences": [], "metrics": {}, "gap": None,
              "sourceDocs": ["CHART_METHODS", "TRADING_POLICY", "RISK_AND_BACKTEST"]}
    if not bars:
        return result
    closes, highs, lows = ([b[k] for b in bars] for k in ("close", "high", "low"))
    volumes = [b["volume"] for b in bars]
    ps = pivots(bars, span, basis)
    result["pivots"] = ps
    by_side = {side: [p for p in ps if p["side"] == side] for side in ("high", "low")}
    hs, ls = by_side["high"], by_side["low"]
    if len(hs) >= 2 and len(ls) >= 2:
        result["structure"] = "uptrend" if hs[-1]["label"] == "HH" and ls[-1]["label"] == "HL" else "downtrend" if hs[-1]["label"] == "LH" and ls[-1]["label"] == "LL" else "mixed"
        if (result["structure"] == "uptrend" and closes[-1] < ls[-1]["price"]) or (result["structure"] == "downtrend" and closes[-1] > hs[-1]["price"]):
            result["structure"] = "broken"
    for side in (hs, ls):
        if not side:
            continue
        p = side[-1]
        end = p["confirmedIndex"] + 1
        a = atr(highs[:end], lows[:end], closes[:end])
        if a is not None and a > 0:
            result["zones"].append(retest(bars, p, a * .25))
    for period, color in ((8, "#e09b31"), (20, "#c6962e"), (21, "#7b61c9"), (50, "#428fa3"), (60, "#9584b8"), (200, "#78838d")):
        for kind in ("EMA", "SMA"):
            values = ema_series(closes, period) if kind == "EMA" else [sum(closes[i-period+1:i+1])/period for i in range(period-1, len(closes))]
            start = period - 1
            result["overlays"].append({"label": f"{kind}{period}", "color": color,
                                       "data": [{"time": bars[start+i]["time"], "value": v} for i, v in enumerate(values)]})
    rsi = rsi_series(closes)
    macd = macd_series(closes)
    macd_line = [None] * len(closes)
    if macd:
        macd_line[-len(macd["macd"]):] = macd["macd"]
    for side, direction in ((ls, "bullish"), (hs, "bearish")):
        if len(side) < 2:
            continue
        a, b = side[-2:]
        pa, pb = a["price"], b["price"]
        for name, series in (("RSI14", rsi), ("MACD12/26/9 line", macd_line)):
            ia, ib = series[a["index"]], series[b["index"]]
            if ia is None or ib is None:
                continue
            found = pb < pa and ib > ia if direction == "bullish" else pb > pa and ib < ia
            if found:
                violations = [i for i in range(b["confirmedIndex"]+1, len(bars)) if (closes[i] < pb if direction == "bullish" else closes[i] > pb)]
                invalidated = bool(violations)
                result["divergences"].append({"indicator": name, "direction": direction,
                                               "state": "invalidated" if invalidated else "candidate",
                                               "from": a["time"], "to": b["time"], "availableAt": b["confirmedAt"],
                                               "invalidatedAt": bars[violations[0]]["time"] if violations else None,
                                               "priceA": pa, "priceB": pb, "valueA": ia, "valueB": ib})
    n = len(bars)
    rvol = volumes[-1] / (sum(volumes[-21:-1])/20) if n >= 21 and sum(volumes[-21:-1]) > 0 else None
    # Each historical observation uses only its own prior 20 bars / prior ATR.
    distribution = []
    for i in range(max(20, n-20), n):
        base = sum(volumes[i-20:i])/20
        a = atr(highs[:i], lows[:i], closes[:i])
        if base > 0 and a and volumes[i]/base >= 1.5 and bars[i]["open"]-bars[i]["close"] >= a:
            distribution.append(bars[i]["time"])
    balance = None
    if n >= 21 and sum(volumes[-20:]) > 0:
        balance = sum(volumes[i] * (1 if closes[i] > closes[i-1] else -1 if closes[i] < closes[i-1] else 0) for i in range(n-20, n)) / sum(volumes[-20:])
    rv = stdev([math.log(closes[i]/closes[i-1]) for i in range(n-20, n)]) if n >= 21 else None
    result["metrics"] = {"rvol20": rvol, "directionVolume20": balance, "distributionDates": distribution if n >= 21 else None,
                         "atr14": atr(highs, lows, closes), "rsi14": rsi[-1],
                         "realizedVol20": rv * math.sqrt(252) if rv is not None and interval == "1d" else rv,
                         "volUnit": "annualized252" if interval == "1d" else "perMinuteBar",
                         "low": min(lows), "high": max(highs), "start": bars[0]["time"], "end": bars[-1]["time"]}
    if n >= 16:
        prior_atr = atr(highs[:-1], lows[:-1], closes[:-1])
        last, prev = bars[-1], bars[-2]
        result["gap"] = {"time": last["time"], "gapATR": (last["open"]-prev["close"])/prior_atr if prior_atr else None,
                         "closeLocation": (last["close"]-last["low"])/(last["high"]-last["low"]) if last["high"] > last["low"] else None,
                         "heldUpGap": last["open"] > prev["close"] and last["low"] > prev["close"],
                         "earningsVerified": False}
    return result
