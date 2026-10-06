"""추세 확장(trend) 전략군 — Hull MA, DEMA/TEMA, 선형회귀 기울기, MA 리본, KAMA, Donchian 중심선.

표준 라이브러리만 사용하며, 여기서 필요한 보조 지표는 순수 파이썬으로 직접 구현합니다.
모든 전략은 데이터 부족 시 None을 반환합니다(예외 던지지 않음).
"""
from __future__ import annotations
from typing import List, Optional

from .. import indicators as ind
from .base import buy, sell, strategy


# ── 보조 지표(모듈 내부 순수 구현) ───────────────────────────
def _wma_series(values: List[float], period: int) -> List[float]:
    """가중이동평균(WMA) 시계열. 길이 = len-period+1."""
    n = len(values)
    if period <= 0 or n < period:
        return []
    denom = period * (period + 1) / 2.0
    out: List[float] = []
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1]
        s = 0.0
        for j, v in enumerate(window):
            s += v * (j + 1)
        out.append(s / denom)
    return out


def _hull_series(values: List[float], period: int) -> List[float]:
    """Hull Moving Average 시계열."""
    if period < 2 or len(values) < period:
        return []
    half = max(1, period // 2)
    sqrt_p = max(1, int(round(period ** 0.5)))
    wma_half = _wma_series(values, half)
    wma_full = _wma_series(values, period)
    if not wma_half or not wma_full:
        return []
    # 두 WMA 길이 정렬(짧은 쪽 기준)
    m = min(len(wma_half), len(wma_full))
    wma_half = wma_half[-m:]
    wma_full = wma_full[-m:]
    raw = [2 * wma_half[i] - wma_full[i] for i in range(m)]
    if len(raw) < sqrt_p:
        return []
    return _wma_series(raw, sqrt_p)


def _dema_series(values: List[float], period: int) -> List[float]:
    """Double EMA 시계열."""
    e1 = ind.ema_series(values, period)
    if not e1:
        return []
    e2 = ind.ema_series(e1, period)
    if not e2:
        return []
    m = len(e2)
    e1_tail = e1[-m:]
    return [2 * e1_tail[i] - e2[i] for i in range(m)]


def _tema_series(values: List[float], period: int) -> List[float]:
    """Triple EMA 시계열."""
    e1 = ind.ema_series(values, period)
    if not e1:
        return []
    e2 = ind.ema_series(e1, period)
    if not e2:
        return []
    e3 = ind.ema_series(e2, period)
    if not e3:
        return []
    m = len(e3)
    e1_tail = e1[-m:]
    e2_tail = e2[-m:]
    return [3 * e1_tail[i] - 3 * e2_tail[i] + e3[i] for i in range(m)]


def _linreg_slope(values: List[float], period: int) -> Optional[float]:
    """최근 period개에 대한 최소제곱 회귀 기울기(가격/봉). 부족 시 None."""
    if len(values) < period or period < 2:
        return None
    y = values[-period:]
    n = period
    sx = n * (n - 1) / 2.0
    sxx = (n - 1) * n * (2 * n - 1) / 6.0
    sy = sum(y)
    sxy = sum(i * y[i] for i in range(n))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


def _kama_series(values: List[float], er_period: int = 10,
                 fast: int = 2, slow: int = 30) -> List[float]:
    """Kaufman Adaptive Moving Average 시계열."""
    n = len(values)
    if n < er_period + 1:
        return []
    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    kama = values[er_period]
    out = [kama]
    for i in range(er_period + 1, n):
        change = abs(values[i] - values[i - er_period])
        vol = 0.0
        for j in range(i - er_period + 1, i + 1):
            vol += abs(values[j] - values[j - 1])
        er = change / vol if vol else 0.0
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama = kama + sc * (values[i] - kama)
        out.append(kama)
    return out


# ── 전략 ──────────────────────────────────────────────────
@strategy("Hull MA 크로스", "trend")
def hull_cross(f):
    cl = f["closes"]
    if not cl or len(cl) < 30:
        return None
    h = _hull_series(cl, 16)
    if len(h) < 2:
        return None
    p = f.get("price")
    if p is None:
        p = cl[-1]
    if h[-2] <= cl[-2] and p > h[-1]:
        return buy("Hull MA 크로스", "trend", 0.6, "가격이 HullMA(16) 상향돌파")
    if h[-2] >= cl[-2] and p < h[-1]:
        return sell("Hull MA 크로스", "trend", 0.6, "가격이 HullMA(16) 하향돌파")
    # 크로스 없으면 기울기 기반 추세
    if h[-1] > h[-2] and p > h[-1]:
        return buy("Hull MA 추세", "trend", 0.45, "HullMA 상승·가격 위")
    if h[-1] < h[-2] and p < h[-1]:
        return sell("Hull MA 추세", "trend", 0.45, "HullMA 하락·가격 아래")
    return None


@strategy("DEMA/TEMA 크로스", "trend")
def dema_tema_cross(f):
    cl = f["closes"]
    if not cl or len(cl) < 40:
        return None
    dema = _dema_series(cl, 20)
    tema = _tema_series(cl, 20)
    if len(dema) < 2 or len(tema) < 2:
        return None
    m = min(len(dema), len(tema))
    if m < 2:
        return None
    d, dp = dema[-1], dema[-2]
    t, tp = tema[-1], tema[-2]
    if tp <= dp and t > d:
        return buy("DEMA/TEMA 골든크로스", "trend", 0.65, "TEMA가 DEMA 상향돌파")
    if tp >= dp and t < d:
        return sell("DEMA/TEMA 데드크로스", "trend", 0.65, "TEMA가 DEMA 하향돌파")
    return None


@strategy("선형회귀 기울기(20)", "trend")
def linreg_slope(f):
    cl = f["closes"]
    if not cl or len(cl) < 22:
        return None
    slope = _linreg_slope(cl, 20)
    if slope is None:
        return None
    p = cl[-1]
    if p <= 0:
        return None
    # 봉당 기울기를 가격 대비 비율(%)로 정규화
    norm = slope / p * 100
    if norm > 0.15:
        return buy("선형회귀 기울기↑", "trend", min(1.0, norm / 0.8 + 0.3), f"20봉 회귀 우상향({norm:+.2f}%/봉)")
    if norm < -0.15:
        return sell("선형회귀 기울기↓", "trend", min(1.0, -norm / 0.8 + 0.3), f"20봉 회귀 우하향({norm:+.2f}%/봉)")
    return None


@strategy("MA 리본 정렬(5/10/20/60)", "trend")
def ma_ribbon(f):
    cl = f["closes"]
    if not cl or len(cl) < 60:
        return None
    periods = [5, 10, 20, 60]
    mas = [ind.sma(cl, p) for p in periods]
    if any(m is None for m in mas):
        return None
    # 인접 쌍의 정렬 방향 집계
    n_pairs = len(mas) - 1
    up = sum(1 for i in range(n_pairs) if mas[i] > mas[i + 1])
    dn = sum(1 for i in range(n_pairs) if mas[i] < mas[i + 1])
    if up == n_pairs:
        return buy("MA 리본 정배열", "trend", 0.75, "5>10>20>60 완전 정배열")
    if dn == n_pairs:
        return sell("MA 리본 역배열", "trend", 0.75, "5<10<20<60 완전 역배열")
    if up == n_pairs - 1 and mas[0] > mas[-1]:
        return buy("MA 리본 정렬↑", "trend", 0.45, f"리본 상향 정렬도 {up}/{n_pairs}")
    if dn == n_pairs - 1 and mas[0] < mas[-1]:
        return sell("MA 리본 정렬↓", "trend", 0.45, f"리본 하향 정렬도 {dn}/{n_pairs}")
    return None


@strategy("KAMA 추세", "trend")
def kama_trend(f):
    cl = f["closes"]
    if not cl or len(cl) < 30:
        return None
    k = _kama_series(cl, 10, 2, 30)
    if len(k) < 2:
        return None
    p = f.get("price")
    if p is None:
        p = cl[-1]
    rising = k[-1] > k[-2]
    falling = k[-1] < k[-2]
    if p > k[-1] and rising:
        return buy("KAMA 추세", "trend", 0.55, "가격>KAMA·KAMA 상승")
    if p < k[-1] and falling:
        return sell("KAMA 추세", "trend", 0.55, "가격<KAMA·KAMA 하락")
    # 가격이 KAMA를 막 돌파(추세전환 초기)
    if k[-2] >= cl[-2] and p > k[-1]:
        return buy("KAMA 돌파", "trend", 0.45, "가격이 KAMA 상향돌파")
    if k[-2] <= cl[-2] and p < k[-1]:
        return sell("KAMA 이탈", "trend", 0.45, "가격이 KAMA 하향이탈")
    return None


@strategy("Donchian 중심선", "trend")
def donchian_mid(f):
    cl = f["closes"]
    highs = f["highs"]
    lows = f["lows"]
    if not cl or len(cl) < 22:
        return None
    period = 20
    dc = ind.donchian(highs, lows, period)
    dc_prev = ind.donchian(highs[:-1], lows[:-1], period)
    if not dc or not dc_prev:
        return None
    mid = (dc["upper"] + dc["lower"]) / 2.0
    mid_prev = (dc_prev["upper"] + dc_prev["lower"]) / 2.0
    p = f.get("price")
    if p is None:
        p = cl[-1]
    rising = mid > mid_prev
    falling = mid < mid_prev
    if p > mid and rising:
        return buy("Donchian 중심선↑", "trend", 0.55, "가격>중심선·중심선 상승")
    if p < mid and falling:
        return sell("Donchian 중심선↓", "trend", 0.55, "가격<중심선·중심선 하락")
    # 중심선 돌파(추세 시작)
    if cl[-2] <= mid_prev and p > mid:
        return buy("Donchian 중심선 돌파", "trend", 0.45, "가격이 중심선 상향돌파")
    if cl[-2] >= mid_prev and p < mid:
        return sell("Donchian 중심선 이탈", "trend", 0.45, "가격이 중심선 하향이탈")
    return None
