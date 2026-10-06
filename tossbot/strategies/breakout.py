"""돌파(breakout) 전략군."""
from __future__ import annotations
from .base import buy, sell, strategy


@strategy("돈치안 채널 돌파", "breakout")
def donchian(f):
    d, p = f["donchian"], f["price"]
    if not d:
        return None
    if p >= d["upper"] * 0.999:
        return buy("돈치안 상단 돌파", "breakout", 0.6, "20일 신고가 돌파")
    if p <= d["lower"] * 1.001:
        return sell("돈치안 하단 이탈", "breakout", 0.6, "20일 신저가 이탈")
    return None


@strategy("거래량 급증 돌파", "breakout")
def volume_breakout(f):
    vr, r1 = f["volRatio"], f["ret"]["1"]
    if vr is None or r1 is None:
        return None
    if vr > 2 and r1 > 1:
        return buy("거래량 급증↑", "breakout", min(1.0, vr / 5 + 0.4), f"거래량 {vr:.1f}배 + 상승")
    if vr > 2 and r1 < -1:
        return sell("거래량 급증↓", "breakout", min(1.0, vr / 5 + 0.4), f"거래량 {vr:.1f}배 + 하락")
    return None


@strategy("52주 고저 위치", "breakout")
def high52(f):
    pos = f["levels"].get("pos52")
    if pos is None:
        return None
    if pos > 92:
        return buy("52주 고가권", "breakout", 0.5, f"52주 위치 {pos:.0f}%(신고가 모멘텀)")
    if pos < 8:
        return sell("52주 저가권", "breakout", 0.45, f"52주 위치 {pos:.0f}%(약세)")
    return None
