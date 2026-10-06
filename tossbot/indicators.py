"""순수 파이썬 기술적 지표 (외부 의존성 없음).

스칼라 입력은 종가 등 float 리스트(시간 오름차순). OHLC 기반 지표는 highs/lows/closes를 받습니다.
"""
from __future__ import annotations
from typing import Dict, List, Optional


# ── 이동평균 ──────────────────────────────────────────────
def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: List[float], period: int) -> List[float]:
    """EMA 시계열. 첫 값은 앞 period개의 SMA로 시드. 길이 = len-period+1."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    out = [e]
    for v in values[period:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def ema(values: List[float], period: int) -> Optional[float]:
    s = ema_series(values, period)
    return s[-1] if s else None


# ── 모멘텀/오실레이터 ─────────────────────────────────────
def rsi_series(values: List[float], period: int = 14) -> List[Optional[float]]:
    """closes와 같은 길이의 RSI 시계열(앞쪽은 None)."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n < period + 1:
        return out
    gains, losses = [], []
    for i in range(1, n):
        ch = values[i] - values[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi(g, l):
        if l == 0:
            return 100.0
        rs = g / l
        return 100 - 100 / (1 + rs)

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return out


def rsi(values: List[float], period: int = 14) -> Optional[float]:
    s = rsi_series(values, period)
    return s[-1] if s else None


def macd_series(values: List[float], fast=12, slow=26, signal=9):
    """MACD line/signal/hist 시계열(slow 시작점 정렬). 반환: dict of lists 또는 None."""
    if len(values) < slow + signal:
        return None
    ef = ema_series(values, fast)
    es = ema_series(values, slow)
    n = len(es)
    ef_tail = ef[len(ef) - n:]
    macd_line = [ef_tail[i] - es[i] for i in range(n)]
    sig = ema_series(macd_line, signal)
    m = len(sig)
    macd_tail = macd_line[len(macd_line) - m:]
    hist = [macd_tail[i] - sig[i] for i in range(m)]
    return {"macd": macd_tail, "signal": sig, "hist": hist}


def macd(values: List[float], fast=12, slow=26, signal=9):
    s = macd_series(values, fast, slow, signal)
    if not s or not s["hist"]:
        return None
    return {"macd": s["macd"][-1], "signal": s["signal"][-1], "hist": s["hist"][-1]}


def stochastic(highs, lows, closes, k_period=14, d_period=3, back=0):
    """Slow Stochastic %K, %D. 반환 {'k','d'} 또는 None.

    HTS 표준에 맞춰 raw fast %K 시계열을 d_period로 평활해 slow %K를 만들고,
    그 slow %K를 다시 d_period로 평활해 %D를 산출한다(slow stochastic).
    back>0이면 마지막에서 back봉 전의 값을 반환(전 구간 재계산 없이 ks 시프트).
    """
    n = len(closes)
    if n < k_period:
        return None
    # raw fast %K 시계열
    ks = []
    for i in range(k_period - 1, n):
        hh = max(highs[i - k_period + 1:i + 1])
        ll = min(lows[i - k_period + 1:i + 1])
        ks.append(100 * (closes[i] - ll) / (hh - ll) if hh > ll else 50.0)
    # slow %K = fast %K를 d_period로 평활(SMA), %D = slow %K를 다시 평활
    slow_k = [sum(ks[j - d_period + 1:j + 1]) / d_period
              for j in range(d_period - 1, len(ks))]
    if not slow_k:
        # 평활할 표본이 부족하면 raw fast %K로 폴백(중립값 컨벤션 유지)
        slow_k = ks
    slow_d = [sum(slow_k[j - d_period + 1:j + 1]) / d_period
              for j in range(d_period - 1, len(slow_k))]
    # back봉 전 값을 ks 시프트로 산출(전 구간 재계산 불필요)
    ki = len(slow_k) - 1 - back
    di = len(slow_d) - 1 - back
    if ki < 0:
        return None
    k = slow_k[ki]
    d = slow_d[di] if di >= 0 else sum(slow_k[:ki + 1]) / (ki + 1)
    return {"k": k, "d": d}


def williams_r(highs, lows, closes, period=14) -> Optional[float]:
    if len(closes) < period:
        return None
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    return -100 * (hh - closes[-1]) / (hh - ll) if hh > ll else -50.0


def cci(highs, lows, closes, period=20) -> Optional[float]:
    if len(closes) < period:
        return None
    tps = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    window = tps[-period:]
    ma = sum(window) / period
    md = sum(abs(x - ma) for x in window) / period
    return (tps[-1] - ma) / (0.015 * md) if md else 0.0


def roc(values: List[float], period=12) -> Optional[float]:
    if len(values) < period + 1 or values[-(period + 1)] == 0:
        return None
    return 100 * (values[-1] - values[-(period + 1)]) / values[-(period + 1)]


# ── 변동성/밴드 ───────────────────────────────────────────
def bollinger(values: List[float], period=20, mult=2.0):
    if len(values) < period:
        return None
    window = values[-period:]
    mid = sum(window) / period
    sd = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
    pctb = (values[-1] - (mid - mult * sd)) / (2 * mult * sd) if sd else 0.5
    return {"mid": mid, "upper": mid + mult * sd, "lower": mid - mult * sd, "sd": sd, "pctB": pctb}


def true_range_series(highs, lows, closes) -> List[float]:
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return tr


def atr(highs, lows, closes, period=14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    tr = true_range_series(highs, lows, closes)
    a = sum(tr[1:period + 1]) / period
    for i in range(period + 1, len(tr)):
        a = (a * (period - 1) + tr[i]) / period
    return a


def keltner(highs, lows, closes, period=20, mult=2.0):
    mid = ema(closes, period)
    a = atr(highs, lows, closes, period)
    if mid is None or a is None:
        return None
    return {"mid": mid, "upper": mid + mult * a, "lower": mid - mult * a, "atr": a}


def donchian(highs, lows, period=20):
    if len(highs) < period:
        return None
    return {"upper": max(highs[-period:]), "lower": min(lows[-period:])}


# ── 추세 강도 ─────────────────────────────────────────────
def adx(highs, lows, closes, period=14):
    """ADX, +DI, -DI (Wilder). 반환 {'adx','plusDI','minusDI'} 또는 None."""
    n = len(closes)
    if n < 2 * period + 1:
        return None
    plus_dm, minus_dm, tr = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    def wilder(seq):
        s = sum(seq[:period])
        out = [s]
        for i in range(period, len(seq)):
            s = s - s / period + seq[i]
            out.append(s)
        return out

    tr_s = wilder(tr)
    pdm_s = wilder(plus_dm)
    mdm_s = wilder(minus_dm)
    dxs = []
    for i in range(len(tr_s)):
        if tr_s[i] == 0:
            dxs.append(0.0); continue
        pdi = 100 * pdm_s[i] / tr_s[i]
        mdi = 100 * mdm_s[i] / tr_s[i]
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0)
    if len(dxs) < period:
        return None
    adx_val = sum(dxs[:period]) / period
    for i in range(period, len(dxs)):
        adx_val = (adx_val * (period - 1) + dxs[i]) / period
    pdi = 100 * pdm_s[-1] / tr_s[-1] if tr_s[-1] else 0.0
    mdi = 100 * mdm_s[-1] / tr_s[-1] if tr_s[-1] else 0.0
    return {"adx": adx_val, "plusDI": pdi, "minusDI": mdi}


# ── 거래량 ────────────────────────────────────────────────
def obv_series(closes, volumes) -> List[float]:
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def obv_slope(closes, volumes, lookback=10) -> Optional[float]:
    o = obv_series(closes, volumes)
    if len(o) < lookback + 1:
        return None
    base = abs(o[-(lookback + 1)]) or 1.0
    return (o[-1] - o[-(lookback + 1)]) / base


def mfi(highs, lows, closes, volumes, period=14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    pos, neg = 0.0, 0.0
    for i in range(len(closes) - period, len(closes)):
        mf = tp[i] * volumes[i]
        if tp[i] > tp[i - 1]:
            pos += mf
        elif tp[i] < tp[i - 1]:
            neg += mf
    if neg == 0:
        return 100.0
    return 100 - 100 / (1 + pos / neg)


def vwap(highs, lows, closes, volumes, period=20) -> Optional[float]:
    if len(closes) < period:
        return None
    num = den = 0.0
    for i in range(len(closes) - period, len(closes)):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        num += tp * volumes[i]
        den += volumes[i]
    return num / den if den else None


# ── 추세 전환 ─────────────────────────────────────────────
def ichimoku(highs, lows, closes):
    def mid(seq, p):
        if len(seq) < p:
            return None
        return (max(seq[-p:]) + min(seq[-p:])) / 2
    if len(closes) < 52:
        return None
    tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2
    kijun = (max(highs[-26:]) + min(lows[-26:])) / 2
    span_a = (tenkan + kijun) / 2
    span_b = (max(highs[-52:]) + min(lows[-52:])) / 2
    return {"tenkan": tenkan, "kijun": kijun, "spanA": span_a, "spanB": span_b,
            "cloudTop": max(span_a, span_b), "cloudBottom": min(span_a, span_b)}


def parabolic_sar(highs, lows, closes=None, af_step=0.02, af_max=0.2) -> Optional[float]:
    n = len(highs)
    if n < 5:
        return None
    # 초기 추세를 데이터로 시드(닫힘 상승이면 up). closes가 없으면 고저 방향으로 폴백.
    if closes is not None and len(closes) >= 2:
        up = closes[1] >= closes[0]
    else:
        up = highs[1] >= highs[0] or lows[1] >= lows[0]
    sar = lows[0] if up else highs[0]
    ep = highs[0] if up else lows[0]
    af = af_step
    for i in range(1, n):
        prev = sar
        sar = prev + af * (ep - prev)
        if up:
            sar = min(sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if highs[i] > ep:
                ep = highs[i]; af = min(af + af_step, af_max)
            if lows[i] < sar:
                # 추세 전환: SAR를 직전 EP로 두되 전환 봉에도 클램프 일관 적용
                up = False; sar = ep; ep = lows[i]; af = af_step
                sar = max(sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
        else:
            sar = max(sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if lows[i] < ep:
                ep = lows[i]; af = min(af + af_step, af_max)
            if highs[i] > sar:
                up = True; sar = ep; ep = highs[i]; af = af_step
                sar = min(sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
    return sar


# ── 기타 ──────────────────────────────────────────────────
def pct_change(values: List[float], n: int) -> Optional[float]:
    if len(values) < n + 1 or values[-(n + 1)] == 0:
        return None
    return (values[-1] / values[-(n + 1)] - 1) * 100


def disparity(values: List[float], period=20) -> Optional[float]:
    m = sma(values, period)
    return 100 * values[-1] / m if m else None
