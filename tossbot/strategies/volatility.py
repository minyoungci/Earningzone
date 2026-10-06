"""변동성/밴드(volatility) 전략군."""
from __future__ import annotations
from .base import buy, sell, strategy


@strategy("볼린저 밴드 회귀", "volatility")
def boll_reversion(f):
    b, p = f["boll"], f["price"]
    if not b:
        return None
    if p < b["lower"]:
        return buy("볼린저 하단 이탈", "volatility", 0.6, "밴드 하단 아래(과매도)")
    if p > b["upper"]:
        return sell("볼린저 상단 이탈", "volatility", 0.6, "밴드 상단 위(과매수)")
    return None


@strategy("볼린저 밴드 돌파", "volatility")
def boll_breakout(f):
    b, p, a = f["boll"], f["price"], f["adx"]
    if not b or not a:
        return None
    if a["adx"] >= 25 and b.get("pctB", 0.5) > 1.0 and a["plusDI"] > a["minusDI"]:
        return buy("볼린저 상향돌파", "volatility", 0.55, "추세장 밴드 상단 돌파(ADX↑)")
    return None


@strategy("볼린저 스퀴즈", "volatility")
def boll_squeeze(f):
    b, p = f["boll"], f["price"]
    if not b or not b["mid"]:
        return None
    width = (b["upper"] - b["lower"]) / b["mid"]
    if width < 0.06 and p > b["mid"]:
        return buy("볼린저 스퀴즈", "volatility", 0.4, "밴드 수축(변동성 확대 임박)+종가>중심")
    return None


@strategy("켈트너 채널 돌파", "volatility")
def keltner_break(f):
    k, p = f["keltner"], f["price"]
    if not k:
        return None
    if p > k["upper"]:
        return buy("켈트너 상단 돌파", "volatility", 0.5, "켈트너 채널 상단 위")
    if p < k["lower"]:
        return sell("켈트너 하단 이탈", "volatility", 0.5, "켈트너 채널 하단 아래")
    return None
