"""분석 오케스트레이션 — Features 빌드 → 전 전략 실행 → 가중 집계.

⚠️ 산출되는 점수·시그널은 교육용 휴리스틱이며 투자 권유가 아닙니다.
"""
from __future__ import annotations

from . import config
from .client import TossAPIError
from .features import build_features
from .strategies import for_interval, run_all


def aggregate(signals):
    total = buy_w = sell_w = 0.0
    n_buy = n_sell = 0
    for s in signals:
        w = config.CATEGORY_WEIGHTS.get(s.category, 1.0)
        total += s.score * w
        if s.action == "BUY":
            n_buy += 1; buy_w += s.score * w
        elif s.action == "SELL":
            n_sell += 1; sell_w += -s.score * w
    if getattr(signals, "errors", None):
        action = "HOLD"
    elif total >= config.AGG_BUY:
        action = "BUY"
    elif total <= config.AGG_SELL:
        action = "SELL"
    else:
        action = "HOLD"
    return {"total": total, "buyW": buy_w, "sellW": sell_w,
            "action": action, "nBuy": n_buy, "nSell": n_sell}


def analyze(client, symbol, name="", interval=None, count=None, last_price=None):
    interval = interval or config.CANDLE_INTERVAL
    count = count or config.CANDLE_COUNT
    # 존재하지 않는 종목 등은 candles 조회에서 TossAPIError 가 발생한다.
    # 그대로 전파하면 server 레벨 500 이 되므로 '데이터 부족' 과 동일한 error dict 로 반환한다.
    try:
        res = client.candles(symbol, interval=interval, count=count)
    except TossAPIError as e:
        if e.code != "stock-not-found":
            raise
        return {"symbol": symbol, "name": name, "error": "종목을 찾을 수 없습니다", "bars": 0}
    candles = res.get("candles", []) if isinstance(res, dict) else []
    ob = None
    if config.USE_ORDERBOOK:
        try:
            ob = client.orderbook(symbol)
        except Exception:
            ob = None
    feats = build_features(symbol, name, candles, last_price=last_price, orderbook=ob)
    if feats.get("error"):
        return {"symbol": symbol, "name": name, "error": feats["error"], "bars": feats.get("bars", 0)}
    signals = run_all(feats, registry=for_interval(interval))
    feats["signals"] = signals
    feats["aggregate"] = aggregate(signals)
    # Reuse this fetch for the optional daily execution policy; timestamps are essential.
    feats["chartCandles"] = candles
    feats["chartInterval"] = interval
    return feats
