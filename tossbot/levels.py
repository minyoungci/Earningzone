"""지지/저항(서폿), 스윙 포인트, 피봇, 52주 위치 분석."""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple


def swing_points(highs: List[float], lows: List[float], k: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """프랙탈 스윙: 좌우 k봉보다 높은/낮은 지점. 반환 (swing_highs, swing_lows) = [(idx, price), ...]."""
    sh, sl = [], []
    n = len(highs)
    for i in range(k, n - k):
        # 좌우 대칭 strict: 양쪽 모든 봉보다 엄격히 높아야(낮아야) 스윙으로 인정.
        # 한쪽만 검사하면 플랫탑/플랫바텀에서 누락·중복이 생기므로 좌/우를 동일 규칙으로 통일.
        left_h = highs[i - k:i]
        right_h = highs[i + 1:i + k + 1]
        left_l = lows[i - k:i]
        right_l = lows[i + 1:i + k + 1]
        if all(highs[i] > x for x in left_h) and all(highs[i] > x for x in right_h):
            sh.append((i, highs[i]))
        if all(lows[i] < x for x in left_l) and all(lows[i] < x for x in right_l):
            sl.append((i, lows[i]))
    return sh, sl


def _cluster(levels: List[float], tol: float) -> List[float]:
    """상대거리 tol 이내 레벨을 묶어 평균값으로 대표."""
    if not levels:
        return []
    levels = sorted(levels)
    groups = [[levels[0]]]
    for v in levels[1:]:
        if abs(v - groups[-1][-1]) / groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def support_resistance(highs, lows, price, k=3, tol=0.012, max_levels=4) -> Dict:
    sh, sl = swing_points(highs, lows, k)
    res = _cluster([p for _, p in sh], tol)
    sup = _cluster([p for _, p in sl], tol)
    # 과거 버그: price*1.001 / price*0.999 컷으로 현재가에 가장 가까운(±0.1%) 레벨이 통째로
    # 누락됐다. 갭을 없애고 가격 기준 한쪽으로만 분류한다 — >=price 는 저항, <price 는 지지.
    # 이렇게 하면 근접 레벨이 보존되면서도 각 레벨이 정확히 한쪽에만 속해
    # nearestResistance/nearestSupport 가 실제 최근접을 가리키고 distTo* 가 항상 >=0 이다.
    resistances = sorted([l for l in res if l >= price])[:max_levels]
    supports = sorted([l for l in sup if l < price], reverse=True)[:max_levels]
    nr = resistances[0] if resistances else None
    ns = supports[0] if supports else None
    return {
        "supports": supports,
        "resistances": resistances,
        "nearestSupport": ns,
        "nearestResistance": nr,
        "distToSupport": (price - ns) / price * 100 if ns else None,
        "distToResistance": (nr - price) / price * 100 if nr else None,
    }


def pivot_points(high: float, low: float, close: float) -> Dict:
    p = (high + low + close) / 3
    return {"p": p, "r1": 2 * p - low, "s1": 2 * p - high,
            "r2": p + (high - low), "s2": p - (high - low),
            "r3": high + 2 * (p - low), "s3": low - 2 * (high - p)}


def range_52w(highs, lows, price, bars=252) -> Dict:
    h = highs[-bars:] if len(highs) >= bars else highs
    l = lows[-bars:] if len(lows) >= bars else lows
    hi, lo = max(h), min(l)
    pos = (price - lo) / (hi - lo) * 100 if hi > lo else None
    return {"high52": hi, "low52": lo, "pos52": pos,
            "fromHigh": (price - hi) / hi * 100 if hi else None}
