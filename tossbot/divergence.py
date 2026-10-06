"""가격 vs 오실레이터(RSI/MACD) 다이버전스 감지.

regular bullish : 가격 저점 낮아짐(LL) + 오실레이터 저점 높아짐(HL) → 반등 신호
regular bearish : 가격 고점 높아짐(HH) + 오실레이터 고점 낮아짐(LH) → 하락 신호
hidden          : 추세 지속형(가격 HL+osc LL=bull / 가격 LH+osc HH=bear)
"""
from __future__ import annotations
from typing import Dict, List, Optional


def _swings(values: List[float], k: int = 3):
    sh, sl = [], []
    n = len(values)
    for i in range(k, n - k):
        w = values[i - k:i + k + 1]
        if values[i] == max(w) and values[i] > values[i - 1]:
            sh.append((i, values[i]))
        if values[i] == min(w) and values[i] < values[i - 1]:
            sl.append((i, values[i]))
    return sh, sl


def _detect(closes: List[float], osc: List[Optional[float]], k: int = 3) -> Dict[str, Optional[str]]:
    # bull/bear 는 서로 다른 스윙 블록(고점/저점)에서 잡히므로 별도 플래그로 모은다.
    # 같은 'regular'/'hidden' 키에 바로 덮어쓰면 양쪽 동시 발생 시 뒤 블록(저점=bullish)이
    # 무조건 이겨버리므로, 분리 저장한 뒤 마지막에 상충(둘 다 True)이면 None(중립)으로 합친다.
    regular_bull = regular_bear = False
    hidden_bull = hidden_bear = False
    sh, sl = _swings(closes, k)

    def ov(i):
        return osc[i] if 0 <= i < len(osc) and osc[i] is not None else None

    if len(sh) >= 2:
        (i1, p1), (i2, p2) = sh[-2], sh[-1]
        a, b = ov(i1), ov(i2)
        if a is not None and b is not None:
            if p2 > p1 and b < a:
                regular_bear = True
            elif p2 < p1 and b > a:
                hidden_bear = True
    if len(sl) >= 2:
        (i1, p1), (i2, p2) = sl[-2], sl[-1]
        a, b = ov(i1), ov(i2)
        if a is not None and b is not None:
            if p2 < p1 and b > a:
                regular_bull = True
            elif p2 > p1 and b < a:
                hidden_bull = True

    def _resolve(bull: bool, bear: bool) -> Optional[str]:
        # 둘 다 잡히면 상충 → 중립(None). 한쪽만이면 해당 방향, 아무것도 없으면 None.
        if bull and bear:
            return None
        if bull:
            return "bullish"
        if bear:
            return "bearish"
        return None

    return {
        # 분리 플래그(상충 판정·디버깅용)
        "regular_bull": regular_bull, "regular_bear": regular_bear,
        "hidden_bull": hidden_bull, "hidden_bear": hidden_bear,
        # 상충 해소된 공개 키(기존 소비처 호환: structure.py, summary)
        "regular": _resolve(regular_bull, regular_bear),
        "hidden": _resolve(hidden_bull, hidden_bear),
    }


def analyze_divergence(closes, rsi_series, macd_hist_series, k=3) -> Dict:
    rsi_d = _detect(closes, rsi_series, k)
    macd_d = _detect(closes, macd_hist_series, k)
    summary = None
    # 각 시리즈의 상충 해소된 regular 만 집계(상충 시 None → 표 없음). bull/bear 동시 발생
    # 시리즈는 더 이상 bullish 로 오집계되지 않는다.
    votes = [rsi_d["regular"], macd_d["regular"]]
    if "bullish" in votes and "bearish" not in votes:
        summary = "bullish"
    elif "bearish" in votes and "bullish" not in votes:
        summary = "bearish"
    return {"rsi": rsi_d, "macd": macd_d, "summary": summary}
