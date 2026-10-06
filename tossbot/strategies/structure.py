"""구조(structure) 전략군 — 다이버전스, 캔들/차트 패턴, 지지/저항, 수급."""
from __future__ import annotations
from .base import buy, sell, strategy


@strategy("RSI 다이버전스", "structure")
def rsi_div(f):
    d = f["divergence"]["rsi"]["regular"]
    if d == "bullish":
        return buy("RSI 상승 다이버전스", "structure", 0.7, "가격 LL + RSI HL(반등 신호)")
    if d == "bearish":
        return sell("RSI 하락 다이버전스", "structure", 0.7, "가격 HH + RSI LH(하락 신호)")
    return None


@strategy("MACD 다이버전스", "structure")
def macd_div(f):
    d = f["divergence"]["macd"]["regular"]
    if d == "bullish":
        return buy("MACD 상승 다이버전스", "structure", 0.65, "가격 LL + MACD HL")
    if d == "bearish":
        return sell("MACD 하락 다이버전스", "structure", 0.65, "가격 HH + MACD LH")
    return None


@strategy("지지/저항 근접", "structure")
def sr_proximity(f):
    lv = f["levels"]
    ds, dr = lv.get("distToSupport"), lv.get("distToResistance")
    if ds is not None and ds < 1.5:
        return buy("지지선 근접", "structure", 0.55, f"지지선 {ds:.1f}% 이내(반등 기대)")
    if dr is not None and dr < 1.5:
        return sell("저항선 근접", "structure", 0.55, f"저항선 {dr:.1f}% 이내(되돌림 경계)")
    return None


@strategy("캔들 패턴", "structure")
def candle_pattern(f):
    pats = f["candlePatterns"]
    bias = sum(p["bias"] for p in pats)
    names = ", ".join(p["name"] for p in pats if p["bias"] != 0)
    if bias > 0:
        return buy("캔들 패턴(강세)", "structure", min(1.0, 0.4 + 0.2 * bias), names or "강세 캔들")
    if bias < 0:
        return sell("캔들 패턴(약세)", "structure", min(1.0, 0.4 + 0.2 * -bias), names or "약세 캔들")
    return None


@strategy("차트 패턴", "structure")
def chart_pattern(f):
    pats = f["chartPatterns"]
    bias = sum(p["bias"] for p in pats)
    names = ", ".join(p["name"] for p in pats)
    if bias > 0:
        return buy("차트 패턴(강세)", "structure", 0.6, names)
    if bias < 0:
        return sell("차트 패턴(약세)", "structure", 0.6, names)
    return None


@strategy("추세 구조", "structure")
def structure_trend(f):
    s = f["structure"]
    if s == "uptrend":
        return buy("추세 구조(상승)", "structure", 0.4, "HH·HL 상승구조")
    if s == "downtrend":
        return sell("추세 구조(하락)", "structure", 0.4, "LH·LL 하락구조")
    return None


@strategy("호가 수급 불균형", "structure")
def orderbook_imbalance(f):
    imb = f["imbalance"]
    if imb is None:
        return None
    if imb > 0.3:
        return buy("호가 매수우위", "structure", min(1.0, imb), f"매수잔량 우위 {imb:+.0%}")
    if imb < -0.3:
        return sell("호가 매도우위", "structure", min(1.0, -imb), f"매도잔량 우위 {imb:+.0%}")
    return None
