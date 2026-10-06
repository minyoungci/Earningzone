"""추세(trend) 전략군."""
from __future__ import annotations
from .. import indicators as ind
from .base import buy, sell, strategy


@strategy("MA 배열", "trend")
def ma_alignment(f):
    a, b, c = f["sma5"], f["sma20"], f["sma60"]
    if None in (a, b, c):
        return None
    if a > b > c:
        return buy("MA 배열", "trend", 0.7, "정배열(5>20>60)")
    if a < b < c:
        return sell("MA 배열", "trend", 0.7, "역배열(5<20<60)")
    return None


@strategy("장기추세(120)", "trend")
def long_trend(f):
    p, s60, s120 = f["price"], f["sma60"], f["sma120"]
    if None in (s60, s120):
        return None
    if p > s120 and s60 > s120:
        return buy("장기추세(120)", "trend", 0.55, "가격·60MA가 120MA 위")
    if p < s120 and s60 < s120:
        return sell("장기추세(120)", "trend", 0.55, "가격·60MA가 120MA 아래")
    return None


@strategy("골든/데드크로스(20/60)", "trend")
def golden_cross(f):
    cl = f["closes"]
    s20, s60 = ind.sma(cl, 20), ind.sma(cl, 60)
    p20, p60 = ind.sma(cl[:-1], 20), ind.sma(cl[:-1], 60)
    if None in (s20, s60, p20, p60):
        return None
    if p20 <= p60 and s20 > s60:
        return buy("골든크로스(20/60)", "trend", 0.8, "20MA가 60MA 상향돌파")
    if p20 >= p60 and s20 < s60:
        return sell("데드크로스(20/60)", "trend", 0.8, "20MA가 60MA 하향돌파")
    return None


@strategy("EMA 크로스(12/26)", "trend")
def ema_cross(f):
    cl = f["closes"]
    e12, e26 = ind.ema(cl, 12), ind.ema(cl, 26)
    pe12, pe26 = ind.ema(cl[:-1], 12), ind.ema(cl[:-1], 26)
    if None in (e12, e26, pe12, pe26):
        return None
    if pe12 <= pe26 and e12 > e26:
        return buy("EMA 크로스(12/26)", "trend", 0.65, "EMA12가 EMA26 상향돌파")
    if pe12 >= pe26 and e12 < e26:
        return sell("EMA 크로스(12/26)", "trend", 0.65, "EMA12가 EMA26 하향돌파")
    return None


@strategy("ADX 추세강도", "trend")
def adx_trend(f):
    a = f["adx"]
    if not a or a["adx"] < 25:
        return None
    st = min(1.0, (a["adx"] - 20) / 30)
    if a["plusDI"] > a["minusDI"]:
        return buy("ADX 추세강도", "trend", st, f"강한 상승추세(ADX {a['adx']:.0f}, +DI>-DI)")
    return sell("ADX 추세강도", "trend", st, f"강한 하락추세(ADX {a['adx']:.0f}, -DI>+DI)")


@strategy("일목균형표", "trend")
def ichimoku_s(f):
    ich, p = f["ichimoku"], f["price"]
    if not ich:
        return None
    if p > ich["cloudTop"] and ich["tenkan"] > ich["kijun"]:
        return buy("일목균형표", "trend", 0.6, "구름 위 + 전환선>기준선")
    if p < ich["cloudBottom"] and ich["tenkan"] < ich["kijun"]:
        return sell("일목균형표", "trend", 0.6, "구름 아래 + 전환선<기준선")
    return None


@strategy("Parabolic SAR", "trend")
def psar_s(f):
    ps, p = f["psar"], f["price"]
    if ps is None:
        return None
    if p > ps:
        return buy("Parabolic SAR", "trend", 0.5, "가격>SAR(상승)")
    return sell("Parabolic SAR", "trend", 0.5, "가격<SAR(하락)")
