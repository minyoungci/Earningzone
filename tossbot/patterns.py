"""캔들스틱 패턴 + 차트 구조(추세/이중천장·바닥) 인식.

각 함수는 OHLC float 리스트(시간 오름차순)를 받고, 감지된 패턴을 [{name, bias}] 로 반환.
bias: +1(강세) / -1(약세) / 0(중립).
"""
from __future__ import annotations
from typing import Dict, List

from .levels import swing_points


def _parts(o, h, l, c):
    body = abs(c - o)
    rng = h - l if h > l else 1e-9
    upper = h - max(o, c)
    lower = min(o, c) - l
    return body, rng, upper, lower


def candlestick_patterns(opens, highs, lows, closes) -> List[Dict]:
    out: List[Dict] = []
    n = len(closes)
    if n < 3:
        return out
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    po, ph, pl, pc = opens[-2], highs[-2], lows[-2], closes[-2]
    o2, c2 = opens[-3], closes[-3]
    body, rng, upper, lower = _parts(o, h, l, c)
    pbody = abs(pc - po)

    # 추세 컨텍스트(직전 5봉 방향)
    downtrend = closes[-1] < closes[-min(6, n)] if n >= 6 else False
    uptrend = closes[-1] > closes[-min(6, n)] if n >= 6 else False

    # Doji
    if body <= 0.1 * rng:
        out.append({"name": "도지(Doji)", "bias": 0})
    # Hammer / Hanging man
    if lower >= 2 * body and upper <= body and body > 0:
        out.append({"name": "해머(Hammer)", "bias": +1 if downtrend else 0})
    # Inverted hammer / Shooting star
    if upper >= 2 * body and lower <= body and body > 0:
        out.append({"name": "슈팅스타(Shooting Star)", "bias": -1 if uptrend else 0})
    # Bullish engulfing
    if pc < po and c > o and c >= po and o <= pc and body > pbody:
        out.append({"name": "상승장악형(Bullish Engulfing)", "bias": +1})
    # Bearish engulfing
    if pc > po and c < o and o >= pc and c <= po and body > pbody:
        out.append({"name": "하락장악형(Bearish Engulfing)", "bias": -1})
    # Bullish harami
    if pc < po and c > o and o > pc and c < po:
        out.append({"name": "상승잉태형(Bullish Harami)", "bias": +1})
    # Morning star (3봉)
    if c2 < o2 and abs(pc - po) <= 0.4 * abs(c2 - o2) and c > o and c > (o2 + c2) / 2:
        out.append({"name": "샛별형(Morning Star)", "bias": +1})
    # Evening star (3봉)
    if c2 > o2 and abs(pc - po) <= 0.4 * abs(c2 - o2) and c < o and c < (o2 + c2) / 2:
        out.append({"name": "석별형(Evening Star)", "bias": -1})
    # Marubozu (장대양/음봉)
    if body >= 0.9 * rng:
        out.append({"name": "장대양봉" if c > o else "장대음봉", "bias": +1 if c > o else -1})
    return out


def chart_structure(highs, lows, closes, k=3) -> Dict:
    """스윙 기반 추세 + 이중천장/바닥 감지."""
    sh, sl = swing_points(highs, lows, k)
    structure = "range"
    if len(sh) >= 2 and len(sl) >= 2:
        hh = sh[-1][1] > sh[-2][1]
        hl = sl[-1][1] > sl[-2][1]
        lh = sh[-1][1] < sh[-2][1]
        ll = sl[-1][1] < sl[-2][1]
        if hh and hl:
            structure = "uptrend"
        elif lh and ll:
            structure = "downtrend"

    patterns: List[Dict] = []
    # 이중천장: 최근 두 스윙고점이 1% 이내로 비슷
    if len(sh) >= 2 and abs(sh[-1][1] - sh[-2][1]) / sh[-2][1] <= 0.02:
        patterns.append({"name": "이중천장(Double Top)", "bias": -1})
    if len(sl) >= 2 and abs(sl[-1][1] - sl[-2][1]) / sl[-2][1] <= 0.02:
        patterns.append({"name": "이중바닥(Double Bottom)", "bias": +1})
    return {"structure": structure, "patterns": patterns,
            "swingHighs": [p for _, p in sh[-3:]], "swingLows": [p for _, p in sl[-3:]]}
