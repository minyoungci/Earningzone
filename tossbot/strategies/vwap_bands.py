"""VWAP 밴드(VWAP bands) 전략군.

롤링 VWAP(20)과 전형가격(typical price) 표준편차 기반 ±1σ/±2σ 밴드를 직접 계산하여
가격-VWAP 관계, VWAP 회귀/돌파, 밴드 터치 반전, 그리고 최근 스윙 기준 Anchored VWAP
근사를 통해 시그널을 생성한다. 카테고리: meanrev / trend.
"""
from __future__ import annotations
from .base import buy, sell, strategy


# ── 내부 헬퍼(순수 파이썬, 방어적) ───────────────────────────
def _typical(highs, lows, closes):
    n = len(closes)
    return [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]


def _rolling_vwap_bands(highs, lows, closes, vols, period=20, mult1=1.0, mult2=2.0):
    """최근 period 구간의 롤링 VWAP과 거래량가중 분산 기반 ±1σ/±2σ 밴드.

    반환: dict{vwap, sd, upper1, lower1, upper2, lower2} 또는 None(데이터 부족/거래량 0).
    """
    n = len(closes)
    if n < period:
        return None
    tp = _typical(highs, lows, closes)
    num = den = 0.0
    for i in range(n - period, n):
        v = vols[i] if i < len(vols) else 0.0
        if v is None:
            v = 0.0
        num += tp[i] * v
        den += v
    if den <= 0:
        return None
    vwap = num / den
    var = 0.0
    for i in range(n - period, n):
        v = vols[i] if i < len(vols) else 0.0
        if v is None:
            v = 0.0
        var += v * (tp[i] - vwap) ** 2
    sd = (var / den) ** 0.5 if den > 0 else 0.0
    if sd <= 0:
        return None
    return {
        "vwap": vwap, "sd": sd,
        "upper1": vwap + mult1 * sd, "lower1": vwap - mult1 * sd,
        "upper2": vwap + mult2 * sd, "lower2": vwap - mult2 * sd,
    }


def _anchored_vwap(highs, lows, closes, vols, anchor_idx):
    """anchor_idx(포함)부터 마지막까지의 Anchored VWAP. 데이터 부족 시 None."""
    n = len(closes)
    if anchor_idx is None or anchor_idx < 0 or anchor_idx >= n:
        return None
    tp = _typical(highs, lows, closes)
    num = den = 0.0
    for i in range(anchor_idx, n):
        v = vols[i] if i < len(vols) else 0.0
        if v is None:
            v = 0.0
        num += tp[i] * v
        den += v
    if den <= 0:
        return None
    return num / den


def _last_swing_low_idx(lows, lookback=40):
    """최근 lookback 구간의 최저점 인덱스(스윙 저점 근사)."""
    n = len(lows)
    if n == 0:
        return None
    start = max(0, n - lookback)
    idx = start
    lo = lows[start]
    for i in range(start, n):
        if lows[i] <= lo:
            lo = lows[i]; idx = i
    return idx


def _last_swing_high_idx(highs, lookback=40):
    """최근 lookback 구간의 최고점 인덱스(스윙 고점 근사)."""
    n = len(highs)
    if n == 0:
        return None
    start = max(0, n - lookback)
    idx = start
    hi = highs[start]
    for i in range(start, n):
        if highs[i] >= hi:
            hi = highs[i]; idx = i
    return idx


# ── 전략 1: 가격-VWAP 관계(추세 편향) ────────────────────────
@strategy("VWAP 추세 편향", "trend")
def vwap_trend_bias(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]; vols = f["volumes"]
    if len(closes) < 22:
        return None
    price = f.get("price") or closes[-1]
    b = _rolling_vwap_bands(highs, lows, closes, vols, 20)
    if not b:
        return None
    vwap, sd = b["vwap"], b["sd"]
    if vwap <= 0 or sd <= 0:
        return None
    dist = (price - vwap) / sd  # σ 단위 이격
    # 1σ 이내 밴드 안에서의 추세 편향만 사용(밴드 밖은 반전 전략이 처리)
    if 0.15 < dist <= 1.0:
        return buy("VWAP 위 추세", "trend", min(1.0, 0.4 + dist * 0.3),
                   f"가격이 VWAP 위 +{dist:.2f}σ")
    if -1.0 <= dist < -0.15:
        return sell("VWAP 아래 추세", "trend", min(1.0, 0.4 + (-dist) * 0.3),
                    f"가격이 VWAP 아래 {dist:.2f}σ")
    return None


# ── 전략 2: VWAP 회귀(mean reversion to VWAP) ────────────────
@strategy("VWAP 회귀", "meanrev")
def vwap_mean_reversion(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]; vols = f["volumes"]
    if len(closes) < 22:
        return None
    price = f.get("price") or closes[-1]
    b = _rolling_vwap_bands(highs, lows, closes, vols, 20)
    if not b:
        return None
    vwap, sd = b["vwap"], b["sd"]
    if sd <= 0:
        return None
    dist = (price - vwap) / sd
    # 1σ~2σ 이격 시 VWAP으로의 회귀를 노림(과도 이격은 추세로 보고 제외)
    if -2.0 <= dist <= -1.0:
        return buy("VWAP 하방 회귀", "meanrev", min(1.0, 0.45 + (-dist - 1.0) * 0.4),
                   f"VWAP 대비 {dist:.2f}σ 저평가→회귀 기대")
    if 1.0 <= dist <= 2.0:
        return sell("VWAP 상방 회귀", "meanrev", min(1.0, 0.45 + (dist - 1.0) * 0.4),
                    f"VWAP 대비 +{dist:.2f}σ 고평가→회귀 기대")
    return None


# ── 전략 3: VWAP 돌파(전일 종가→당일 VWAP 상/하향 교차) ──────
@strategy("VWAP 돌파", "trend")
def vwap_cross(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]; vols = f["volumes"]
    if len(closes) < 23:
        return None
    price = f.get("price") or closes[-1]
    prev_close = closes[-2]
    b_now = _rolling_vwap_bands(highs, lows, closes, vols, 20)
    b_prev = _rolling_vwap_bands(highs[:-1], lows[:-1], closes[:-1], vols[:-1], 20)
    if not b_now or not b_prev:
        return None
    vw_now, vw_prev = b_now["vwap"], b_prev["vwap"]
    # 직전 봉은 VWAP 아래, 현재가는 VWAP 위로 상향 교차
    if prev_close <= vw_prev and price > vw_now:
        return buy("VWAP 상향돌파", "trend", 0.6, "종가가 VWAP 상향 교차")
    if prev_close >= vw_prev and price < vw_now:
        return sell("VWAP 하향돌파", "trend", 0.6, "종가가 VWAP 하향 교차")
    return None


# ── 전략 4: 밴드 터치 반전(±2σ 터치 후 되돌림) ──────────────
@strategy("VWAP 밴드 반전", "meanrev")
def vwap_band_reversal(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]; vols = f["volumes"]
    if len(closes) < 22:
        return None
    price = f.get("price") or closes[-1]
    b = _rolling_vwap_bands(highs, lows, closes, vols, 20)
    if not b:
        return None
    # 저가가 하단 2σ를 찍고 현재가는 다시 그 위로 복귀 → 매수 반전
    if lows[-1] <= b["lower2"] and price > b["lower2"]:
        return buy("하단밴드 반전", "meanrev", 0.65, "VWAP -2σ 터치 후 복귀")
    # 고가가 상단 2σ를 찍고 현재가는 다시 그 아래로 복귀 → 매도 반전
    if highs[-1] >= b["upper2"] and price < b["upper2"]:
        return sell("상단밴드 반전", "meanrev", 0.65, "VWAP +2σ 터치 후 복귀")
    return None


# ── 전략 5: 밴드 워크(상/하단 밴드 돌파 추세 추종) ───────────
@strategy("VWAP 밴드 워크", "trend")
def vwap_band_walk(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]; vols = f["volumes"]
    if len(closes) < 22:
        return None
    price = f.get("price") or closes[-1]
    b = _rolling_vwap_bands(highs, lows, closes, vols, 20)
    if not b:
        return None
    vwap, sd = b["vwap"], b["sd"]
    if sd <= 0:
        return None
    # 종가가 상단 1σ 위에서 마감하며 직전봉보다 상승 → 추세 지속
    if price > b["upper1"] and price <= b["upper2"] and closes[-1] > closes[-2]:
        return buy("상단밴드 워크", "trend", 0.5, "VWAP +1σ 위 추세 지속")
    if price < b["lower1"] and price >= b["lower2"] and closes[-1] < closes[-2]:
        return sell("하단밴드 워크", "trend", 0.5, "VWAP -1σ 아래 추세 지속")
    return None


# ── 전략 6: Anchored VWAP(최근 스윙 기준) 지지/저항 ─────────
@strategy("Anchored VWAP", "trend")
def anchored_vwap_strat(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]; vols = f["volumes"]
    if len(closes) < 25:
        return None
    price = f.get("price") or closes[-1]
    atr = f.get("atr")
    # 근사 톨러런스: ATR이 있으면 0.5*ATR, 없으면 가격의 0.5%
    tol = (0.5 * atr) if atr else (price * 0.005)
    if tol <= 0:
        return None

    lo_idx = _last_swing_low_idx(lows, 40)
    hi_idx = _last_swing_high_idx(highs, 40)
    avwap_lo = _anchored_vwap(highs, lows, closes, vols, lo_idx)
    avwap_hi = _anchored_vwap(highs, lows, closes, vols, hi_idx)

    # 스윙 저점 기준 AVWAP은 상승 추세의 지지선 역할: 위에서 근접 후 반등
    if avwap_lo is not None and lo_idx is not None and lo_idx < len(closes) - 3:
        if price >= avwap_lo and (price - avwap_lo) <= tol and closes[-1] >= closes[-2]:
            return buy("AVWAP 지지", "trend", 0.55, "스윙저점 AVWAP 지지선 반등")
    # 스윙 고점 기준 AVWAP은 하락 추세의 저항선 역할: 아래에서 근접 후 반락
    if avwap_hi is not None and hi_idx is not None and hi_idx < len(closes) - 3:
        if price <= avwap_hi and (avwap_hi - price) <= tol and closes[-1] <= closes[-2]:
            return sell("AVWAP 저항", "trend", 0.55, "스윙고점 AVWAP 저항선 반락")
    return None
