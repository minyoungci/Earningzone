"""거래량 확장(volume_ext) 전략군.

OBV 추세/다이버전스, 거래량 마름→돌파, 클라이맥스 거래량, 누적/분산(A/D Line) 기울기,
MFI 크로스, 거래대금(가격*거래량) 급증. 카테고리: breakout / structure.
표준 라이브러리만 사용. 데이터 부족 시 None 반환.
"""
from __future__ import annotations
from .base import buy, sell, strategy
from .. import indicators as ind


def _sma(vals, n):
    if not vals or len(vals) < n or n <= 0:
        return None
    return sum(vals[-n:]) / n


def _slope_norm(seq, lookback):
    """seq[-1] - seq[-(lookback+1)] 를 기준값으로 정규화한 기울기. None 가드."""
    if not seq or len(seq) < lookback + 1:
        return None
    base = abs(seq[-(lookback + 1)]) or 1.0
    return (seq[-1] - seq[-(lookback + 1)]) / base


def _ad_line(highs, lows, closes, vols):
    """누적/분산(Accumulation/Distribution) Line 시계열."""
    n = len(closes)
    if n == 0:
        return []
    out = []
    acc = 0.0
    for i in range(n):
        hi, lo, cl = highs[i], lows[i], closes[i]
        rng = hi - lo
        if rng > 0:
            mfm = ((cl - lo) - (hi - cl)) / rng
        else:
            mfm = 0.0
        acc += mfm * (vols[i] if i < len(vols) else 0.0)
        out.append(acc)
    return out


# ── 1) OBV 추세 (가격·OBV 동반 추세 확인) ───────────────────
@strategy("OBV 추세", "structure")
def obv_trend(f):
    closes = f.get("closes"); vols = f.get("volumes")
    if not closes or not vols or len(closes) < 40:
        return None
    obv = ind.obv_series(closes, vols)
    obv_sl = _slope_norm(obv, 20)
    price_sl = ind.pct_change(closes, 20)
    if obv_sl is None or price_sl is None:
        return None
    # OBV가 뚜렷이 상승하고 가격도 상승 → 매집 동반 상승
    if obv_sl > 0.15 and price_sl > 0:
        return buy("OBV 상승추세", "structure",
                   min(1.0, abs(obv_sl) + 0.35),
                   f"OBV 20봉 +{obv_sl*100:.0f}%·가격동반↑")
    # OBV가 뚜렷이 하락하고 가격도 하락 → 분산 동반 하락
    if obv_sl < -0.15 and price_sl < 0:
        return sell("OBV 하락추세", "structure",
                    min(1.0, abs(obv_sl) + 0.35),
                    f"OBV 20봉 {obv_sl*100:.0f}%·가격동반↓")
    return None


# ── 2) OBV 다이버전스 (가격 vs OBV 방향 불일치) ─────────────
@strategy("OBV 다이버전스", "structure")
def obv_divergence(f):
    closes = f.get("closes"); vols = f.get("volumes")
    if not closes or not vols or len(closes) < 40:
        return None
    obv = ind.obv_series(closes, vols)
    look = 20
    if len(obv) < look + 1 or len(closes) < look + 1:
        return None
    price_chg = ind.pct_change(closes, look)
    obv_sl = _slope_norm(obv, look)
    if price_chg is None or obv_sl is None:
        return None
    # 강세 다이버전스: 가격은 하락했는데 OBV는 상승(저점에서 매집)
    if price_chg < -2 and obv_sl > 0.1:
        return buy("OBV 강세 다이버전스", "structure", 0.6,
                   f"가격 {price_chg:+.1f}%↓ vs OBV↑(매집)")
    # 약세 다이버전스: 가격은 상승했는데 OBV는 하락(상단에서 분산)
    if price_chg > 2 and obv_sl < -0.1:
        return sell("OBV 약세 다이버전스", "structure", 0.6,
                    f"가격 {price_chg:+.1f}%↑ vs OBV↓(분산)")
    return None


# ── 3) 거래량 마름 → 돌파 (squeeze breakout) ────────────────
@strategy("거래량 마름 돌파", "breakout")
def volume_dryup_breakout(f):
    closes = f.get("closes"); highs = f.get("highs")
    lows = f.get("lows"); vols = f.get("volumes")
    if not closes or not vols or len(closes) < 30:
        return None
    price = f.get("price") or closes[-1]
    cur_vol = vols[-1]
    # 직전(현재봉 제외) 거래량 평균 — 거래량이 평소보다 말라 있었는지
    prior_vols = vols[-21:-1]
    avg_prior = _sma(prior_vols, len(prior_vols)) if prior_vols else None
    if not avg_prior or avg_prior <= 0:
        return None
    # 돌파 기준선: 직전 N봉 고가(현재봉 제외)
    if len(highs) < 11 or len(lows) < 11:
        return None
    prior_high = max(highs[-11:-1])
    prior_low = min(lows[-11:-1])
    vol_ratio = cur_vol / avg_prior
    # 직전 며칠간 거래량이 평균 이하로 위축되어 있었는지 확인
    recent_quiet = vols[-6:-1]
    quiet = recent_quiet and (sum(recent_quiet) / len(recent_quiet)) < avg_prior * 0.9
    if not quiet:
        return None
    # 거래량 동반 상향 돌파
    if vol_ratio >= 1.8 and price > prior_high:
        return buy("거래량 마름후 돌파", "breakout",
                   min(1.0, 0.45 + (vol_ratio - 1.8) / 4),
                   f"거래량 위축후 x{vol_ratio:.1f} 고점돌파")
    # 거래량 동반 하향 이탈
    if vol_ratio >= 1.8 and price < prior_low:
        return sell("거래량 마름후 이탈", "breakout",
                    min(1.0, 0.45 + (vol_ratio - 1.8) / 4),
                    f"거래량 위축후 x{vol_ratio:.1f} 저점이탈")
    return None


# ── 4) 클라이맥스 거래량 (>3배 + 장대 캔들) ─────────────────
@strategy("클라이맥스 거래량", "structure")
def climax_volume(f):
    opens = f.get("opens"); closes = f.get("closes")
    highs = f.get("highs"); lows = f.get("lows"); vols = f.get("volumes")
    if not closes or not vols or not opens or len(closes) < 30:
        return None
    cur_vol = vols[-1]
    avg_prior = _sma(vols[-21:-1], 20)
    if not avg_prior or avg_prior <= 0:
        return None
    vol_ratio = cur_vol / avg_prior
    if vol_ratio < 3.0:
        return None
    o, c = opens[-1], closes[-1]
    hi, lo = highs[-1], lows[-1]
    rng = hi - lo
    if rng <= 0 or o <= 0:
        return None
    body = abs(c - o)
    # 장대 캔들: 몸통이 전체 범위의 60% 이상
    if body < rng * 0.6:
        return None
    body_pct = body / o * 100
    # 직전 추세(소진 클라이맥스 판단용)
    prior_ret = ind.pct_change(closes, 10)
    strength = min(1.0, 0.5 + (vol_ratio - 3.0) / 6)
    # 하락 클라이맥스(장대 음봉, 선행 하락) → 투매 소진, 반등 기대
    if c < o:
        if prior_ret is not None and prior_ret < -3:
            return buy("매도 클라이맥스", "structure", strength,
                       f"거래량 x{vol_ratio:.1f} 장대음봉(투매소진)")
        return sell("매도 클라이맥스", "structure", min(1.0, strength * 0.8),
                    f"거래량 x{vol_ratio:.1f} 장대음봉")
    # 상승 클라이맥스(장대 양봉, 선행 상승) → 과열 소진, 차익 경계
    if c > o:
        if prior_ret is not None and prior_ret > 3:
            return sell("매수 클라이맥스", "structure", strength,
                        f"거래량 x{vol_ratio:.1f} 장대양봉(과열소진)")
        return buy("매수 클라이맥스", "structure", min(1.0, strength * 0.8),
                   f"거래량 x{vol_ratio:.1f} 장대양봉")
    return None


# ── 5) A/D Line 기울기 (누적/분산) ──────────────────────────
@strategy("A/D Line 기울기", "structure")
def ad_line_slope(f):
    closes = f.get("closes"); highs = f.get("highs")
    lows = f.get("lows"); vols = f.get("volumes")
    if not closes or not vols or len(closes) < 35:
        return None
    ad = _ad_line(highs, lows, closes, vols)
    ad_sl = _slope_norm(ad, 15)
    if ad_sl is None:
        return None
    price_sl = ind.pct_change(closes, 15)
    if price_sl is None:
        return None
    # A/D 상승(누적) + 가격 동반/선행 → 매집 신호
    if ad_sl > 0.1 and price_sl >= -1:
        return buy("A/D Line 누적", "structure",
                   min(1.0, 0.4 + abs(ad_sl) * 0.5),
                   f"A/D 15봉 누적(+{ad_sl*100:.0f}%)")
    # A/D 하락(분산) + 가격 정체/하락 → 분산 신호
    if ad_sl < -0.1 and price_sl <= 1:
        return sell("A/D Line 분산", "structure",
                    min(1.0, 0.4 + abs(ad_sl) * 0.5),
                    f"A/D 15봉 분산({ad_sl*100:.0f}%)")
    return None


# ── 6) MFI 크로스 (자금흐름 20/80 라인 교차) ────────────────
@strategy("MFI 크로스", "breakout")
def mfi_cross(f):
    highs = f.get("highs"); lows = f.get("lows")
    closes = f.get("closes"); vols = f.get("volumes")
    if not closes or not vols or len(closes) < 30:
        return None
    mfi_now = ind.mfi(highs, lows, closes, vols, 14)
    mfi_prev = (ind.mfi(highs[:-1], lows[:-1], closes[:-1], vols[:-1], 14)
                if len(closes) > 16 else None)
    if mfi_now is None or mfi_prev is None:
        return None
    # 과매도(20) 상향 돌파 → 자금 유입 전환
    if mfi_prev <= 20 < mfi_now:
        return buy("MFI 20 상향돌파", "breakout", 0.55,
                   f"MFI {mfi_prev:.0f}→{mfi_now:.0f}(자금유입)")
    # 과매수(80) 하향 이탈 → 자금 이탈 전환
    if mfi_prev >= 80 > mfi_now:
        return sell("MFI 80 하향이탈", "breakout", 0.55,
                    f"MFI {mfi_prev:.0f}→{mfi_now:.0f}(자금이탈)")
    return None


# ── 7) 거래대금(가격*거래량) 급증 ───────────────────────────
@strategy("거래대금 급증", "breakout")
def turnover_surge(f):
    closes = f.get("closes"); vols = f.get("volumes")
    if not closes or not vols or len(closes) < 30:
        return None
    n = min(len(closes), len(vols))
    if n < 21:
        return None
    turnover = [closes[i] * vols[i] for i in range(n)]
    cur = turnover[-1]
    avg_prior = _sma(turnover[-21:-1], 20)
    if not avg_prior or avg_prior <= 0:
        return None
    ratio = cur / avg_prior
    if ratio < 2.0:
        return None
    day_ret = ind.pct_change(closes, 1)
    if day_ret is None:
        return None
    strength = min(1.0, 0.45 + (ratio - 2.0) / 6)
    # 거래대금 급증 + 양봉 → 관심 유입(매수)
    if day_ret > 0.3:
        return buy("거래대금 급증↑", "breakout", strength,
                   f"거래대금 x{ratio:.1f}·당일 {day_ret:+.1f}%")
    # 거래대금 급증 + 음봉 → 대량 매물 출회(매도)
    if day_ret < -0.3:
        return sell("거래대금 급증↓", "breakout", strength,
                    f"거래대금 x{ratio:.1f}·당일 {day_ret:+.1f}%")
    return None
