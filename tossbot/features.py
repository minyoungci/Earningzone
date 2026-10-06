"""Features 계약 — 한 종목의 모든 분석 결과를 담는 단일 dict를 생성.

전략(strategies)은 이 Features dict만 보고 시그널을 냅니다. (전략은 API를 직접 호출하지 않음)
"""
from __future__ import annotations
import math
from typing import Dict, List, Optional

from . import divergence as dv
from . import indicators as ind
from . import levels as lv
from . import patterns as pat


def _f(x) -> Optional[float]:
    try:
        value = float(x)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def build_features(symbol: str, name: str, candles_newest_first: List[dict],
                   last_price=None, orderbook: Optional[dict] = None) -> Dict:
    candles = list(reversed(candles_newest_first or []))  # 시간 오름차순
    opens, highs, lows, closes, vols = [], [], [], [], []
    currency = "KRW"
    for c in candles:
        o, h, l, cl = _f(c.get("openPrice")), _f(c.get("highPrice")), _f(c.get("lowPrice")), _f(c.get("closePrice"))
        if None in (o, h, l, cl) or min(o, h, l, cl) <= 0 or h < max(o, cl) or l > min(o, cl):
            continue
        opens.append(o); highs.append(h); lows.append(l); closes.append(cl)
        vols.append(max(0.0, _f(c.get("volume")) or 0.0))
        currency = c.get("currency", currency)

    if len(closes) < 30:
        return {"symbol": symbol, "name": name, "error": "캔들 데이터 부족", "bars": len(closes)}

    price = _f(last_price)
    if price is None or price <= 0:
        price = closes[-1]

    rsi_s = ind.rsi_series(closes, 14)
    macd_s = ind.macd_series(closes)
    macd_hist = macd_s["hist"] if macd_s else []
    # macd hist를 closes 길이에 맞춰 None 패딩(다이버전스 정렬용)
    macd_hist_aligned = [None] * (len(closes) - len(macd_hist)) + list(macd_hist)
    # macd_s 단일 소스에서 마지막 값 구성(ind.macd 중복 호출 제거 — 값 동일)
    macd_now = ({"macd": macd_s["macd"][-1], "signal": macd_s["signal"][-1],
                 "hist": macd_hist[-1]} if macd_hist else None)

    stoch = ind.stochastic(highs, lows, closes)
    stoch_prev = ind.stochastic(highs[:-1], lows[:-1], closes[:-1]) if len(closes) > 14 else None
    boll = ind.bollinger(closes, 20, 2)
    a = ind.atr(highs, lows, closes, 14)
    # 거래량 SMA20을 한 번만 계산해 재사용(중복 호출 제거 + '>0' 명시 비교)
    vol_sma20 = ind.sma(vols, 20)
    vol_ratio = (vols[-1] / vol_sma20 if vol_sma20 is not None and vol_sma20 > 0 else None)

    sr = lv.support_resistance(highs, lows, price)
    piv = lv.pivot_points(highs[-1], lows[-1], closes[-1])
    r52 = lv.range_52w(highs, lows, price)
    diverg = dv.analyze_divergence(closes, rsi_s, macd_hist_aligned)
    cpat = pat.candlestick_patterns(opens, highs, lows, closes)
    struct = pat.chart_structure(highs, lows, closes)

    imb = None
    if orderbook:
        bid = sum((_f(b.get("volume")) or 0) for b in orderbook.get("bids", []))
        ask = sum((_f(x.get("volume")) or 0) for x in orderbook.get("asks", []))
        if bid + ask > 0:
            imb = (bid - ask) / (bid + ask)

    return {
        "symbol": symbol, "name": name, "bars": len(closes), "currency": currency,
        "price": price, "lastClose": closes[-1],
        # 시계열(전략이 필요 시 사용)
        "opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": vols,
        # 이동평균/추세
        "sma5": ind.sma(closes, 5), "sma20": ind.sma(closes, 20),
        "sma60": ind.sma(closes, 60), "sma120": ind.sma(closes, 120),
        "ema12": ind.ema(closes, 12), "ema26": ind.ema(closes, 26),
        "ichimoku": ind.ichimoku(highs, lows, closes), "psar": ind.parabolic_sar(highs, lows),
        "adx": ind.adx(highs, lows, closes),
        # 모멘텀
        "rsi": rsi_s[-1] if rsi_s else None, "rsiPrev": rsi_s[-2] if len(rsi_s) > 1 else None,
        "macd": ({**macd_now, "histPrev": macd_hist[-2]} if (macd_now and len(macd_hist) > 1) else macd_now),
        "stoch": stoch, "stochPrev": stoch_prev,
        "cci": ind.cci(highs, lows, closes), "williamsR": ind.williams_r(highs, lows, closes),
        "roc": ind.roc(closes), "mfi": ind.mfi(highs, lows, closes, vols),
        # 변동성/밴드
        "boll": boll, "keltner": ind.keltner(highs, lows, closes),
        "donchian": ind.donchian(highs, lows), "atr": a,
        "atrPct": (a / price * 100 if a and price else None),
        # 거래량
        "obvSlope": ind.obv_slope(closes, vols), "volRatio": vol_ratio,
        "vwap": ind.vwap(highs, lows, closes, vols),
        # 수익률/이격도
        "ret": {"1": ind.pct_change(closes, 1), "5": ind.pct_change(closes, 5),
                "20": ind.pct_change(closes, 20), "60": ind.pct_change(closes, 60)},
        "disparity20": ind.disparity(closes, 20),
        # 레벨/구조
        "levels": {**sr, "pivots": piv, **r52},
        "divergence": diverg, "candlePatterns": cpat,
        "structure": struct["structure"], "chartPatterns": struct["patterns"],
        "imbalance": imb,
    }
