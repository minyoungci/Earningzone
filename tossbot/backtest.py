"""백테스팅 워크포워드 시뮬레이터 — 표준 라이브러리만 사용.

라이브 분석(analysis.analyze)과 '동일한 집계 신호'(build_features→run_all→aggregate)를
재사용해 과거 캔들을 한 봉씩 전진하며 롱-온리·현금계좌·전액 진입 매매를 시뮬레이션하고
성과지표를 산출한다.

⚠️ 룩어헤드(look-ahead) 금지: 봉 i 의 의사결정은 '봉 i 진입 전까지 알 수 있는 정보'
(candles[:i])로만 계산하고, 체결은 봉 i 의 시가(open[i])에서 한다.

⚠️ 산출 지표는 교육용 휴리스틱 백테스트이며 투자 권유가 아닙니다. 과거 성과가
미래 수익을 보장하지 않습니다.

compare(): 전략 카테고리별 성과 비교. 봉당 build_features+run_all 은 '한 번만' 계산하고,
7개 변형(all + 6개 카테고리)이 같은 시그널 스트림에서 각자 필터·집계·포지션 상태를
독립적으로 시뮬레이션한다(1패스 워크포워드).
"""
from __future__ import annotations

import math

from . import config
from .analysis import aggregate
from .client import TossAPIError
from .features import build_features
from .strategies import REGISTRY, for_interval, run_all

# ── 수수료/세금: config 에 있으면 사용, 없으면 sim.py 와 동일 기본값 ──────────────
FEE_RATE = getattr(config, "FEE_RATE", 0.00015)   # 매매 수수료 0.015%
TAX_RATE = getattr(config, "TAX_RATE", 0.0018)    # 매도 거래세 0.18%

WARMUP = 60       # 워밍업 봉 수(지표 안정화 + build_features 의 최소 30봉 충족)
_TRADING_DAYS = 252  # 연율화(샤프) 기준 거래일(일봉)
# 캔들 간격별 연율화 계수(샤프). 일봉=252거래일, 주봉=52, 월봉=12, 시간봉=252*6.5시간.
_ANNUALIZE = {"1d": 252, "1w": 52, "1mo": 12, "1M": 12,
              "1h": 1638, "60m": 1638, "30m": 3276, "15m": 6552,
              "5m": 19656, "1m": 98280}


def _f(x):
    """안전 float 변환(None/문자열 캔들 필드 대응)."""
    try:
        value = float(x)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _r2(x):
    """소수 2자리 반올림(None/비수치는 그대로)."""
    if x is None or isinstance(x, bool):
        return x
    if isinstance(x, (int, float)) and math.isfinite(x):
        return round(float(x), 2)
    return x


# ── 카테고리 필터용 임계 스케일링 ─────────────────────────────────

def _scaled_thresholds(categories, registry=None):
    """카테고리 부분집합용 BUY/SELL 임계값 산출.

    근거: config.AGG_BUY / AGG_SELL 은 '전체 전략(len(REGISTRY)개)'이 만드는
    가중합 분포를 기준으로 보정된 값이다. 일부 카테고리만 사용하면 달성 가능한
    가중합의 상한이 대략 참여 전략 수에 비례해 줄어들므로,
    share = (선택 카테고리 전략 수 / 전체 전략 수) 비율로 임계값을 축소한다.
    다만 임계가 0 근처까지 내려가면 약한 신호 1~2개로도 매매가 발생하므로
    절대값 0.8 을 바닥(floor)으로 둔다.
    """
    registry = REGISTRY if registry is None else registry
    total = len(registry)
    selected = sum(1 for fn in registry
                   if getattr(fn, "s_category", None) in categories)
    share = (selected / total) if total else 0.0
    buy_th = max(0.8, config.AGG_BUY * share)
    sell_th = min(-0.8, config.AGG_SELL * share)
    return buy_th, sell_th


def _make_decider(categories, registry=None):
    """카테고리 필터 + 스케일 임계값으로 시그널 리스트→액션을 결정하는 함수 생성.

    categories 가 None 이면 라이브 분석과 동일한 aggregate() 그대로 사용
    (기존 단일 backtest 동작 불변).
    """
    if categories is None:
        return lambda signals: aggregate(signals)["action"]

    cats = set(categories)
    buy_th, sell_th = _scaled_thresholds(cats, registry)
    weights = config.CATEGORY_WEIGHTS

    def decide(signals):
        # aggregate() 와 동일한 가중합 계산을 선택 카테고리 시그널로만 수행.
        total = 0.0
        for s in signals:
            if s.category in cats:
                total += s.score * weights.get(s.category, 1.0)
        if total >= buy_th:
            return "BUY"
        if total <= sell_th:
            return "SELL"
        return "HOLD"

    return decide


# ── 데이터 로드/파싱(단일·비교 공용) ───────────────────────────────

def _load_data(client, symbol, name, interval, count):
    """캔들 조회 + 파싱. 성공 시 (data, None), 실패 시 (None, error_dict).

    error_dict 는 기존 backtest 의 에러 계약({'symbol','name','error','bars'})과 동일.
    """
    # 토스 캔들 상한(200)을 넘으면 API 가 에러를 반환하므로 방어적으로 캡한다.
    count = max(WARMUP + 10, min(int(count), 200))
    # 과거 캔들 확보(TossAPIError 는 analysis.py 와 동일 계약으로 변환).
    try:
        res = client.candles(symbol, interval=interval, count=count)
    except TossAPIError as e:
        if e.code != "stock-not-found":
            raise
        return None, {"symbol": symbol, "name": name,
                      "error": "종목을 찾을 수 없습니다", "bars": 0}

    newest_first = res.get("candles", []) if isinstance(res, dict) else []
    # 시간 오름차순(과거→현재)으로 정규화. 각 봉을 한 번만 파싱해 재사용한다.
    asc = list(reversed(newest_first or []))

    currency = "KRW"
    # OHLC 배열과 build_features 용 원본 캔들(valid_raw)을 같은 루프에서 한 번에 구성.
    # 파싱 실패 봉은 양쪽에서 동일하게 제외해 closes 와 valid_raw 의 인덱스를 정합시킨다.
    opens, closes, times, valid_raw = [], [], [], []
    for c in asc:
        o, h, l, cl = (_f(c.get("openPrice")), _f(c.get("highPrice")),
                       _f(c.get("lowPrice")), _f(c.get("closePrice")))
        if None in (o, h, l, cl) or min(o, h, l, cl) <= 0 or h < max(o, cl) or l > min(o, cl):
            continue
        opens.append(o); closes.append(cl)
        valid_raw.append(c)
        currency = c.get("currency", currency)
        # time 은 candles 엔드포인트와 동일 형식(일봉=YYYY-MM-DD 문자열).
        ts = str(c.get("timestamp") or c.get("date") or "")
        times.append(ts[:10] if interval == "1d" and len(ts) >= 10 else ts)

    n = len(closes)
    if n < WARMUP + 10:
        return None, {"symbol": symbol, "name": name,
                      "error": "데이터 부족", "bars": n}

    return {"opens": opens, "closes": closes, "times": times,
            "valid_raw": valid_raw, "currency": currency, "n": n, "interval": interval}, None


# ── 1패스 멀티 변형 시뮬레이션 엔진 ────────────────────────────────

def _simulate(data, deciders, symbol, name, stop_pct, capital):
    """워크포워드 1패스로 여러 변형(deciders={key: decide_fn})을 동시 시뮬레이션.

    성능 핵심: 봉당 build_features + run_all 은 '한 번만' 계산하고, 각 변형은
    같은 시그널에서 자기 결정 함수로 액션을 얻어 포지션 상태를 독립 갱신한다.
    반환: {key: 상태 dict(trades/equity_curve/daily_returns/held_bars/final cash)}.
    """
    opens, closes, times = data["opens"], data["closes"], data["times"]
    valid_raw, n = data["valid_raw"], data["n"]
    fee = FEE_RATE
    tax = TAX_RATE
    base_close = closes[WARMUP]  # buyHold 기준가(동일 구간 매수후보유)
    registry = for_interval(data.get("interval", "1d"))

    # ── 변형별 포지션/상태 ─────────────────────────────────────
    states = {}
    for key in deciders:
        states[key] = {
            "cash": float(capital),
            "qty": 0.0,               # 보유 수량(분할 없이 전액 진입이므로 소수 허용)
            "entry_price": None,      # 진입가(open 체결가)
            "entry_time": None,
            "entry_idx": None,
            "stop_support": None,     # 진입 시 보관한 지지선(하향이탈 손절 기준)
            "trades": [],
            "equity_curve": [],
            "daily_returns": [],      # 에쿼티 일일수익률(샤프용)
            "prev_equity": None,
            "held_bars": 0,           # 보유(노출) 봉 수 — exposurePct 산출
        }

    def _exit(st, i, reason):
        """현재 포지션을 open/close 가격으로 청산하고 trade 기록을 남긴다."""
        # 신호 청산은 다음 봉 시가(open[i]), 손절류는 당일 종가(close[i])에서 체결.
        px = opens[i] if reason == "signal" else closes[i]
        proceeds = st["qty"] * px
        net = proceeds - proceeds * (fee + tax)   # 매도: 수수료 + 거래세 차감
        cost = st["qty"] * st["entry_price"] + st["qty"] * st["entry_price"] * fee
        pnl = net - cost
        ret_pct = (pnl / cost * 100.0) if cost else 0.0
        st["trades"].append({
            "entryTime": st["entry_time"], "entryPrice": _r2(st["entry_price"]),
            "exitTime": times[i], "exitPrice": _r2(px),
            "qty": _r2(st["qty"]), "retPct": _r2(ret_pct), "pnl": _r2(pnl),
            "bars": i - st["entry_idx"], "exitReason": reason,
        })
        st["cash"] += net
        st["qty"] = 0.0
        st["entry_price"] = st["entry_time"] = st["entry_idx"] = None
        st["stop_support"] = None

    # ── 워밍업 이후 한 봉씩 전진(피처/시그널은 봉당 1회만 계산) ────
    for i in range(WARMUP, n):
        # (a) 봉 i 진입 전 정보(candles[:i])로 집계 신호 계산.
        #     build_features 는 뉴스트-퍼스트를 받으므로 valid_raw[:i] 를 역순 전달.
        hist_newest_first = list(reversed(valid_raw[:i]))
        feats = build_features(symbol, name, hist_newest_first)
        signals = None
        if not feats.get("error"):
            signals = run_all(feats, registry=registry)

        for key, decide in deciders.items():
            st = states[key]
            action = decide(signals) if signals is not None else "HOLD"

            # (b) 의사결정 → 체결.
            if st["qty"] == 0.0:
                # 플랫 + BUY → 봉 i 시가에 전액 매수(수수료 차감).
                if action == "BUY":
                    px = opens[i]
                    if px > 0:
                        # 전액 진입: 수수료까지 포함한 총비용이 cash 를 넘지 않도록 수량 산정.
                        st["qty"] = st["cash"] / (px * (1.0 + fee))
                        spent = st["qty"] * px * (1.0 + fee)
                        st["cash"] -= spent
                        st["entry_price"] = px
                        st["entry_time"] = times[i]
                        st["entry_idx"] = i
                        # 진입 시점 지지선(직전까지의 정보)을 손절 기준으로 보관.
                        sr = feats.get("levels") if not feats.get("error") else None
                        st["stop_support"] = sr.get("nearestSupport") if sr else None
            else:
                # 보유 중 — 청산 조건 평가(우선순위: 손절류 먼저, 그다음 신호).
                stop_hit = closes[i] < st["entry_price"] * (1.0 - stop_pct)
                support_break = (st["stop_support"] is not None
                                 and closes[i] < st["stop_support"])
                if stop_hit:
                    _exit(st, i, "stop")
                elif support_break:
                    _exit(st, i, "support_break")
                elif action == "SELL":
                    _exit(st, i, "signal")

            # (c) 매 봉 에쿼티(시가평가) 기록.
            if st["qty"] > 0.0:
                equity = st["cash"] + closes[i] * st["qty"]
                st["held_bars"] += 1
            else:
                equity = st["cash"]
            buy_hold = capital * closes[i] / base_close if base_close else capital
            st["equity_curve"].append({"time": times[i],
                                       "equity": _r2(equity),
                                       "buyHold": _r2(buy_hold)})

            if st["prev_equity"] is not None and st["prev_equity"] > 0:
                st["daily_returns"].append(equity / st["prev_equity"] - 1.0)
            st["prev_equity"] = equity

    # ── 미청산 포지션은 마지막 봉 종가로 강제 청산(지표 정합성) ──────
    for st in states.values():
        if st["qty"] > 0.0:
            i = n - 1
            px = closes[i]
            proceeds = st["qty"] * px
            net = proceeds - proceeds * (fee + tax)
            cost = st["qty"] * st["entry_price"] + st["qty"] * st["entry_price"] * fee
            pnl = net - cost
            ret_pct = (pnl / cost * 100.0) if cost else 0.0
            st["trades"].append({
                "entryTime": st["entry_time"], "entryPrice": _r2(st["entry_price"]),
                "exitTime": times[i], "exitPrice": _r2(px),
                "qty": _r2(st["qty"]), "retPct": _r2(ret_pct), "pnl": _r2(pnl),
                "bars": i - st["entry_idx"], "exitReason": "eod",
            })
            st["cash"] += net
            st["qty"] = 0.0
            # 마지막 에쿼티 포인트를 청산 후 현금으로 갱신.
            if st["equity_curve"]:
                st["equity_curve"][-1]["equity"] = _r2(st["cash"])

    return states


def _compute_metrics(st, data, interval, capital):
    """변형 상태 dict → 성과지표(기존 backtest metrics 와 동일 공식)."""
    closes, n = data["closes"], data["n"]
    trades = st["trades"]
    final_equity = st["cash"]  # 종료 시 전액 현금(미청산분 강제청산 후)
    total_bars = n - WARMUP
    base_close = closes[WARMUP]

    total_return_pct = (final_equity / capital - 1.0) * 100.0 if capital else 0.0
    bh_final = capital * closes[n - 1] / base_close if base_close else capital
    buy_hold_return_pct = (bh_final / capital - 1.0) * 100.0 if capital else 0.0

    num_trades = len(trades)
    wins = [t for t in trades if (t["pnl"] or 0) > 0]
    losses = [t for t in trades if (t["pnl"] or 0) < 0]
    winning = len(wins)
    losing = len(losses)
    win_rate = (winning / num_trades * 100.0) if num_trades else 0.0

    # 최대 낙폭(peak-to-trough) — 에쿼티 곡선 기준.
    peak = -float("inf")
    max_dd = 0.0
    for pt in st["equity_curve"]:
        eq = pt["equity"]
        if eq is None:
            continue
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    # 샤프(봉당수익률 평균/표준편차 * sqrt(연율화계수)). 간격별 계수 적용. 표준편차 0이면 0.
    daily_returns = st["daily_returns"]
    sharpe = 0.0
    if len(daily_returns) > 1:
        mean = sum(daily_returns) / len(daily_returns)
        var = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std = math.sqrt(var)
        ann = _ANNUALIZE.get(interval, _TRADING_DAYS)
        sharpe = (mean / std * math.sqrt(ann)) if std > 0 else 0.0

    # 손익비(이익합 / 손실합 abs). 손실 0이면 None.
    gross_profit = sum((t["pnl"] or 0) for t in wins)
    gross_loss = abs(sum((t["pnl"] or 0) for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    avg_win_pct = (sum((t["retPct"] or 0) for t in wins) / winning) if winning else 0.0
    avg_loss_pct = (sum((t["retPct"] or 0) for t in losses) / losing) if losing else 0.0
    avg_hold_bars = (sum(t["bars"] for t in trades) / num_trades) if num_trades else 0.0
    exposure_pct = (st["held_bars"] / total_bars * 100.0) if total_bars else 0.0

    return {
        "totalReturnPct": _r2(total_return_pct),
        "buyHoldReturnPct": _r2(buy_hold_return_pct),
        "finalEquity": _r2(final_equity),
        "initialCapital": _r2(float(capital)),
        "numTrades": num_trades,
        "winRate": _r2(win_rate),
        "winningTrades": winning,
        "losingTrades": losing,
        "maxDrawdownPct": _r2(max_dd),
        "sharpe": _r2(sharpe),
        "profitFactor": _r2(profit_factor) if profit_factor is not None else None,
        "avgWinPct": _r2(avg_win_pct),
        "avgLossPct": _r2(avg_loss_pct),
        "avgHoldBars": _r2(avg_hold_bars),
        "exposurePct": _r2(exposure_pct),
    }


def backtest(client, symbol, name="", interval="1d", count=200,
             stop_pct=0.08, capital=1_000_000, categories=None) -> dict:
    """워크포워드 백테스트 실행.

    Parameters
    ----------
    client     : TossClient 호환(candles 메서드 보유)
    symbol     : 종목 코드
    name       : 종목명(표시용)
    interval   : 캔들 간격(기본 '1d')
    count      : 조회 캔들 수(기본 200). 토스 API 가 캔들을 최대 200봉까지만 제공하므로 200 으로 캡한다.
    stop_pct   : 손절 비율(예: 0.08 = -8%)
    capital    : 초기 자본(종목 통화 기준)
    categories : 전략 카테고리 필터(예: ["trend"]). None 이면 전체 전략(기존 동작 불변).
                 지정 시 run_all 시그널을 s.category in categories 로 필터하고,
                 임계값은 전략 수 비율로 스케일한다(_scaled_thresholds 참고).

    Returns
    -------
    dict : [백테스트 출력 계약] 형태. 데이터 부족/무효 종목 시 {'error', 'bars'} 포함.
    """
    data, err = _load_data(client, symbol, name, interval, count)
    if err:
        return err

    key = "all" if categories is None else "filtered"
    states = _simulate(data, {key: _make_decider(categories, for_interval(interval))},
                       symbol, name, stop_pct, capital)
    st = states[key]
    metrics = _compute_metrics(st, data, interval, capital)

    params = {
        "stopPct": stop_pct, "capital": _r2(float(capital)),
        "feeRate": FEE_RATE, "taxRate": TAX_RATE, "warmup": WARMUP,
    }
    # 기존 단일 backtest 출력 계약 불변: categories 필터를 쓸 때만 params 에 노출.
    if categories is not None:
        params["categories"] = sorted(set(categories))

    return {
        "symbol": symbol, "name": name, "currency": data["currency"],
        "interval": interval, "bars": data["n"],
        "params": params,
        "metrics": metrics,
        "trades": st["trades"],
        "equityCurve": st["equity_curve"],
    }


# compare() 결과 M 에 담는 지표 키(공유 계약).
_COMPARE_KEYS = ("totalReturnPct", "buyHoldReturnPct", "numTrades", "winRate",
                 "maxDrawdownPct", "sharpe", "profitFactor", "exposurePct")


def compare(client, symbol, name="", interval="1d", count=200,
            stop_pct=0.08, capital=10_000_000) -> dict:
    """전략 카테고리별 백테스트 비교(all + config.CATEGORY_WEIGHTS 의 6개 카테고리).

    성능: 워크포워드 1패스로 봉당 build_features+run_all 을 한 번만 계산하고,
    7개 변형이 같은 시그널에서 각자 필터·집계·포지션 상태를 독립 시뮬레이션한다.

    Returns
    -------
    dict : {"symbol","name","currency","bars","params",
            "results": {"all": M, "<category>": M, ...}, "best": key}
           M = totalReturnPct/buyHoldReturnPct/numTrades/winRate/
               maxDrawdownPct/sharpe/profitFactor/exposurePct
           데이터 부족/무효 종목은 기존과 동일 {'error',...} 계약.
    """
    data, err = _load_data(client, symbol, name, interval, count)
    if err:
        return err

    # 카테고리 목록은 config.CATEGORY_WEIGHTS 키에서(전략 레지스트리와 동일 분류).
    category_keys = list(config.CATEGORY_WEIGHTS.keys())
    deciders = {"all": _make_decider(None)}
    for cat in category_keys:
        deciders[cat] = _make_decider([cat], for_interval(interval))

    states = _simulate(data, deciders, symbol, name, stop_pct, capital)

    results = {}
    for key in deciders:
        m = _compute_metrics(states[key], data, interval, capital)
        results[key] = {k: m[k] for k in _COMPARE_KEYS}

    # best: 총수익률 최고 변형(동률이면 선언 순서 우선).
    def _ret(k):
        v = results[k]["totalReturnPct"]
        return v if isinstance(v, (int, float)) else float("-inf")

    best = max(results, key=_ret)

    return {
        "symbol": symbol, "name": name, "currency": data["currency"],
        "bars": data["n"],
        "params": {
            "interval": interval, "stopPct": stop_pct,
            "capital": _r2(float(capital)),
            "feeRate": FEE_RATE, "taxRate": TAX_RATE, "warmup": WARMUP,
        },
        "results": results,
        "best": best,
    }
