"""피봇 확장(structure) 전략군 — 카마릴라/Woodie/클래식 피봇 기반 S/R 반전·돌파.

직전 완성봉의 H/L/C로 피봇을 직접 산출(카마릴라·Woodie)하고,
f["levels"]["pivots"](클래식 P/R1/S1...)도 함께 활용한다.
현재가가 각 레벨에 근접/돌파했을 때 반전 또는 돌파 신호를 낸다.
"""
from __future__ import annotations
from .base import buy, sell, strategy


def _prev_hlc(f):
    """직전 완성봉의 (high, low, close). 데이터 부족 시 None."""
    highs = f.get("highs"); lows = f.get("lows"); closes = f.get("closes")
    if not highs or not lows or not closes:
        return None
    if len(highs) < 2 or len(lows) < 2 or len(closes) < 2:
        return None
    # 마지막 인덱스가 진행중일 수 있으므로 직전봉(-2) 사용
    h = highs[-2]; l = lows[-2]; c = closes[-2]
    if None in (h, l, c) or h <= l:
        return None
    return float(h), float(l), float(c)


def _price(f):
    p = f.get("price")
    if p is None:
        p = f.get("lastClose")
    try:
        return float(p)
    except (TypeError, ValueError):
        return None


def _camarilla(h, l, c):
    rng = h - l
    if rng <= 0:
        return None
    return {
        "h3": c + rng * 1.1 / 4.0,
        "h4": c + rng * 1.1 / 2.0,
        "l3": c - rng * 1.1 / 4.0,
        "l4": c - rng * 1.1 / 2.0,
    }


def _woodie(h, l, c):
    # Woodie 피봇은 종가에 가중(2C+H+L)/4
    p = (h + l + 2 * c) / 4.0
    return {
        "p": p,
        "r1": 2 * p - l,
        "s1": 2 * p - h,
        "r2": p + (h - l),
        "s2": p - (h - l),
    }


@strategy("카마릴라 H3/L3 반전", "structure")
def camarilla_reversal(f):
    hlc = _prev_hlc(f)
    price = _price(f)
    if hlc is None or price is None:
        return None
    cam = _camarilla(*hlc)
    if cam is None:
        return None
    rng = hlc[0] - hlc[1]
    tol = rng * 0.12 or None
    if tol is None:
        return None
    # L3 근접 & 미이탈(H4~L4 박스 안) → 매수 반전
    if cam["l4"] < price <= cam["l3"] + tol and price >= cam["l4"]:
        dist = abs(price - cam["l3"]) / price * 100
        return buy("카마릴라 L3 반전", "structure", 0.6, f"L3 지지 반전대 근접({dist:.1f}%)")
    # H3 근접 & 미이탈 → 매도 반전
    if cam["h3"] - tol <= price < cam["h4"] and price <= cam["h4"]:
        dist = abs(price - cam["h3"]) / price * 100
        return sell("카마릴라 H3 반전", "structure", 0.6, f"H3 저항 반전대 근접({dist:.1f}%)")
    return None


@strategy("카마릴라 H4/L4 돌파", "structure")
def camarilla_breakout(f):
    hlc = _prev_hlc(f)
    price = _price(f)
    if hlc is None or price is None:
        return None
    cam = _camarilla(*hlc)
    if cam is None:
        return None
    # H4 상향 돌파 → 추세 매수
    if price > cam["h4"]:
        over = (price - cam["h4"]) / price * 100
        return buy("카마릴라 H4 돌파", "structure", min(1.0, 0.6 + over / 5), f"H4 상향 돌파({over:.1f}%)")
    # L4 하향 이탈 → 추세 매도
    if price < cam["l4"]:
        under = (cam["l4"] - price) / price * 100
        return sell("카마릴라 L4 이탈", "structure", min(1.0, 0.6 + under / 5), f"L4 하향 이탈({under:.1f}%)")
    return None


@strategy("Woodie 피봇 반응", "structure")
def woodie_pivot(f):
    hlc = _prev_hlc(f)
    price = _price(f)
    if hlc is None or price is None:
        return None
    wd = _woodie(*hlc)
    rng = hlc[0] - hlc[1]
    tol = rng * 0.12
    if tol <= 0:
        return None
    # S1 근접(피봇 아래) → 매수 / R1 근접(피봇 위) → 매도
    if price < wd["p"] and abs(price - wd["s1"]) <= tol:
        return buy("Woodie S1 지지", "structure", 0.55, f"Woodie S1 {wd['s1']:.0f} 근접")
    if price > wd["p"] and abs(price - wd["r1"]) <= tol:
        return sell("Woodie R1 저항", "structure", 0.55, f"Woodie R1 {wd['r1']:.0f} 근접")
    return None


@strategy("Woodie S2/R2 변곡", "structure")
def woodie_extreme(f):
    hlc = _prev_hlc(f)
    price = _price(f)
    if hlc is None or price is None:
        return None
    wd = _woodie(*hlc)
    rng = hlc[0] - hlc[1]
    tol = rng * 0.12
    if tol <= 0:
        return None
    # S2 근접/하회 → 강한 지지 반등 기대 / R2 근접/상회 → 강한 저항 되돌림
    if price <= wd["s2"] + tol:
        return buy("Woodie S2 변곡", "structure", 0.6, f"Woodie S2 {wd['s2']:.0f} 도달(반등 기대)")
    if price >= wd["r2"] - tol:
        return sell("Woodie R2 변곡", "structure", 0.6, f"Woodie R2 {wd['r2']:.0f} 도달(되돌림 경계)")
    return None


@strategy("클래식 피봇 R1/S1 반응", "structure")
def classic_pivot_r1s1(f):
    lv = f.get("levels") or {}
    piv = lv.get("pivots") or {}
    price = _price(f)
    if price is None or not piv:
        return None
    p = piv.get("p"); r1 = piv.get("r1"); s1 = piv.get("s1")
    if None in (p, r1, s1):
        return None
    band = abs(r1 - s1) * 0.18
    if band <= 0:
        return None
    # 피봇 위에서 S1(되돌림) 지지 근접 → 매수, R1 저항 근접 → 매도
    if abs(price - s1) <= band:
        return buy("클래식 S1 지지", "structure", 0.5, f"피봇 S1 {s1:.0f} 근접(지지)")
    if abs(price - r1) <= band:
        return sell("클래식 R1 저항", "structure", 0.5, f"피봇 R1 {r1:.0f} 근접(저항)")
    return None


@strategy("클래식 피봇 돌파", "structure")
def classic_pivot_break(f):
    lv = f.get("levels") or {}
    piv = lv.get("pivots") or {}
    price = _price(f)
    if price is None or not piv:
        return None
    p = piv.get("p"); r2 = piv.get("r2"); s2 = piv.get("s2")
    if None in (p, r2, s2):
        return None
    # R2 상향 돌파 → 매수 / S2 하향 이탈 → 매도
    if price > r2:
        over = (price - r2) / price * 100
        return buy("클래식 R2 돌파", "structure", min(1.0, 0.55 + over / 5), f"피봇 R2 상향 돌파({over:.1f}%)")
    if price < s2:
        under = (s2 - price) / price * 100
        return sell("클래식 S2 이탈", "structure", min(1.0, 0.55 + under / 5), f"피봇 S2 하향 이탈({under:.1f}%)")
    return None
