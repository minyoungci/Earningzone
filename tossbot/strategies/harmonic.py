"""하모닉/피보나치(harmonic) 전략군.

최근 주요 스윙(고점-저점)을 직접 검출해 피보나치 되돌림/확장 레벨을 계산하고,
지지/저항 반등·돌파, ABCD·가틀리·배트 하모닉 패턴 근사 전략을 제공합니다.
모든 계산은 순수 파이썬으로 직접 구현하며, 데이터 부족 시 None을 반환합니다.
"""
from __future__ import annotations
from .base import buy, sell, strategy


# ── 스윙(지그재그) 검출 유틸 ──────────────────────────────
def _swings(highs, lows, left=2, right=2):
    """프랙탈 기반 스윙 고/저점 검출.

    반환: 시간 오름차순 [{'idx','price','kind'}] (kind: 'H'|'L').
    인접 동일종류 스윙은 더 극단값으로 합쳐 H/L 교대가 되도록 정리.
    데이터 부족/검출 실패 시 빈 리스트.
    """
    n = len(highs)
    if n < left + right + 1 or len(lows) != n:
        return []
    raw = []
    for i in range(left, n - right):
        hh = highs[i]
        is_high = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if highs[j] >= hh:
                is_high = False
                break
        if is_high:
            raw.append({"idx": i, "price": hh, "kind": "H"})
            continue
        ll = lows[i]
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if lows[j] <= ll:
                is_low = False
                break
        if is_low:
            raw.append({"idx": i, "price": ll, "kind": "L"})
    if not raw:
        return []
    raw.sort(key=lambda s: s["idx"])
    # 같은 종류 연속 → 더 극단값만 유지(H는 max, L은 min)
    merged = [raw[0]]
    for s in raw[1:]:
        last = merged[-1]
        if s["kind"] == last["kind"]:
            if (s["kind"] == "H" and s["price"] >= last["price"]) or \
               (s["kind"] == "L" and s["price"] <= last["price"]):
                merged[-1] = s
        else:
            merged.append(s)
    return merged


def _last_leg(highs, lows, left=2, right=2):
    """가장 최근의 (스윙고점, 스윙저점) 한 다리(leg)를 반환.

    반환: (hi_price, lo_price, direction) 또는 None.
    direction: 'up' = 저점→고점(상승 다리), 'down' = 고점→저점(하락 다리).
    """
    sw = _swings(highs, lows, left, right)
    if len(sw) < 2:
        return None
    a, b = sw[-2], sw[-1]
    if a["kind"] == b["kind"]:
        return None
    if a["kind"] == "L" and b["kind"] == "H":
        return (b["price"], a["price"], "up")
    if a["kind"] == "H" and b["kind"] == "L":
        return (a["price"], b["price"], "down")
    return None


def _ratio(x, target, tol):
    """x가 target 비율의 ±tol 허용오차 안에 있으면 근접도(0..1) 반환, 아니면 None."""
    if target == 0:
        return None
    diff = abs(x - target)
    if diff > tol:
        return None
    return 1.0 - diff / tol  # 정확히 맞을수록 1에 가까움


# ── 피보나치 되돌림 반등/되돌림 ───────────────────────────
@strategy("피보나치 되돌림 반등", "structure")
def fib_retrace_bounce(f):
    """직전 상승 다리의 되돌림 구간(0.382/0.5/0.618/0.786)에서의 반등(매수)·
    하락 다리 되돌림 저항에서의 되돌림(매도) 근접 신호."""
    highs = f["highs"]; lows = f["lows"]
    price = f.get("price")
    if price is None or len(highs) < 30:
        return None
    leg = _last_leg(highs, lows)
    if not leg:
        return None
    hi, lo, direction = leg
    rng = hi - lo
    if rng <= 0:
        return None
    fibs = (0.382, 0.5, 0.618, 0.786)
    tol = max(rng * 0.025, 1e-9)  # 가격기준 허용오차(다리 폭의 2.5%)
    if direction == "up":
        # 상승 다리 → 고점에서 아래로 되돌림 레벨 = hi - rng*r, 지지 반등
        for r in fibs:
            lvl = hi - rng * r
            near = _ratio(price, lvl, tol)
            if near is not None:
                return buy("피보나치 되돌림 지지", "structure", 0.45 + 0.25 * near,
                           f"상승다리 {r:.3f} 되돌림 지지 근접")
    else:
        # 하락 다리 → 저점에서 위로 되돌림 레벨 = lo + rng*r, 저항 되돌림
        for r in fibs:
            lvl = lo + rng * r
            near = _ratio(price, lvl, tol)
            if near is not None:
                return sell("피보나치 되돌림 저항", "structure", 0.45 + 0.25 * near,
                            f"하락다리 {r:.3f} 되돌림 저항 근접")
    return None


# ── 골든포켓(0.618~0.786) 정밀 반등 ───────────────────────
@strategy("피보나치 골든포켓", "structure")
def fib_golden_pocket(f):
    """0.618~0.786 사이 골든포켓 구간에서의 반등/되돌림. 추세 정렬 시 가중."""
    highs = f["highs"]; lows = f["lows"]
    price = f.get("price")
    if price is None or len(highs) < 30:
        return None
    leg = _last_leg(highs, lows)
    if not leg:
        return None
    hi, lo, direction = leg
    rng = hi - lo
    if rng <= 0:
        return None
    if direction == "up":
        lo_lvl = hi - rng * 0.786
        hi_lvl = hi - rng * 0.618
        if lo_lvl <= price <= hi_lvl:
            base = 0.6
            if f.get("rsi") is not None and f["rsi"] < 45:
                base += 0.1
            return buy("골든포켓 지지", "structure", min(1.0, base),
                       "0.618~0.786 골든포켓 지지 반등 기대")
    else:
        lo_lvl = lo + rng * 0.618
        hi_lvl = lo + rng * 0.786
        if lo_lvl <= price <= hi_lvl:
            base = 0.6
            if f.get("rsi") is not None and f["rsi"] > 55:
                base += 0.1
            return sell("골든포켓 저항", "structure", min(1.0, base),
                        "0.618~0.786 골든포켓 저항 되돌림 경계")
    return None


# ── 피보나치 확장 돌파 ────────────────────────────────────
@strategy("피보나치 확장 돌파", "breakout")
def fib_extension_break(f):
    """다리 끝(고/저점) 너머 확장 레벨(1.272/1.618) 돌파 모멘텀."""
    highs = f["highs"]; lows = f["lows"]
    price = f.get("price")
    if price is None or len(highs) < 30:
        return None
    leg = _last_leg(highs, lows)
    if not leg:
        return None
    hi, lo, direction = leg
    rng = hi - lo
    if rng <= 0:
        return None
    if direction == "up":
        ext1 = hi + rng * (1.272 - 1.0)
        ext2 = hi + rng * (1.618 - 1.0)
        if price >= ext2 * 0.999:
            return buy("피보나치 1.618 확장 돌파", "breakout", 0.65, "상승 다리 1.618 확장 돌파")
        if price >= ext1 * 0.999:
            return buy("피보나치 1.272 확장 돌파", "breakout", 0.55, "상승 다리 1.272 확장 돌파")
    else:
        ext1 = lo - rng * (1.272 - 1.0)
        ext2 = lo - rng * (1.618 - 1.0)
        if price <= ext2 * 1.001:
            return sell("피보나치 1.618 확장 이탈", "breakout", 0.65, "하락 다리 1.618 확장 하락")
        if price <= ext1 * 1.001:
            return sell("피보나치 1.272 확장 이탈", "breakout", 0.55, "하락 다리 1.272 확장 하락")
    return None


# ── ABCD 하모닉 근사 ──────────────────────────────────────
@strategy("ABCD 하모닉", "structure")
def abcd_pattern(f):
    """AB=CD 근사: 최근 4개 스윙(X 없이 A-B-C-D)에서 BC 되돌림 0.382~0.886,
    CD=AB 길이 근접 시 D 완성점에서의 반전 신호."""
    highs = f["highs"]; lows = f["lows"]
    price = f.get("price")
    if price is None or len(highs) < 30:
        return None
    sw = _swings(highs, lows)
    if len(sw) < 4:
        return None
    A, B, C, D = sw[-4], sw[-3], sw[-2], sw[-1]
    # 교대 패턴 확인
    kinds = [A["kind"], B["kind"], C["kind"], D["kind"]]
    if kinds not in (["L", "H", "L", "H"], ["H", "L", "H", "L"]):
        return None
    ab = abs(B["price"] - A["price"])
    bc = abs(C["price"] - B["price"])
    cd = abs(D["price"] - C["price"])
    if ab <= 0 or bc <= 0:
        return None
    bc_ret = bc / ab
    cd_ab = cd / ab
    # BC 되돌림 0.382~0.886, CD≈AB(±20%)
    if not (0.30 <= bc_ret <= 0.95):
        return None
    if abs(cd_ab - 1.0) > 0.25:
        return None
    # D 완성점 근접 확인(현재가가 D 부근)
    leg_rng = abs(D["price"] - C["price"]) or 1e-9
    if abs(price - D["price"]) > leg_rng * 0.15:
        return None
    quality = 1.0 - abs(cd_ab - 1.0) / 0.25
    strength = min(1.0, 0.5 + 0.2 * quality)
    if D["kind"] == "L":  # 바닥 D → 강세 반전
        return buy("ABCD 강세 완성", "structure", strength, "AB=CD 바닥 D 완성(반등)")
    return sell("ABCD 약세 완성", "structure", strength, "AB=CD 천장 D 완성(반락)")


# ── 가틀리(Gartley) 하모닉 근사 ───────────────────────────
@strategy("가틀리 하모닉", "structure")
def gartley_pattern(f):
    """XABCD 5점 가틀리 근사: AB=XA의 0.618, D=XA의 0.786 되돌림.
    D 완성점에서 반전 신호(허용오차 내 비율 매칭)."""
    sig = _xabcd(f, name="가틀리", b_ratio=0.618, b_tol=0.10,
                 d_ratio=0.786, d_tol=0.08, base_strength=0.6)
    return sig


# ── 배트(Bat) 하모닉 근사 ─────────────────────────────────
@strategy("배트 하모닉", "structure")
def bat_pattern(f):
    """XABCD 5점 배트 근사: AB=XA의 0.382~0.5, D=XA의 0.886 되돌림.
    D 완성점에서 반전 신호."""
    sig = _xabcd(f, name="배트", b_ratio=0.44, b_tol=0.12,
                 d_ratio=0.886, d_tol=0.06, base_strength=0.6)
    return sig


def _xabcd(f, name, b_ratio, b_tol, d_ratio, d_tol, base_strength):
    """XABCD 하모닉 공통 검출기.

    - AB = XA 의 b_ratio (±b_tol) 되돌림
    - D  = XA 의 d_ratio (±d_tol) 되돌림 (D 완성점이 현재가 부근)
    - BC 는 AB의 0.382~0.886 사이(완만한 일반 조건)
    데이터/패턴 불충족 시 None.
    """
    highs = f.get("highs"); lows = f.get("lows")
    price = f.get("price")
    if not highs or not lows or price is None or len(highs) < 35:
        return None
    sw = _swings(highs, lows)
    if len(sw) < 5:
        return None
    X, A, B, C, D = sw[-5], sw[-4], sw[-3], sw[-2], sw[-1]
    kinds = [s["kind"] for s in (X, A, B, C, D)]
    bullish = kinds == ["L", "H", "L", "H", "L"]   # D가 바닥 → 강세
    bearish = kinds == ["H", "L", "H", "L", "H"]   # D가 천장 → 약세
    if not (bullish or bearish):
        return None
    xa = abs(A["price"] - X["price"])
    ab = abs(B["price"] - A["price"])
    bc = abs(C["price"] - B["price"])
    xd = abs(D["price"] - X["price"])
    if xa <= 0 or ab <= 0:
        return None
    ab_xa = ab / xa
    d_xa = xd / xa
    bc_ab = bc / ab
    nb = _ratio(ab_xa, b_ratio, b_tol)
    nd = _ratio(d_xa, d_ratio, d_tol)
    if nb is None or nd is None:
        return None
    if not (0.30 <= bc_ab <= 0.95):
        return None
    # D 완성점이 현재가 부근인지 확인
    leg_rng = abs(D["price"] - C["price"]) or 1e-9
    if abs(price - D["price"]) > leg_rng * 0.2:
        return None
    strength = min(1.0, base_strength + 0.2 * ((nb + nd) / 2))
    if bullish:
        return buy(f"{name} 강세 완성", "structure", strength,
                   f"{name} D점 {d_ratio:.3f} 되돌림 강세 반전")
    return sell(f"{name} 약세 완성", "structure", strength,
                f"{name} D점 {d_ratio:.3f} 되돌림 약세 반전")
