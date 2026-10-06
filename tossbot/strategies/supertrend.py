"""추세전환(trend) 전략군 — Supertrend, Aroon, Vortex, TRIX, DMI.

ind에 없는 지표는 모듈 내부에서 순수 파이썬으로 직접 구현한다.
모든 함수는 데이터 부족·None 상황에서 None을 반환(예외를 던지지 않음).
"""
from __future__ import annotations
from typing import List, Optional

from .. import indicators as ind
from .base import buy, sell, strategy


# ── 내부 지표 구현 ────────────────────────────────────────
def _supertrend_dir(highs, lows, closes, period=10, mult=3.0):
    """Supertrend 추세 방향 시계열. 1=상승, -1=하락. 데이터 부족 시 None."""
    n = len(closes)
    if n < period + 2:
        return None
    tr = ind.true_range_series(highs, lows, closes)  # 길이 n
    # Wilder ATR 시계열
    atr = [None] * n
    if len(tr) <= period:
        return None
    a = sum(tr[1:period + 1]) / period
    atr[period] = a
    for i in range(period + 1, n):
        a = (a * (period - 1) + tr[i]) / period
        atr[i] = a

    upper = [None] * n
    lower = [None] * n
    direction = [None] * n  # 1 상승 / -1 하락
    st = [None] * n
    for i in range(period, n):
        if atr[i] is None:
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        bu = hl2 + mult * atr[i]
        bl = hl2 - mult * atr[i]
        if upper[i - 1] is None:
            upper[i] = bu
            lower[i] = bl
            # 첫 봉 방향 시드: 중앙선(hl2) 기준. lower band 기준은 거의 항상 참이라
            # direction 이 상시 1(상승)로 상방 편향되므로 hl2 로 비교해 편향 제거.
            direction[i] = 1 if closes[i] >= hl2 else -1
            st[i] = lower[i] if direction[i] == 1 else upper[i]
            continue
        # 밴드 잠금 규칙
        upper[i] = bu if (bu < upper[i - 1] or closes[i - 1] > upper[i - 1]) else upper[i - 1]
        lower[i] = bl if (bl > lower[i - 1] or closes[i - 1] < lower[i - 1]) else lower[i - 1]
        prev_dir = direction[i - 1]
        if prev_dir == 1:
            direction[i] = -1 if closes[i] < lower[i] else 1
        else:
            direction[i] = 1 if closes[i] > upper[i] else -1
        # 추세 전환 시 새로 활성화된 반대 밴드를 현재 basic 밴드로 리셋(표준 TradingView 규칙).
        # 직전 추세 동안 잠긴 stale 밴드를 그대로 쓰면 전환 직후 한 봉 지연이 생기므로,
        # 전환 봉에서 곧바로 현재 basic 밴드(bu/bl)를 stop 으로 채택한다.
        if direction[i] != prev_dir:
            if direction[i] == 1:
                lower[i] = bl
                st[i] = lower[i]
            else:
                upper[i] = bu
                st[i] = upper[i]
        else:
            st[i] = lower[i] if direction[i] == 1 else upper[i]
    # 마지막 유효 방향 두 개 반환
    dirs = [d for d in direction if d is not None]
    if len(dirs) < 2:
        return None
    return dirs


def _aroon(highs, lows, period=25):
    """Aroon Up/Down (현재·직전). 반환 (up, down, upPrev, downPrev) 또는 None."""
    n = len(highs)
    if n < period + 2:
        return None

    def calc(hs, ls):
        win_h = hs[-(period + 1):]
        win_l = ls[-(period + 1):]
        # 최근 period+1개 중 최고/최저가 나온 위치(현재로부터 몇 봉 전)
        hh_idx = max(range(len(win_h)), key=lambda i: win_h[i])
        ll_idx = min(range(len(win_l)), key=lambda i: win_l[i])
        since_high = (len(win_h) - 1) - hh_idx
        since_low = (len(win_l) - 1) - ll_idx
        up = 100.0 * (period - since_high) / period
        down = 100.0 * (period - since_low) / period
        return up, down

    up, down = calc(highs, lows)
    up_p, down_p = calc(highs[:-1], lows[:-1])
    return up, down, up_p, down_p


def _vortex(highs, lows, closes, period=14):
    """Vortex VI+ / VI-. 반환 (vi_plus, vi_minus, vp_prev, vm_prev) 또는 None."""
    n = len(closes)
    if n < period + 2:
        return None
    vm_plus, vm_minus, tr = [], [], []
    for i in range(1, n):
        vm_plus.append(abs(highs[i] - lows[i - 1]))
        vm_minus.append(abs(lows[i] - highs[i - 1]))
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    if len(tr) < period + 1:
        return None

    def vi(end):
        s_tr = sum(tr[end - period:end])
        if s_tr == 0:
            return None, None
        vp = sum(vm_plus[end - period:end]) / s_tr
        vm = sum(vm_minus[end - period:end]) / s_tr
        return vp, vm

    vp, vm = vi(len(tr))
    vp_p, vm_p = vi(len(tr) - 1)
    if None in (vp, vm, vp_p, vm_p):
        return None
    return vp, vm, vp_p, vm_p


def _trix(closes, period=15):
    """TRIX (삼중 EMA의 변화율, %). 반환 (trix, trixPrev) 또는 None."""
    if len(closes) < period * 3 + 2:
        return None
    e1 = ind.ema_series(closes, period)
    if len(e1) < period:
        return None
    e2 = ind.ema_series(e1, period)
    if len(e2) < period:
        return None
    e3 = ind.ema_series(e2, period)
    if len(e3) < 3:
        return None

    def roc(seq, idx):
        prev = seq[idx - 1]
        if prev == 0:
            return None
        return 100.0 * (seq[idx] - prev) / prev

    t = roc(e3, len(e3) - 1)
    tp = roc(e3, len(e3) - 2)
    if t is None or tp is None:
        return None
    return t, tp


# ── 전략 ──────────────────────────────────────────────────
@strategy("Supertrend 전환", "trend")
def supertrend_flip(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]
    if len(closes) < 20:
        return None
    dirs = _supertrend_dir(highs, lows, closes, 10, 3.0)
    if not dirs or len(dirs) < 2:
        return None
    cur, prev = dirs[-1], dirs[-2]
    if prev < 0 and cur > 0:
        return buy("Supertrend 상승전환", "trend", 0.7, "Supertrend 하락→상승 전환")
    if prev > 0 and cur < 0:
        return sell("Supertrend 하락전환", "trend", 0.7, "Supertrend 상승→하락 전환")
    return None


@strategy("Supertrend 추세", "trend")
def supertrend_dir(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]
    if len(closes) < 20:
        return None
    dirs = _supertrend_dir(highs, lows, closes, 10, 3.0)
    if not dirs:
        return None
    cur = dirs[-1]
    if cur > 0:
        return buy("Supertrend 상승추세", "trend", 0.5, "가격이 Supertrend 위(상승)")
    return sell("Supertrend 하락추세", "trend", 0.5, "가격이 Supertrend 아래(하락)")


@strategy("Aroon 크로스(25)", "trend")
def aroon_cross(f):
    highs = f["highs"]; lows = f["lows"]
    a = _aroon(highs, lows, 25)
    if not a:
        return None
    up, down, up_p, down_p = a
    if up_p <= down_p and up > down and up >= 70:
        return buy("Aroon 상향크로스", "trend", min(1.0, up / 100 + 0.1),
                   f"Aroon Up>Down (Up {up:.0f})")
    if up_p >= down_p and up < down and down >= 70:
        return sell("Aroon 하향크로스", "trend", min(1.0, down / 100 + 0.1),
                    f"Aroon Down>Up (Down {down:.0f})")
    return None


@strategy("Vortex 크로스", "trend")
def vortex_cross(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]
    v = _vortex(highs, lows, closes, 14)
    if not v:
        return None
    vp, vm, vp_p, vm_p = v
    if vp_p <= vm_p and vp > vm:
        return buy("Vortex 상향크로스", "trend", min(1.0, (vp - vm) * 2 + 0.45),
                   f"VI+ > VI- ({vp:.2f}>{vm:.2f})")
    if vp_p >= vm_p and vp < vm:
        return sell("Vortex 하향크로스", "trend", min(1.0, (vm - vp) * 2 + 0.45),
                    f"VI- > VI+ ({vm:.2f}>{vp:.2f})")
    return None


@strategy("TRIX 시그널", "trend")
def trix_signal(f):
    closes = f["closes"]
    t = _trix(closes, 15)
    if not t:
        return None
    trix, trix_p = t
    if trix_p <= 0 < trix:
        return buy("TRIX 상향돌파", "trend", 0.55, f"TRIX 0선 상향 ({trix:+.3f})")
    if trix_p >= 0 > trix:
        return sell("TRIX 하향돌파", "trend", 0.55, f"TRIX 0선 하향 ({trix:+.3f})")
    return None


@strategy("DMI 크로스(+DI/-DI)", "trend")
def dmi_cross(f):
    closes = f["closes"]; highs = f["highs"]; lows = f["lows"]
    if len(closes) < 32:
        return None
    a = ind.adx(highs, lows, closes, 14)
    a_prev = ind.adx(highs[:-1], lows[:-1], closes[:-1], 14)
    if not a or not a_prev:
        return None
    pdi, mdi = a["plusDI"], a["minusDI"]
    pdi_p, mdi_p = a_prev["plusDI"], a_prev["minusDI"]
    adx_v = a["adx"]
    st = min(1.0, max(0.0, (adx_v - 15) / 30) + 0.4)
    if pdi_p <= mdi_p and pdi > mdi:
        return buy("DMI 상향크로스", "trend", st, f"+DI>-DI 교차 (ADX {adx_v:.0f})")
    if pdi_p >= mdi_p and pdi < mdi:
        return sell("DMI 하향크로스", "trend", st, f"-DI>+DI 교차 (ADX {adx_v:.0f})")
    return None
