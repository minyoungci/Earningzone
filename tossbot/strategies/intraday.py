"""인트라데이(분봉) 전략군 — VWAP·EMA9/21·분봉 모멘텀/ROC·돌파.

시계열(closes/highs/lows/volumes)과 f["vwap"]만 사용하므로 일봉에 적용해도 무해합니다.
(시계열만 쓰는 순수 함수라 분봉이 없으면 일봉 기준으로 동작합니다.)
"""
from __future__ import annotations
from .base import buy, sell, strategy as _strategy
from .. import indicators as ind

INTRADAY_REGISTRY = []


def strategy(name, category):
    return _strategy(name, category, registry=INTRADAY_REGISTRY)


@strategy("VWAP 회귀", "meanrev")
def vwap_reversion(f):
    """가격이 VWAP에서 과도하게 이탈하면 평균회귀를 노림(분봉 스캘핑 친화)."""
    vw = f.get("vwap")
    price = f.get("price")
    atr = f.get("atr")
    if vw is None or price is None or not vw:
        return None
    dev = (price - vw) / vw * 100.0
    # ATR 기반 동적 임계(없으면 0.6% 고정)
    thr = (atr / vw * 100.0 * 1.2) if (atr and vw) else 0.6
    thr = max(thr, 0.4)
    if dev <= -thr:
        return buy("VWAP 하향이탈 회귀", "meanrev", min(1.0, -dev / (thr * 2) + 0.4),
                   f"VWAP 대비 {dev:+.2f}% 저평가")
    if dev >= thr:
        return sell("VWAP 상향이탈 회귀", "meanrev", min(1.0, dev / (thr * 2) + 0.4),
                    f"VWAP 대비 {dev:+.2f}% 고평가")
    return None


@strategy("VWAP 돌파", "breakout")
def vwap_breakout(f):
    """직전봉은 VWAP 아래/위였다가 현재봉이 VWAP를 돌파하면 추세 진입."""
    vw = f.get("vwap")
    closes = f.get("closes")
    if vw is None or not vw or not closes or len(closes) < 2:
        return None
    prev, cur = closes[-2], closes[-1]
    vr = f.get("volRatio")
    vol_ok = (vr is not None and vr > 1.2)
    if prev <= vw < cur:
        strength = 0.7 if vol_ok else 0.55
        return buy("VWAP 상향돌파", "breakout", strength,
                   "종가 VWAP 상향" + (" + 거래량" if vol_ok else ""))
    if prev >= vw > cur:
        strength = 0.7 if vol_ok else 0.55
        return sell("VWAP 하향이탈", "breakout", strength,
                    "종가 VWAP 하향" + (" + 거래량" if vol_ok else ""))
    return None


@strategy("EMA9/21 크로스", "momentum")
def ema_9_21_cross(f):
    """단기 EMA(9/21) 골든·데드 크로스 — 분봉 추세전환 포착."""
    closes = f.get("closes")
    if not closes or len(closes) < 23:
        return None
    e9 = ind.ema_series(closes, 9)
    e21 = ind.ema_series(closes, 21)
    if len(e9) < 2 or len(e21) < 2:
        return None
    # 끝에서 2개 비교(시계열 길이 정렬: 둘 다 마지막 2개만 사용)
    f9_prev, f9_cur = e9[-2], e9[-1]
    f21_prev, f21_cur = e21[-2], e21[-1]
    if f9_prev <= f21_prev and f9_cur > f21_cur:
        return buy("EMA9>21 골든크로스", "momentum", 0.6, "단기 EMA 골든크로스")
    if f9_prev >= f21_prev and f9_cur < f21_cur:
        return sell("EMA9<21 데드크로스", "momentum", 0.6, "단기 EMA 데드크로스")
    return None


@strategy("분봉 ROC 모멘텀", "momentum")
def intraday_roc(f):
    """짧은 룩백(ROC9)으로 분봉 가속/감속 모멘텀을 포착."""
    closes = f.get("closes")
    if not closes or len(closes) < 12:
        return None
    r = ind.roc(closes, 9)
    if r is None:
        return None
    if r > 1.5:
        return buy("분봉 모멘텀↑", "momentum", min(1.0, r / 6 + 0.35), f"ROC9 {r:+.2f}%")
    if r < -1.5:
        return sell("분봉 모멘텀↓", "momentum", min(1.0, -r / 6 + 0.35), f"ROC9 {r:+.2f}%")
    return None


@strategy("최근 N봉 돌파", "breakout")
def recent_range_breakout(f):
    """직전 20봉 고/저를 현재가가 돌파하면 분봉 레인지 브레이크."""
    highs = f.get("highs")
    lows = f.get("lows")
    price = f.get("price")
    if not highs or not lows or price is None or len(highs) < 22:
        return None
    # 현재봉 제외한 직전 20봉의 고/저
    prior_high = max(highs[-21:-1])
    prior_low = min(lows[-21:-1])
    if prior_high <= 0:
        return None
    vr = f.get("volRatio")
    if price > prior_high:
        boost = 0.15 if (vr is not None and vr > 1.5) else 0.0
        return buy("20봉 고가 돌파", "breakout", min(1.0, 0.55 + boost),
                   f"직전 20봉 고가 {prior_high:,.0f} 돌파")
    if price < prior_low:
        boost = 0.15 if (vr is not None and vr > 1.5) else 0.0
        return sell("20봉 저가 이탈", "breakout", min(1.0, 0.55 + boost),
                    f"직전 20봉 저가 {prior_low:,.0f} 이탈")
    return None
