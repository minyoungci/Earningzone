"""StochRSI · 자금흐름(Flow) 모멘텀 전략군.

Stochastic RSI(과매수/매도·K/D 크로스), Chaikin Money Flow(20),
Elder Ray(bull/bear power), Force Index, Ease of Movement.
모든 지표는 features dict의 OHLCV 시계열에서 순수 파이썬으로 직접 계산.
"""
from __future__ import annotations
from .base import buy, sell, strategy
from .. import indicators as ind


# ── 내부 헬퍼 ─────────────────────────────────────────────
def _stochrsi_series(closes, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3):
    """StochRSI %K, %D 시계열 반환(앞쪽은 데이터 부족). (kSeries, dSeries) 또는 (None, None)."""
    if closes is None or len(closes) < rsi_period + stoch_period + 1:
        return None, None
    rsi_s = ind.rsi_series(closes, rsi_period)
    # None 제거(유효 RSI만)
    rsi_vals = [r for r in rsi_s if r is not None]
    if len(rsi_vals) < stoch_period:
        return None, None
    raw = []  # 원시 StochRSI(0..100)
    for i in range(stoch_period - 1, len(rsi_vals)):
        window = rsi_vals[i - stoch_period + 1:i + 1]
        hh = max(window)
        ll = min(window)
        raw.append(100 * (rsi_vals[i] - ll) / (hh - ll) if hh > ll else 50.0)
    if not raw:
        return None, None
    # %K = raw의 k_smooth 이동평균
    k_series = []
    for i in range(len(raw)):
        seg = raw[max(0, i - k_smooth + 1):i + 1]
        k_series.append(sum(seg) / len(seg))
    # %D = %K의 d_smooth 이동평균
    d_series = []
    for i in range(len(k_series)):
        seg = k_series[max(0, i - d_smooth + 1):i + 1]
        d_series.append(sum(seg) / len(seg))
    return k_series, d_series


def _ema_last(values, period):
    return ind.ema(values, period)


# ── StochRSI 과매수/과매도 ────────────────────────────────
@strategy("StochRSI 과매수/과매도", "momentum")
def stochrsi_levels(f):
    closes = f.get("closes")
    k_series, _ = _stochrsi_series(closes)
    if not k_series:
        return None
    k = k_series[-1]
    if k <= 20:
        return buy("StochRSI 과매도", "momentum", min(1.0, (20 - k) / 20 + 0.5),
                   f"StochRSI %K {k:.0f}<=20")
    if k >= 80:
        return sell("StochRSI 과매수", "momentum", min(1.0, (k - 80) / 20 + 0.5),
                    f"StochRSI %K {k:.0f}>=80")
    return None


# ── StochRSI K/D 크로스 ───────────────────────────────────
@strategy("StochRSI K/D 크로스", "momentum")
def stochrsi_cross(f):
    closes = f.get("closes")
    k_series, d_series = _stochrsi_series(closes)
    if not k_series or not d_series or len(k_series) < 2 or len(d_series) < 2:
        return None
    k, kp = k_series[-1], k_series[-2]
    d, dp = d_series[-1], d_series[-2]
    # 과매도권 상향 골든크로스
    if kp <= dp and k > d and k < 40:
        return buy("StochRSI 골든크로스", "momentum", 0.6,
                   f"과매도권 %K>%D (K {k:.0f})")
    # 과매수권 하향 데드크로스
    if kp >= dp and k < d and k > 60:
        return sell("StochRSI 데드크로스", "momentum", 0.6,
                    f"과매수권 %K<%D (K {k:.0f})")
    return None


# ── Chaikin Money Flow (20) ───────────────────────────────
@strategy("Chaikin Money Flow", "momentum")
def cmf(f):
    highs = f.get("highs"); lows = f.get("lows")
    closes = f.get("closes"); vols = f.get("volumes")
    if None in (highs, lows, closes, vols):
        return None
    period = 20
    if len(closes) < period:
        return None
    mfv_sum = 0.0
    vol_sum = 0.0
    for i in range(len(closes) - period, len(closes)):
        h, l, c, v = highs[i], lows[i], closes[i], vols[i]
        rng = h - l
        if rng <= 0:
            mult = 0.0
        else:
            mult = ((c - l) - (h - c)) / rng
        mfv_sum += mult * v
        vol_sum += v
    if vol_sum <= 0:
        return None
    val = mfv_sum / vol_sum  # -1..+1
    if val > 0.10:
        return buy("CMF 매집", "momentum", min(1.0, val * 2 + 0.4),
                   f"CMF {val:+.2f}(매수자금 유입)")
    if val < -0.10:
        return sell("CMF 분산", "momentum", min(1.0, -val * 2 + 0.4),
                    f"CMF {val:+.2f}(매도자금 유출)")
    return None


# ── Elder Ray (Bull/Bear Power) ───────────────────────────
@strategy("Elder Ray", "momentum")
def elder_ray(f):
    highs = f.get("highs"); lows = f.get("lows"); closes = f.get("closes")
    if None in (highs, lows, closes):
        return None
    period = 13
    if len(closes) < period + 1:
        return None
    e = _ema_last(closes, period)
    ep = _ema_last(closes[:-1], period)
    if e is None or ep is None:
        return None
    bull = highs[-1] - e          # Bull Power
    bear = lows[-1] - e           # Bear Power
    bull_p = highs[-2] - ep
    bear_p = lows[-2] - ep
    rising = e > ep               # EMA 추세 상승
    falling = e < ep
    # 상승추세 + Bear Power 음수이나 회복(저점 매수)
    if rising and bear < 0 and bear > bear_p:
        return buy("Elder Ray 매수", "momentum", 0.55,
                   f"상승추세·Bear Power 회복({bear:+.0f})")
    # 하락추세 + Bull Power 양수이나 약화(반등 소진)
    if falling and bull > 0 and bull < bull_p:
        return sell("Elder Ray 매도", "momentum", 0.55,
                    f"하락추세·Bull Power 약화({bull:+.0f})")
    return None


# ── Force Index (13 EMA) ──────────────────────────────────
@strategy("Force Index", "momentum")
def force_index(f):
    closes = f.get("closes"); vols = f.get("volumes")
    if None in (closes, vols):
        return None
    period = 13
    if len(closes) < period + 2:
        return None
    # 1기간 Force Index 시계열
    fi1 = [(closes[i] - closes[i - 1]) * vols[i] for i in range(1, len(closes))]
    if len(fi1) < period + 1:
        return None
    fi_s = ind.ema_series(fi1, period)
    if len(fi_s) < 2:
        return None
    fi, fip = fi_s[-1], fi_s[-2]
    # 0선 상향 돌파(매수 압력 전환)
    if fip <= 0 < fi:
        return buy("Force Index 0선 상향", "momentum", 0.55, "매수 압력 우위 전환")
    # 0선 하향 돌파(매도 압력 전환)
    if fip >= 0 > fi:
        return sell("Force Index 0선 하향", "momentum", 0.55, "매도 압력 우위 전환")
    return None


# ── Ease of Movement (EMV 14) ─────────────────────────────
@strategy("Ease of Movement", "momentum")
def ease_of_movement(f):
    highs = f.get("highs"); lows = f.get("lows"); vols = f.get("volumes")
    if None in (highs, lows, vols):
        return None
    period = 14
    if len(highs) < period + 1:
        return None
    emv = []  # 1기간 EMV 시계열
    for i in range(1, len(highs)):
        mid = (highs[i] + lows[i]) / 2
        mid_prev = (highs[i - 1] + lows[i - 1]) / 2
        dist = mid - mid_prev
        rng = highs[i] - lows[i]
        v = vols[i]
        if v <= 0 or rng <= 0:
            box = 0.0
        else:
            # 박스비율: (volume / scale) / range. 스케일은 거래량 단위 보정.
            box = (v / 100000000.0) / rng
        emv.append(dist / box if box > 0 else 0.0)
    if len(emv) < period + 1:
        return None
    # EMV의 period 단순이동평균
    cur = sum(emv[-period:]) / period
    prev = sum(emv[-period - 1:-1]) / period
    if prev <= 0 < cur:
        return buy("EMV 0선 상향", "momentum", 0.45, "적은 저항으로 상승(매수 우호)")
    if prev >= 0 > cur:
        return sell("EMV 0선 하향", "momentum", 0.45, "적은 저항으로 하락(매도 우호)")
    return None
