"""확장 캔들패턴(structure) 전략군.

opens/highs/lows/closes 를 직접 분석해 멀티봉 캔들 패턴을 인식한다.
features.candlePatterns 와 중복되지 않는 확장 패턴(3봉/2봉 위주)을 다룬다.
모든 함수는 데이터 부족·None 시 안전하게 None 을 반환한다.
"""
from __future__ import annotations
from .base import buy, sell, strategy


# ── 내부 헬퍼(순수 파이썬) ────────────────────────────────
def _ohlc(f, n):
    """최근 n봉의 (opens,highs,lows,closes) 슬라이스. 부족하면 None."""
    o = f.get("opens"); h = f.get("highs"); l = f.get("lows"); c = f.get("closes")
    if not o or not h or not l or not c:
        return None
    m = min(len(o), len(h), len(l), len(c))
    if m < n:
        return None
    return o[-n:], h[-n:], l[-n:], c[-n:]


def _body(op, cl):
    return abs(cl - op)


def _rng(hi, lo):
    return hi - lo


def _is_bull(op, cl):
    return cl > op


def _is_bear(op, cl):
    return cl < op


def _mid(op, cl):
    return (op + cl) / 2.0


# ── 적삼병 / 흑삼병 (Three White Soldiers / Three Black Crows) ──
@strategy("적삼병/흑삼병", "structure")
def three_soldiers_crows(f):
    s = _ohlc(f, 3)
    if s is None:
        return None
    o, h, l, c = s
    bodies = [_body(o[i], c[i]) for i in range(3)]
    rngs = [_rng(h[i], l[i]) for i in range(3)]
    if min(rngs) <= 0:
        return None
    # 몸통이 어느 정도 실하고(레인지의 50%+) 연속 진행
    solid = all(bodies[i] >= 0.5 * rngs[i] for i in range(3))
    if not solid:
        return None
    # 적삼병: 3연속 양봉, 종가 상승, 시가가 직전 몸통 안에서 출발
    bulls = all(_is_bull(o[i], c[i]) for i in range(3))
    if bulls and c[2] > c[1] > c[0]:
        in_body = o[1] >= o[0] and o[2] >= o[1] and o[1] <= c[0] and o[2] <= c[1]
        if in_body:
            return buy("적삼병", "structure", 0.7, "3연속 양봉(강세 지속)")
    # 흑삼병: 3연속 음봉, 종가 하락, 시가가 직전 몸통 안에서 출발
    bears = all(_is_bear(o[i], c[i]) for i in range(3))
    if bears and c[2] < c[1] < c[0]:
        in_body = o[1] <= o[0] and o[2] <= o[1] and o[1] >= c[0] and o[2] >= c[1]
        if in_body:
            return sell("흑삼병", "structure", 0.7, "3연속 음봉(약세 지속)")
    return None


# ── 관통형 / 먹구름형 (Piercing Line / Dark Cloud Cover) ──
@strategy("관통형/먹구름형", "structure")
def piercing_darkcloud(f):
    s = _ohlc(f, 2)
    if s is None:
        return None
    o, h, l, c = s
    b0 = _body(o[0], c[0]); b1 = _body(o[1], c[1])
    r0 = _rng(h[0], l[0])
    if r0 <= 0 or b0 <= 0 or b1 <= 0:
        return None
    # 첫 봉은 실체가 큰 추세봉이어야 의미가 있음
    if b0 < 0.5 * r0:
        return None
    mid0 = _mid(o[0], c[0])
    # 관통형: 첫 봉 음봉 → 둘째 봉 양봉, 갭하락 시가, 첫 음봉 몸통 중간 이상까지 회복(전체 돌파는 아님)
    if _is_bear(o[0], c[0]) and _is_bull(o[1], c[1]):
        if o[1] < c[0] and mid0 < c[1] < o[0]:
            return buy("관통형", "structure", 0.65, "음봉 후 몸통 절반 이상 회복")
    # 먹구름형: 첫 봉 양봉 → 둘째 봉 음봉, 갭상승 시가, 첫 양봉 몸통 중간 이하까지 잠식
    if _is_bull(o[0], c[0]) and _is_bear(o[1], c[1]):
        if o[1] > c[0] and o[0] < c[1] < mid0:
            return sell("먹구름형", "structure", 0.65, "양봉 후 몸통 절반 이상 잠식")
    return None


# ── 집게천장 / 집게바닥 (Tweezer Top / Bottom) ──
@strategy("집게천장/바닥", "structure")
def tweezer(f):
    s = _ohlc(f, 2)
    if s is None:
        return None
    o, h, l, c = s
    rngs = [_rng(h[i], l[i]) for i in range(2)]
    if min(rngs) <= 0:
        return None
    tol = 0.0015  # 0.15% 허용오차
    avg_r = (rngs[0] + rngs[1]) / 2.0
    if avg_r <= 0:
        return None
    # 집게바닥: 두 봉 저점이 거의 동일 + 둘째 봉 강세 전환(음→양 또는 종가 회복)
    if abs(l[0] - l[1]) <= tol * max(l[0], l[1]):
        if _is_bear(o[0], c[0]) and _is_bull(o[1], c[1]):
            return buy("집게바닥", "structure", 0.55, "동일 저점 후 강세전환")
    # 집게천장: 두 봉 고점이 거의 동일 + 둘째 봉 약세 전환(양→음)
    if abs(h[0] - h[1]) <= tol * max(h[0], h[1]):
        if _is_bull(o[0], c[0]) and _is_bear(o[1], c[1]):
            return sell("집게천장", "structure", 0.55, "동일 고점 후 약세전환")
    return None


# ── 삼내부 상승 / 하락 (Three Inside Up / Down) ──
@strategy("삼내부 상승/하락", "structure")
def three_inside(f):
    s = _ohlc(f, 3)
    if s is None:
        return None
    o, h, l, c = s
    b0 = _body(o[0], c[0])
    if b0 <= 0:
        return None
    hi0 = max(o[0], c[0]); lo0 = min(o[0], c[0])
    # 둘째 봉 몸통이 첫 봉 몸통 내부에 포함(하라미)
    inside = max(o[1], c[1]) <= hi0 and min(o[1], c[1]) >= lo0
    if not inside:
        return None
    # 삼내부 상승: 첫 음봉 + 내부 양봉 + 셋째 양봉이 첫 봉 시가 돌파
    if _is_bear(o[0], c[0]) and _is_bull(o[1], c[1]) and _is_bull(o[2], c[2]):
        if c[2] > o[0]:
            return buy("삼내부 상승", "structure", 0.6, "하락 하라미 후 상향 확정")
    # 삼내부 하락: 첫 양봉 + 내부 음봉 + 셋째 음봉이 첫 봉 시가 이탈
    if _is_bull(o[0], c[0]) and _is_bear(o[1], c[1]) and _is_bear(o[2], c[2]):
        if c[2] < o[0]:
            return sell("삼내부 하락", "structure", 0.6, "상승 하라미 후 하향 확정")
    return None


# ── 샅바형 (Belt Hold) ──
@strategy("샅바형", "structure")
def belt_hold(f):
    s = _ohlc(f, 1)
    if s is None:
        return None
    o, h, l, c = s
    op, hi, lo, cl = o[0], h[0], l[0], c[0]
    rng = _rng(hi, lo)
    if rng <= 0:
        return None
    body = _body(op, cl)
    if body < 0.6 * rng:
        return None
    # 강세 샅바형: 시가=저가 부근(아래꼬리 거의 없음), 양봉으로 길게 상승
    if _is_bull(op, cl) and (op - lo) <= 0.05 * rng:
        return buy("강세 샅바형", "structure", 0.5, "저가 시가 장대양봉(반등)")
    # 약세 샅바형: 시가=고가 부근(위꼬리 거의 없음), 음봉으로 길게 하락
    if _is_bear(op, cl) and (hi - op) <= 0.05 * rng:
        return sell("약세 샅바형", "structure", 0.5, "고가 시가 장대음봉(반락)")
    return None


# ── 십자별 (Doji Star) ──
@strategy("십자별", "structure")
def doji_star(f):
    s = _ohlc(f, 2)
    if s is None:
        return None
    o, h, l, c = s
    r0 = _rng(h[0], l[0]); r1 = _rng(h[1], l[1])
    if r0 <= 0 or r1 <= 0:
        return None
    b0 = _body(o[0], c[0]); b1 = _body(o[1], c[1])
    # 둘째 봉이 도지(몸통이 레인지의 10% 이하)
    if b1 > 0.1 * r1:
        return None
    # 첫 봉은 실체 있는 추세봉
    if b0 < 0.5 * r0:
        return None
    mid0 = _mid(o[0], c[0])
    doji_mid = _mid(o[1], c[1])
    # 상승십자별: 하락추세 음봉 후 갭하락 도지(바닥 반전 경계)
    if _is_bear(o[0], c[0]) and doji_mid < mid0:
        return buy("상승십자별", "structure", 0.5, "하락 후 도지(반전 신호)")
    # 하락십자별: 상승추세 양봉 후 갭상승 도지(천장 반전 경계)
    if _is_bull(o[0], c[0]) and doji_mid > mid0:
        return sell("하락십자별", "structure", 0.5, "상승 후 도지(반전 신호)")
    return None


# ── 잉태십자 (Harami Cross) ──
@strategy("잉태십자", "structure")
def harami_cross(f):
    s = _ohlc(f, 2)
    if s is None:
        return None
    o, h, l, c = s
    r1 = _rng(h[1], l[1])
    if r1 <= 0:
        return None
    b0 = _body(o[0], c[0]); b1 = _body(o[1], c[1])
    if b0 <= 0:
        return None
    # 둘째 봉이 도지에 가깝고(레인지 10% 이하), 첫 봉 몸통 내부에 포함
    if b1 > 0.1 * r1:
        return None
    hi0 = max(o[0], c[0]); lo0 = min(o[0], c[0])
    inside = max(o[1], c[1]) <= hi0 and min(o[1], c[1]) >= lo0
    if not inside:
        return None
    # 첫 봉이 큰 추세봉일 때 의미
    if b0 < 0.5 * _rng(h[0], l[0]):
        return None
    # 상승 잉태십자: 큰 음봉 내부의 도지(바닥 반전)
    if _is_bear(o[0], c[0]):
        return buy("상승 잉태십자", "structure", 0.55, "장대음봉 속 도지(반전)")
    # 하락 잉태십자: 큰 양봉 내부의 도지(천장 반전)
    if _is_bull(o[0], c[0]):
        return sell("하락 잉태십자", "structure", 0.55, "장대양봉 속 도지(반전)")
    return None
