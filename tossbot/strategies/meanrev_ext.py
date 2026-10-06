"""평균회귀 확장(mean-reversion extension) 전략군.

RSI(2) Connors, 볼린저 %B 극단, TTM 스퀴즈, CCI ±100 회귀,
수익률 z-score, Williams %R 반전. 카테고리: meanrev | volatility.
"""
from __future__ import annotations
from .base import buy, sell, strategy
from .. import indicators as ind


# ── RSI(2) Connors ───────────────────────────────────────
@strategy("RSI(2) Connors", "meanrev")
def rsi2_connors(f):
    """초단기 RSI(2) 극단 + 장기 추세 필터(상승추세 눌림목 매수)."""
    closes = f.get("closes")
    if not closes or len(closes) < 60:
        return None
    sma200 = ind.sma(closes, min(200, len(closes)))  # 가용 범위 내 장기 평균
    sma5 = f.get("sma5")
    r2 = ind.rsi(closes, 2)
    if r2 is None or sma200 is None:
        return None
    price = f.get("price") or closes[-1]
    # 상승추세(가격이 장기평균 위) + RSI2 극단 과매도 → 눌림목 매수
    if price > sma200 and r2 < 10:
        st = min(1.0, (10 - r2) / 10 * 0.5 + 0.5)
        return buy("RSI(2) 눌림목", "meanrev", st, f"상승추세 RSI(2) {r2:.0f}<10")
    # 하락추세(가격이 장기평균 아래) + RSI2 극단 과매수 → 반등 소진 매도
    if price < sma200 and r2 > 90:
        st = min(1.0, (r2 - 90) / 10 * 0.5 + 0.5)
        return sell("RSI(2) 반등소진", "meanrev", st, f"하락추세 RSI(2) {r2:.0f}>90")
    # 추세 무관 RSI5 단기 회귀(보조)
    if sma5 is not None and r2 < 5:
        return buy("RSI(2) 극단과매도", "meanrev", 0.45, f"RSI(2) {r2:.0f}<5")
    return None


# ── 볼린저 %B 극단 ───────────────────────────────────────
@strategy("볼린저 %B 극단", "meanrev")
def bollinger_pctb_extreme(f):
    """%B > 1(상단 이탈) 또는 < 0(하단 이탈) 시 밴드 내부 회귀 베팅."""
    boll = f.get("boll")
    if not boll:
        return None
    pctb = boll.get("pctB")
    if pctb is None:
        return None
    if pctb < 0.0:
        st = min(1.0, 0.5 + (-pctb))
        return buy("%B<0 회귀", "meanrev", st, f"%B {pctb:.2f}<0(하단 이탈)")
    if pctb > 1.0:
        st = min(1.0, 0.5 + (pctb - 1.0))
        return sell("%B>1 회귀", "meanrev", st, f"%B {pctb:.2f}>1(상단 이탈)")
    return None


# ── TTM 스퀴즈 ───────────────────────────────────────────
@strategy("TTM 스퀴즈 해제", "volatility")
def ttm_squeeze(f):
    """볼린저밴드가 켈트너채널 내부(스퀴즈)였다가 벗어나며 방향 분출."""
    closes = f.get("closes")
    highs = f.get("highs")
    lows = f.get("lows")
    if not closes or len(closes) < 25:
        return None
    boll = ind.bollinger(closes, 20, 2.0)
    kel = ind.keltner(highs, lows, closes, 20, 1.5)
    if not boll or not kel:
        return None
    # 현재 스퀴즈 여부: BB가 Keltner 내부에 완전히 들어가 있으면 스퀴즈 ON
    squeeze_on = (boll["lower"] > kel["lower"]) and (boll["upper"] < kel["upper"])
    # 직전 봉 스퀴즈 여부
    boll_p = ind.bollinger(closes[:-1], 20, 2.0)
    kel_p = ind.keltner(highs[:-1], lows[:-1], closes[:-1], 20, 1.5)
    if not boll_p or not kel_p:
        return None
    squeeze_prev = (boll_p["lower"] > kel_p["lower"]) and (boll_p["upper"] < kel_p["upper"])
    # 스퀴즈 해제(직전 ON → 현재 OFF) 시 모멘텀 방향으로 진입
    if squeeze_prev and not squeeze_on:
        mid = boll["mid"]
        price = f.get("price") or closes[-1]
        mom = ind.roc(closes, 6)
        if price > mid and (mom is None or mom >= 0):
            return buy("스퀴즈 상방 분출", "volatility", 0.6, "BB가 KC 이탈·중심선 위")
        if price < mid and (mom is None or mom <= 0):
            return sell("스퀴즈 하방 분출", "volatility", 0.6, "BB가 KC 이탈·중심선 아래")
    return None


# ── CCI ±100 회귀 ────────────────────────────────────────
@strategy("CCI ±100 반전", "meanrev")
def cci_revert(f):
    """CCI가 +100/-100 극단을 찍고 다시 안쪽으로 되돌아올 때 회귀 진입."""
    closes = f.get("closes")
    highs = f.get("highs")
    lows = f.get("lows")
    if not closes or len(closes) < 21:
        return None
    cci_now = f.get("cci")
    if cci_now is None:
        cci_now = ind.cci(highs, lows, closes, 20)
    cci_prev = ind.cci(highs[:-1], lows[:-1], closes[:-1], 20)
    if cci_now is None or cci_prev is None:
        return None
    # -100 아래에서 위로 재진입 → 과매도 반전 매수
    if cci_prev <= -100 < cci_now:
        return buy("CCI -100 재진입", "meanrev", 0.6, f"CCI {cci_prev:.0f}→{cci_now:.0f}")
    # +100 위에서 아래로 재진입 → 과매수 반전 매도
    if cci_prev >= 100 > cci_now:
        return sell("CCI +100 재진입", "meanrev", 0.6, f"CCI {cci_prev:.0f}→{cci_now:.0f}")
    return None


# ── 수익률 z-score ───────────────────────────────────────
@strategy("수익률 z-score 회귀", "meanrev")
def return_zscore(f):
    """일간 수익률의 z-score가 극단(±2σ)일 때 평균 회귀 베팅."""
    closes = f.get("closes")
    if not closes or len(closes) < 25:
        return None
    n = 20
    rets = []
    for i in range(len(closes) - n, len(closes)):
        prev = closes[i - 1]
        if prev:
            rets.append((closes[i] / prev - 1.0) * 100.0)
    if len(rets) < n:
        return None
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / len(rets)
    sd = var ** 0.5
    if sd <= 0:
        return None
    last_ret = rets[-1]
    z = (last_ret - mean) / sd
    # 비정상적 급락(음의 극단) → 반등 매수
    if z < -2.0:
        st = min(1.0, 0.4 + (-z - 2.0) * 0.25)
        return buy("수익률 z-score 급락", "meanrev", st, f"z {z:.1f}<-2(과대낙폭)")
    # 비정상적 급등(양의 극단) → 되돌림 매도
    if z > 2.0:
        st = min(1.0, 0.4 + (z - 2.0) * 0.25)
        return sell("수익률 z-score 급등", "meanrev", st, f"z {z:.1f}>+2(과대급등)")
    return None


# ── Williams %R 반전 ─────────────────────────────────────
@strategy("Williams %R 반전", "meanrev")
def williams_revert(f):
    """%R이 극단(-80/-20)을 벗어나 안쪽으로 전환할 때 회귀 진입."""
    closes = f.get("closes")
    highs = f.get("highs")
    lows = f.get("lows")
    if not closes or len(closes) < 16:
        return None
    wr_now = f.get("williamsR")
    if wr_now is None:
        wr_now = ind.williams_r(highs, lows, closes, 14)
    wr_prev = ind.williams_r(highs[:-1], lows[:-1], closes[:-1], 14)
    if wr_now is None or wr_prev is None:
        return None
    # 과매도(-80 이하)에서 위로 전환 → 반등 매수
    if wr_prev <= -80 < wr_now:
        return buy("%R 과매도 반전", "meanrev", 0.55, f"%R {wr_prev:.0f}→{wr_now:.0f}")
    # 과매수(-20 이상)에서 아래로 전환 → 하락 매도
    if wr_prev >= -20 > wr_now:
        return sell("%R 과매수 반전", "meanrev", 0.55, f"%R {wr_prev:.0f}→{wr_now:.0f}")
    return None
