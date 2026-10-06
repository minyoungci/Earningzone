"""모멘텀(momentum) 전략군."""
from __future__ import annotations
from .base import buy, sell, strategy


@strategy("RSI 과매수/과매도", "momentum")
def rsi_levels(f):
    r = f["rsi"]
    if r is None:
        return None
    if r < 30:
        return buy("RSI 과매도", "momentum", min(1.0, (30 - r) / 15 + 0.5), f"RSI {r:.0f}<30")
    if r > 70:
        return sell("RSI 과매수", "momentum", min(1.0, (r - 70) / 15 + 0.5), f"RSI {r:.0f}>70")
    return None


@strategy("RSI 50 돌파", "momentum")
def rsi_50_cross(f):
    r, rp = f["rsi"], f["rsiPrev"]
    if None in (r, rp):
        return None
    if rp <= 50 < r:
        return buy("RSI 50 상향돌파", "momentum", 0.5, "RSI 50선 상향")
    if rp >= 50 > r:
        return sell("RSI 50 하향돌파", "momentum", 0.5, "RSI 50선 하향")
    return None


@strategy("MACD 시그널 크로스", "momentum")
def macd_cross(f):
    m = f["macd"]
    if not m or m.get("histPrev") is None:
        return None
    if m["histPrev"] <= 0 < m["hist"]:
        return buy("MACD 골든크로스", "momentum", 0.7, "MACD가 시그널 상향돌파")
    if m["histPrev"] >= 0 > m["hist"]:
        return sell("MACD 데드크로스", "momentum", 0.7, "MACD가 시그널 하향돌파")
    return None


@strategy("MACD 히스토그램 모멘텀", "momentum")
def macd_hist_mom(f):
    m = f["macd"]
    if not m or m.get("histPrev") is None:
        return None
    if m["hist"] > 0 and m["hist"] > m["histPrev"]:
        return buy("MACD 히스토그램↑", "momentum", 0.45, "히스토그램 양수·확대")
    if m["hist"] < 0 and m["hist"] < m["histPrev"]:
        return sell("MACD 히스토그램↓", "momentum", 0.45, "히스토그램 음수·확대")
    return None


@strategy("스토캐스틱 크로스", "momentum")
def stoch_cross(f):
    s, sp = f["stoch"], f["stochPrev"]
    if not s or not sp:
        return None
    if sp["k"] <= sp["d"] and s["k"] > s["d"] and s["k"] < 25:
        return buy("스토캐스틱 골든크로스", "momentum", 0.6, f"과매도권 %K>%D (K {s['k']:.0f})")
    if sp["k"] >= sp["d"] and s["k"] < s["d"] and s["k"] > 75:
        return sell("스토캐스틱 데드크로스", "momentum", 0.6, f"과매수권 %K<%D (K {s['k']:.0f})")
    return None


@strategy("CCI 과열/침체", "momentum")
def cci_levels(f):
    c = f["cci"]
    if c is None:
        return None
    if c < -100:
        return buy("CCI 침체", "momentum", min(1.0, (-c - 100) / 100 + 0.4), f"CCI {c:.0f}<-100")
    if c > 100:
        return sell("CCI 과열", "momentum", min(1.0, (c - 100) / 100 + 0.4), f"CCI {c:.0f}>100")
    return None


@strategy("Williams %R", "momentum")
def williams(f):
    w = f["williamsR"]
    if w is None:
        return None
    if w < -80:
        return buy("Williams %R 과매도", "momentum", 0.45, f"%R {w:.0f}<-80")
    if w > -20:
        return sell("Williams %R 과매수", "momentum", 0.45, f"%R {w:.0f}>-20")
    return None


@strategy("MFI 자금흐름", "momentum")
def mfi_levels(f):
    m = f["mfi"]
    if m is None:
        return None
    if m < 20:
        return buy("MFI 과매도", "momentum", 0.5, f"MFI {m:.0f}<20(자금유입 여력)")
    if m > 80:
        return sell("MFI 과매수", "momentum", 0.5, f"MFI {m:.0f}>80")
    return None


@strategy("ROC 모멘텀", "momentum")
def roc_mom(f):
    r = f["roc"]
    if r is None:
        return None
    if r > 5:
        return buy("ROC 모멘텀↑", "momentum", min(1.0, r / 20 + 0.3), f"ROC {r:+.1f}%")
    if r < -5:
        return sell("ROC 모멘텀↓", "momentum", min(1.0, -r / 20 + 0.3), f"ROC {r:+.1f}%")
    return None
