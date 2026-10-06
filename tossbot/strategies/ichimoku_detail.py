"""일목균형표(Ichimoku) 세부 전략군.

전환/기준선 크로스, 구름 돌파(kumo breakout), 후행스팬 확인,
구름 두께/트위스트, 삼역전호(three-role) 정배열 등을 다룬다.
f["ichimoku"](최신 1봉)와 closes/highs/lows를 활용. 카테고리 trend.
"""
from __future__ import annotations
from .base import buy, sell, strategy


def _ichi_at(highs, lows, i):
    """i번째(0-기반) 봉 기준 일목 값 dict 또는 None. i 시점까지의 데이터만 사용."""
    if highs is None or lows is None:
        return None
    if i < 0 or i >= len(highs) or i >= len(lows):
        return None
    if i + 1 < 52:  # span_b(52봉) 계산 불가
        return None
    h, l = highs[:i + 1], lows[:i + 1]
    tenkan = (max(h[-9:]) + min(l[-9:])) / 2
    kijun = (max(h[-26:]) + min(l[-26:])) / 2
    span_a = (tenkan + kijun) / 2
    span_b = (max(h[-52:]) + min(l[-52:])) / 2
    return {
        "tenkan": tenkan, "kijun": kijun, "spanA": span_a, "spanB": span_b,
        "cloudTop": max(span_a, span_b), "cloudBottom": min(span_a, span_b),
    }


@strategy("일목 전환/기준선 크로스", "trend")
def tenkan_kijun_cross(f):
    """전환선이 기준선을 상/하향 돌파(TK cross). 구름 위치로 강도 가중."""
    highs, lows, closes = f.get("highs"), f.get("lows"), f.get("closes")
    if not closes or len(closes) < 53:
        return None
    cur = _ichi_at(highs, lows, len(closes) - 1)
    prev = _ichi_at(highs, lows, len(closes) - 2)
    if not cur or not prev:
        return None
    price = f.get("price")
    if price is None:
        return None
    pt, pk = prev["tenkan"], prev["kijun"]
    ct, ck = cur["tenkan"], cur["kijun"]
    if pt <= pk and ct > ck:
        above = price > cur["cloudTop"]
        s = 0.7 if above else (0.45 if price < cur["cloudBottom"] else 0.55)
        loc = "구름 위" if above else ("구름 아래" if price < cur["cloudBottom"] else "구름 내부")
        return buy("일목 전환선 골든크로스", "trend", s, f"전환>기준 ({loc})")
    if pt >= pk and ct < ck:
        below = price < cur["cloudBottom"]
        s = 0.7 if below else (0.45 if price > cur["cloudTop"] else 0.55)
        loc = "구름 아래" if below else ("구름 위" if price > cur["cloudTop"] else "구름 내부")
        return sell("일목 전환선 데드크로스", "trend", s, f"전환<기준 ({loc})")
    return None


@strategy("일목 구름 돌파", "trend")
def kumo_breakout(f):
    """현재가가 구름(kumo)을 상/하향 돌파. 직전봉은 구름 안/반대편에 있었어야 함."""
    highs, lows, closes = f.get("highs"), f.get("lows"), f.get("closes")
    ichi = f.get("ichimoku")
    if not ichi or not closes or len(closes) < 53:
        return None
    price = f.get("price")
    if price is None:
        return None
    prev_close = closes[-2]
    top, bot = ichi.get("cloudTop"), ichi.get("cloudBottom")
    if top is None or bot is None:
        return None
    # 상향 돌파: 직전 종가는 구름 위가 아니었고, 현재가가 구름 상단 위
    if prev_close <= top and price > top:
        thick = (top - bot) / price * 100 if price else 0.0
        s = min(0.85, 0.6 + min(thick, 3.0) / 12)
        return buy("일목 구름 상향돌파", "trend", s, f"가격>구름상단 (두께 {thick:.1f}%)")
    # 하향 돌파
    if prev_close >= bot and price < bot:
        thick = (top - bot) / price * 100 if price else 0.0
        s = min(0.85, 0.6 + min(thick, 3.0) / 12)
        return sell("일목 구름 하향돌파", "trend", s, f"가격<구름하단 (두께 {thick:.1f}%)")
    return None


@strategy("일목 후행스팬 확인", "trend")
def chikou_confirm(f):
    """후행스팬(=현재가)을 26봉 전 종가와 비교. 26봉 전 가격 위/아래로 전환되는 시점."""
    closes = f.get("closes")
    if not closes or len(closes) < 28:
        return None
    price = f.get("price")
    if price is None:
        return None
    past = closes[-27]       # 현재 후행스팬과 비교되는 26봉 전 종가
    prev_price = closes[-2]  # 직전 후행스팬(직전 종가)
    prev_past = closes[-28]  # 그때의 26봉 전 종가
    if None in (past, prev_price, prev_past):
        return None
    # 후행스팬이 26봉 전 가격을 상향 돌파
    if prev_price <= prev_past and price > past:
        return buy("일목 후행스팬 상향", "trend", 0.5, "후행스팬>26봉전 종가")
    # 하향 돌파
    if prev_price >= prev_past and price < past:
        return sell("일목 후행스팬 하향", "trend", 0.5, "후행스팬<26봉전 종가")
    return None


@strategy("일목 구름 트위스트", "trend")
def kumo_twist(f):
    """선행스팬A·B 교차(kumo twist) → 추세 전환 시그널. 가격이 같은 방향이면 가중."""
    highs, lows, closes = f.get("highs"), f.get("lows"), f.get("closes")
    if not closes or len(closes) < 53:
        return None
    cur = _ichi_at(highs, lows, len(closes) - 1)
    prev = _ichi_at(highs, lows, len(closes) - 2)
    if not cur or not prev:
        return None
    price = f.get("price")
    if price is None:
        return None
    pa, pb = prev["spanA"], prev["spanB"]
    ca, cb = cur["spanA"], cur["spanB"]
    # A가 B를 상향 교차 → 강세 트위스트(구름 양전환)
    if pa <= pb and ca > cb:
        s = 0.6 if price > cur["cloudTop"] else 0.45
        return buy("일목 구름 양전환", "trend", s, "선행스팬A>B (강세 트위스트)")
    # A가 B를 하향 교차 → 약세 트위스트
    if pa >= pb and ca < cb:
        s = 0.6 if price < cur["cloudBottom"] else 0.45
        return sell("일목 구름 음전환", "trend", s, "선행스팬A<B (약세 트위스트)")
    return None


@strategy("일목 삼역전호 정배열", "trend")
def sanyaku_alignment(f):
    """삼역전호(三役好転/逆転): 전환>기준, 가격>구름, 후행스팬>26봉전 모두 충족."""
    highs, lows, closes = f.get("highs"), f.get("lows"), f.get("closes")
    ichi = f.get("ichimoku")
    if not ichi or not closes or len(closes) < 28:
        return None
    price = f.get("price")
    tenkan, kijun = ichi.get("tenkan"), ichi.get("kijun")
    top, bot = ichi.get("cloudTop"), ichi.get("cloudBottom")
    if None in (price, tenkan, kijun, top, bot):
        return None
    past = closes[-27]
    if past is None:
        return None
    # 삼역호전(강세 정배열)
    bull = (tenkan > kijun) and (price > top) and (price > past)
    if bull:
        return buy("일목 삼역호전", "trend", 0.8, "전환>기준·가격>구름·후행>26봉전")
    # 삼역역전(약세 정배열)
    bear = (tenkan < kijun) and (price < bot) and (price < past)
    if bear:
        return sell("일목 삼역역전", "trend", 0.8, "전환<기준·가격<구름·후행<26봉전")
    return None


@strategy("일목 구름 지지/저항", "trend")
def kumo_support_resistance(f):
    """추세 유지 중 가격이 구름 상단(지지)/하단(저항)에 근접해 되돌림. 추세 방향 추종."""
    closes = f.get("closes")
    ichi = f.get("ichimoku")
    if not ichi or not closes or len(closes) < 53:
        return None
    price = f.get("price")
    a = f.get("atr")
    top, bot = ichi.get("cloudTop"), ichi.get("cloudBottom")
    tenkan, kijun = ichi.get("tenkan"), ichi.get("kijun")
    if None in (price, top, bot, tenkan, kijun) or not a or a <= 0:
        return None
    # 가격이 구름 위(상승추세)에서 구름 상단(지지)으로 되돌림
    if price > top and (price - top) <= a and tenkan >= kijun:
        return buy("일목 구름 지지", "trend", 0.5, "상승추세 구름상단 지지 되돌림")
    # 가격이 구름 아래(하락추세)에서 구름 하단(저항)으로 반등
    if price < bot and (bot - price) <= a and tenkan <= kijun:
        return sell("일목 구름 저항", "trend", 0.5, "하락추세 구름하단 저항 반등")
    return None
