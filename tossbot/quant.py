"""퀀트 종목 발굴 — 팩터 스크리닝 + 매매 플랜(진입존/목표/손절/R:R).

유니버스 전 종목을 analysis.analyze() 한 번씩 돌려(캔들 재조회 없음) 팩터를 추출하고,
리서치 근거 가중치로 quantScore(0~100)를 산출한 뒤 지지/저항 기반 매매 플랜을 붙입니다.

⚠️ 산출되는 점수·플랜은 교육용 휴리스틱이며 투자 권유가 아닙니다. (표준 라이브러리만 사용)
"""
from __future__ import annotations

import copy
import time
from typing import Dict, List, Optional

from . import config
from .analysis import analyze
from .client import TossAPIError
from .cache import TTLCache

# ── 팩터 가중치 (합계 1.0) — 리서치 근거는 각 항목 주석 참조 ─────────────
W_MOMENTUM = 0.30   # 모멘텀: 3~12개월 수익률의 지속성(Jegadeesh & Titman 1993).
                    #   20/60일 수익률 + 변동성조정 모멘텀(위험 대비 추세 강도)을 함께 본다.
W_TREND = 0.25      # 추세질: ADX(Wilder 1978)가 높을수록 추세 신뢰도↑,
                    #   스윙 구조(HH/HL uptrend)가 뒷받침될 때 추세추종 승률이 높다.
W_AGG = 0.20        # 종합시그널: 다전략 앙상블 합(aggregate.total) — 서로 다른
                    #   범주 전략의 합의(ensemble)가 단일 지표보다 강건하다.
W_VOLUME = 0.10     # 수급: 거래량 급증(volRatio)은 가격 움직임의 확인 신호
                    #   (volume confirms price — Granville OBV 계열의 고전 원칙).
W_TIMING = 0.15     # 진입타이밍: RSI 30~60 구간의 눌림목 진입이 유리하고
                    #   과열(70+)은 감점. 52주 고점 -5% 이내는 단기 되돌림 위험으로 감점.


def _norm(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    """v를 [lo,hi] 구간 선형 매핑으로 0~1 정규화. None 은 그대로 None."""
    if v is None or hi <= lo:
        return None
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _avg(parts: List[Optional[float]], neutral: float = 0.5) -> float:
    """None 을 제외한 평균. 전부 None 이면 중립값(0.5)."""
    vals = [p for p in parts if p is not None]
    return sum(vals) / len(vals) if vals else neutral


def extract_factors(feats: Dict) -> Dict:
    """analyze() 결과(feats)에서 퀀트 팩터를 추출 — 캔들 재조회 없이 재사용."""
    ret = feats.get("ret") or {}
    levels = feats.get("levels") or {}
    agg = feats.get("aggregate") or {}
    adx_d = feats.get("adx")  # {'adx','plusDI','minusDI'} 또는 None
    mom20 = ret.get("20")     # 20일 수익률(%)
    mom60 = ret.get("60")     # 60일 수익률(%)
    atr_pct = feats.get("atrPct")
    # 변동성조정 모멘텀 = 모멘텀 / ATR% (0분모 가드) — 샤프류 위험조정 개념
    vol_adj = (mom20 / atr_pct) if (mom20 is not None and atr_pct) else None
    return {
        "mom20": mom20,
        "mom60": mom60,
        "volAdjMom": round(vol_adj, 2) if vol_adj is not None else None,
        "rsi": feats.get("rsi"),
        "adx": adx_d.get("adx") if isinstance(adx_d, dict) else None,
        "volumeSurge": feats.get("volRatio"),
        "pos52": levels.get("pos52"),
        "aggTotal": agg.get("total"),
    }


def quant_score(feats: Dict, factors: Optional[Dict] = None) -> float:
    """팩터 가중합 → 0~100 정규화 점수 (소수 1자리 반올림)."""
    f = factors if factors is not None else extract_factors(feats)

    # 1) 모멘텀 0.30 — 20일(-10~+20%), 60일(-20~+40%), 변동성조정(-3~+5)을 평균.
    #    구간은 KOSPI 일봉 기준 상/하위 분포를 넉넉히 덮는 경험적 범위.
    s_mom = _avg([
        _norm(f.get("mom20"), -10.0, 20.0),
        _norm(f.get("mom60"), -20.0, 40.0),
        _norm(f.get("volAdjMom"), -3.0, 5.0),
    ])

    # 2) 추세질 0.25 — ADX 10~40 정규화(25+ 이면 유의미한 추세, Wilder 기준)
    #    + 스윙 구조: uptrend=1.0 / range=0.5 / downtrend=0.0 을 절반씩 결합.
    struct = feats.get("structure")
    s_struct = {"uptrend": 1.0, "range": 0.5, "downtrend": 0.0}.get(struct, 0.5)
    s_trend = _avg([_norm(f.get("adx"), 10.0, 40.0), s_struct])

    # 3) 종합시그널 0.20 — 다전략 가중합 total 을 -5~+5 로 정규화
    #    (AGG_BUY=2.5 가 0.75, AGG_SELL=-2.5 가 0.25 에 오도록).
    s_agg = _avg([_norm(f.get("aggTotal"), -5.0, 5.0)])

    # 4) 수급 0.10 — 거래량비율 0.5~2.5 배 정규화(2배+ 급증이면 만점 근처).
    s_vol = _avg([_norm(f.get("volumeSurge"), 0.5, 2.5)])

    # 5) 진입타이밍 0.15 — RSI 30~60 눌림목 구간이 만점, 70+ 과열 감점.
    rsi = f.get("rsi")
    if rsi is None:
        s_rsi = 0.5
    elif 30.0 <= rsi <= 60.0:
        s_rsi = 1.0                                  # 눌림목/중립 — 진입 유리
    elif rsi > 60.0:
        # 60→70 선형 하락, 70+ 과열은 0.1 고정 감점
        s_rsi = 0.1 if rsi >= 70.0 else 1.0 - 0.9 * (rsi - 60.0) / 10.0
    else:
        s_rsi = 0.5                                  # 과매도(<30) — 반등/추가하락 반반
    s_timing = s_rsi
    # 52주 고점 -5% 이내(pos52 환산 시 최상단 부근)는 저항 근접 — 타이밍 감점.
    from_high = (feats.get("levels") or {}).get("fromHigh")
    pos52 = f.get("pos52")
    near_high = ((from_high is not None and from_high >= -5.0)
                 or (from_high is None and pos52 is not None and pos52 >= 95.0))
    if near_high:
        s_timing = max(0.0, s_timing - 0.4)

    score = 100.0 * (W_MOMENTUM * s_mom + W_TREND * s_trend + W_AGG * s_agg
                     + W_VOLUME * s_vol + W_TIMING * s_timing)
    return round(max(0.0, min(100.0, score)), 1)


def trade_plan(feats: Dict, stop_pct: float = 0.03) -> Dict:
    """지지/저항 기반 매매 플랜. 레벨이 없으면 키는 유지하되 값은 None(None-안전)."""
    levels = feats.get("levels") or {}
    price = feats.get("price")
    ns = levels.get("nearestSupport")
    nr = levels.get("nearestResistance")

    entry_low = ns                                    # 진입존 하단 = 최근접 지지
    # 기본 정책은 지지 바로 위 +1.5%까지를 진입존으로 본다.
    entry_high = ns * 1.015 if ns else None
    target = nr                                       # 목표 = 최근접 저항
    # 손절: 진입존 하단 -stop_pct 와 지지선 -2% 중 더 보수적인(낮은) 값
    stop = min(entry_low * (1.0 - stop_pct), ns * 0.98) if ns else None

    rr = None
    if target is not None and entry_high is not None and stop is not None:
        denom = entry_high - stop
        if denom > 0:                                 # 0분모/역전 가드
            rr = round((target - entry_high) / denom, 2)

    in_zone = bool(entry_low is not None and entry_high is not None
                   and price is not None and entry_low <= price <= entry_high)

    # 한줄 코멘트 (한국어)
    if ns is None and nr is None:
        note = "지지/저항 레벨 부족 — 플랜 산출 불가"
    elif ns is None:
        note = "아래 지지선 없음 — 진입존 산출 불가, 관망 권장"
    elif nr is None:
        note = "위 저항 없음(신고가권) — 목표가 미정, 추격 주의"
    elif in_zone:
        note = f"현재가가 지지 {ns:,.0f} 진입존 안 — R:R {rr if rr is not None else '-'}"
    else:
        note = f"지지 {ns:,.0f} 부근 눌림 대기 — 목표 {nr:,.0f}"

    return {
        "entryLow": round(entry_low, 2) if entry_low is not None else None,
        "entryHigh": round(entry_high, 2) if entry_high is not None else None,
        "target": round(target, 2) if target is not None else None,
        "stop": round(stop, 2) if stop is not None else None,
        "rr": rr,
        "inZone": in_zone,
        "note": note,
    }


def build_reasons(feats: Dict, factors: Dict, plan: Dict) -> List[str]:
    """픽 추천 이유(한국어) — 이미 계산된 팩터/플랜에서만 생성, 최대 5개.

    각 규칙은 quant_score 가중치의 리서치 근거와 동일 맥락(모멘텀 지속성,
    ADX 추세 신뢰도, 거래량 확인, RSI 눌림목, R:R 비대칭)을 문장화한 것.
    """
    reasons: List[str] = []
    mom20 = factors.get("mom20")
    if mom20 is not None:
        if mom20 >= 10.0:
            reasons.append(f"20일 +{mom20:.1f}% 상승 모멘텀")
        elif mom20 <= -10.0:
            reasons.append(f"20일 {mom20:.1f}% 조정 — 눌림목 후보")
    adx = factors.get("adx")
    if adx is not None and adx >= 25.0:                # Wilder: ADX 25+ 유의미한 추세
        reasons.append(f"ADX {adx:.0f} — 뚜렷한 추세")
    if feats.get("structure") == "uptrend":
        reasons.append("상승 구조(고점·저점 상향)")
    vs = factors.get("volumeSurge")
    if vs is not None and vs >= 1.5:
        reasons.append(f"거래량 평소 대비 {vs:.1f}배")
    rsi = factors.get("rsi")
    if rsi is not None:
        if 30.0 <= rsi <= 45.0:
            reasons.append(f"RSI {rsi:.0f} — 과열 없이 진입 여지")
        elif rsi >= 70.0:
            reasons.append("RSI 과열 주의(감점)")
    agg_total = factors.get("aggTotal")
    if agg_total is not None and agg_total >= config.AGG_BUY:
        reasons.append(f"94전략 종합 매수 우위 +{agg_total:.1f}")
    if plan.get("inZone"):
        reasons.append("현재가가 써폿 진입존 안")
    rr = plan.get("rr")
    if rr is not None and rr >= 2.0:
        reasons.append(f"손익비 1:{rr} 비대칭 유리")
    return reasons[:5]


# ── 수급 레이더 임계값 — 리서치 근거는 각 규칙 주석 참조 ─────────────
FLOW_IMB_TH = 0.3       # 호가 잔량 불균형 |(bid-ask)/(bid+ask)| ≥ 0.3 → 한쪽 우위
FLOW_OBV_TH = 0.15      # OBV 10봉 상대 기울기 ≥ +15% → 자금 유입(Granville OBV)


def flow_alert(feats: Dict) -> Optional[Dict]:
    """한 종목의 수급 이상 신호를 감지 — 이미 계산된 feats 만 사용(API 호출 없음).

    토스 API 는 옵션 데이터를 제공하지 않으므로, 옵션 플로우 대신
    거래량·호가·OBV 기반 수급 신호로 대체한다. alert 0개면 None.
    """
    vol_ratio = feats.get("volRatio")
    ret1 = (feats.get("ret") or {}).get("1")           # 1일 수익률(%)
    imb = feats.get("imbalance")                       # (bid-ask)/(bid+ask), -1~+1
    obv = feats.get("obvSlope")                        # 10봉 OBV 상대 기울기
    from_high = (feats.get("levels") or {}).get("fromHigh")  # 52주 고점 대비 %
    agg_action = (feats.get("aggregate") or {}).get("action", "HOLD")

    score = 0
    buy_pts = sell_pts = 0
    alerts: List[Dict] = []

    # ① 조용한 매집 — 가격은 잠잠한데 거래량만 급증(가장 강한 신호, +3).
    #    Wyckoff accumulation: 상승 전 조용한 흡수 국면에서 거래량 선행 급증.
    if (vol_ratio is not None and vol_ratio >= 2.0
            and ret1 is not None and abs(ret1) < 2.0):
        alerts.append({"label": "조용한 매집?",
                       "detail": f"가격 변동 {ret1:+.1f}% 뿐인데 거래량 "
                                 f"{vol_ratio:.1f}배 — 매집 가능성"})
        score += 3                                     # 방향 중립(WATCH) — 아래 합산에서 처리
    # ② 거래량 급등 동반 상승 — volume confirms price(Granville), +2 BUY.
    elif (vol_ratio is not None and vol_ratio >= 2.5
            and ret1 is not None and ret1 >= 3.0):
        alerts.append({"label": "거래량 급등 동반 상승",
                       "detail": f"하루 {ret1:+.1f}% 상승에 거래량 "
                                 f"{vol_ratio:.1f}배 동반 — 수급 확인"})
        score += 2
        buy_pts += 2
    # ③ 거래량 동반 급락 — 대량 분산(distribution) 이탈 경계, +2 SELL.
    elif (vol_ratio is not None and vol_ratio >= 2.5
            and ret1 is not None and ret1 <= -3.0):
        alerts.append({"label": "거래량 동반 급락 — 이탈 경계",
                       "detail": f"하루 {ret1:+.1f}% 하락에 거래량 "
                                 f"{vol_ratio:.1f}배 — 지지 이탈 경계"})
        score += 2
        sell_pts += 2

    # ④ 호가 불균형 — 잔량 매수/매도 우위는 단기 가격 압력의 프록시
    #    (order flow imbalance — Cont et al. 2014), ±0.3 임계.
    if imb is not None:
        if imb >= FLOW_IMB_TH:
            alerts.append({"label": "호가 매수 우위",
                           "detail": f"호가 잔량 매수측 {imb * 100:+.0f}% 우위"})
            score += 1
            buy_pts += 1
        elif imb <= -FLOW_IMB_TH:
            alerts.append({"label": "호가 매도 우위",
                           "detail": f"호가 잔량 매도측 {abs(imb) * 100:.0f}% 우위"})
            score += 1
            sell_pts += 1

    # ⑤ OBV 자금 유입 — OBV 기울기 상위(+15%↑)는 누적 순매수 유입(Granville).
    if obv is not None and obv >= FLOW_OBV_TH:
        alerts.append({"label": "OBV 자금 유입",
                       "detail": f"OBV 10일 기울기 {obv:+.2f} — 누적 자금 유입"})
        score += 1
        buy_pts += 1

    # ⑥ 신고가 도전 — 52주 고점 -3% 이내 + 거래량 실림(52-week high momentum,
    #    George & Hwang 2004: 신고가 근접 종목의 후속 수익률 우위).
    if (from_high is not None and from_high >= -3.0
            and vol_ratio is not None and vol_ratio >= 1.5):
        alerts.append({"label": "신고가 도전",
                       "detail": f"52주 고점 대비 {from_high:.1f}% — 거래량 "
                                 f"{vol_ratio:.1f}배 실린 돌파 시도"})
        score += 1
        buy_pts += 1

    if not alerts:
        return None                                    # 신호 없으면 레이더 제외

    # 의견: 신호 방향 합산 우선, 동률(조용한 매집 등 중립)이면 aggregate.action 참조
    if buy_pts > sell_pts:
        opinion = "BUY"
    elif sell_pts > buy_pts:
        opinion = "SELL"
    elif agg_action in ("BUY", "SELL"):                # WATCH → aggregate BUY 면 BUY
        opinion = agg_action
    else:
        opinion = "WATCH"

    return {
        "symbol": feats.get("symbol"),
        "name": feats.get("name"),
        "price": feats.get("price"),
        "currency": feats.get("currency", "KRW"),
        "flowScore": score,
        "opinion": opinion,
        "alerts": alerts,
    }


def _normalize_universe(universe) -> List[tuple]:
    """(symbol, name) 튜플 또는 symbol 문자열 모두 허용 (screener 와 동일 규칙)."""
    norm = []
    for item in (universe or []):
        if isinstance(item, (list, tuple)):
            sym = str(item[0]) if len(item) >= 1 else None
            name = str(item[1]) if len(item) >= 2 else ""
        else:
            sym, name = str(item), ""
        if sym:
            norm.append((sym, name))
    return norm


# 시장 화이트리스트 — server 측 검증과 동일하게 유지할 것
_VALID_MARKETS = ("kr", "us", "kosdaq", "usgrowth", "all")

# ── 단기 캐시 — 서버 /api/quant 와 오토파일럿 rescreen 이 같은 시장을 각자
#    풀스캔(150종목 = 300 API 콜, 레이트리미터 하한 ~48s)하는 중복을 제거한다. ──
_FEATS_TTL = 90.0        # 종목별 analyze() 캐시 — 일봉 기반이라 90s 내 재사용 안전
                         #   (TTL 내 신선도가 필요한 값은 현재가·호가 불균형뿐이며
                         #    스크리닝 용도는 이를 허용한다)
_SCREEN_TTL = 120.0      # (market)별 스크리닝 결과 캐시 — 서버·오토파일럿 공유
_feats_cache = TTLCache(maxsize=512)
_screen_cache = TTLCache(maxsize=16)


def clear_caches():
    _feats_cache.clear()
    _screen_cache.clear()


def _analyze_cached(client, sym: str, name: str):
    key = (client, sym, name, config.CANDLE_INTERVAL, config.CANDLE_COUNT, config.USE_ORDERBOOK)
    def build():
        feats = analyze(client, sym, name)
        if feats.get("error"):
            # Data shortages are transient; do not retain a successful feature entry.
            raise ValueError(feats["error"])
        return feats
    return copy.deepcopy(_feats_cache.get_or_create(key, _FEATS_TTL, build))


def screen(client, universe=None, top_n: int = 10, market: str = "kr", strategy="legacy", include_symbols=()) -> Dict:
    market = market if market in _VALID_MARKETS else "kr"
    top_n = max(1, min(20, int(top_n)))
    if universe is None:
        full = _screen_cache.get_or_create(
            (client, market, strategy), _SCREEN_TTL,
            lambda: _build_screen(client, market=market, strategy=strategy))
    else:
        full = _build_screen(client, universe=universe, market=market, strategy=strategy)
    result = copy.deepcopy(full)
    selected = result["picks"][:top_n]
    seen = {p["symbol"] for p in selected}
    selected.extend(p for p in result["picks"] if p["symbol"] in include_symbols and p["symbol"] not in seen)
    result["picks"] = selected
    return result


def _build_screen(client, universe=None, market: str = "kr", strategy="legacy") -> Dict:
    """유니버스 전 종목을 팩터 스크리닝해 quantScore 내림차순 top_n 픽 반환.

    market: "kr"→KOSPI_UNIVERSE, "us"→US_UNIVERSE, "kosdaq"→KOSDAQ_UNIVERSE,
    "usgrowth"→US_GROWTH_UNIVERSE, "all"→4개 전부 합침
    (화이트리스트 외 값은 "kr" 폴백). universe 명시 시 market 무시.
    각 종목은 analyze() 한 번으로 충분(캔들 재조회 금지) — error 종목은 skip.
    (토스에 없는 심볼도 이 error-skip 으로 자연 처리된다.)
    USD 종목의 currency 는 analyze() 결과에서 그대로 전달된다.
    반환 dict 에는 같은 analyze 패스의 feats 를 재사용한 수급 레이더
    "flowAlerts"(flowScore 내림차순 최대 12개)가 함께 담긴다 — 추가 API 호출 없음.
    universe 미지정 시 (market)별 결과를 _SCREEN_TTL 동안 모듈 캐시해
    서버 /api/quant 와 오토파일럿이 스캔을 공유한다(반환은 깊은 복사로 격리).
    """
    market = market if market in _VALID_MARKETS else "kr"  # 화이트리스트 폴백
    if universe is None:
        if market == "us":
            universe = config.US_UNIVERSE
        elif market == "kosdaq":
            universe = config.KOSDAQ_UNIVERSE
        elif market == "usgrowth":
            universe = config.US_GROWTH_UNIVERSE
        elif market == "all":
            universe = (list(config.KOSPI_UNIVERSE) + list(config.KOSDAQ_UNIVERSE)
                        + list(config.US_UNIVERSE) + list(config.US_GROWTH_UNIVERSE))
        else:
            universe = config.KOSPI_UNIVERSE
    norm = _normalize_universe(universe)

    picks = []
    flow_alerts = []                                  # 전체 유니버스 수급 레이더
    for sym, name in norm:
        try:
            feats = _analyze_cached(client, sym, name)
        except TossAPIError as exc:
            if exc.code != "stock-not-found":
                raise
            continue                                  # 없는 종목은 건너뛰되 인증/연결 오류는 표시
        except OSError:
            raise                                     # 네트워크/타임아웃 오류를 빈 스캔으로 숨기지 않음
        except Exception:  # noqa: BLE001 - 개별 종목 실패는 전체 중단 금지
            continue
        if not feats or feats.get("error"):
            continue                                  # 데이터 부족 등 — skip

        factors = extract_factors(feats)
        agg = feats.get("aggregate") or {}
        plan = trade_plan(feats)
        picks.append({
            "symbol": sym,
            "name": feats.get("name") or name,
            "price": feats.get("price"),
            "currency": feats.get("currency", "KRW"),
            "quantScore": quant_score(feats, factors),
            "factors": factors,
            "plan": plan,
            "action": agg.get("action", "HOLD"),
            "reasons": build_reasons(feats, factors, plan),
        })
        if strategy == "chart_confirmed":
            from .chart_execution import normalize, timing
            pick = picks[-1]
            pick["timing"] = timing(sym, normalize(feats.get("chartCandles") or []))
            if feats.get("chartInterval") != "1d":
                pick["timing"].update(eligible=False, phase="blocked", reason="차트 확인 전략은 일봉 전용")
            pick["action"] = "BUY" if pick["timing"]["eligible"] else "SELL" if pick["timing"]["exitSignal"] else "HOLD"
            pick["plan"] = pick["timing"]["plan"] or {}

        # 수급 레이더 — 같은 feats 재사용(추가 API 호출 금지), 신호 없으면 None
        fa = flow_alert(feats)
        if fa:
            if not fa.get("name"):
                fa["name"] = name
            fa["_volumeSurge"] = factors.get("volumeSurge") or 0.0  # 동점 정렬용
            flow_alerts.append(fa)

    picks.sort(key=lambda p: p["quantScore"], reverse=True)
    if strategy == "chart_confirmed":
        picks.sort(key=lambda p: bool(p["timing"]["eligible"]), reverse=True)
    # flowScore 내림차순, 동점이면 volumeSurge 큰 순 — 상위 12개만
    flow_alerts.sort(key=lambda a: (a["flowScore"], a["_volumeSurge"]), reverse=True)
    flow_alerts = flow_alerts[:12]
    for fa in flow_alerts:
        fa.pop("_volumeSurge", None)                  # 내부 정렬 키 제거
    result = {
        "generatedAt": time.strftime("%H:%M:%S"),
        "market": market,
        "universeSize": len(norm),
        "picks": picks,                               # 캐시엔 미절단 전체 저장
        "flowAlerts": flow_alerts,
    }
    return result
