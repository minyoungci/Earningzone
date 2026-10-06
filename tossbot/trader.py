"""트레이더 — 분석 결과를 받아 (DRY_RUN 게이트된) 주문을 집행하고 포트폴리오를 갱신.

step(analyses): 보유종목은 (점수<=EXIT_SCORE 또는 risk.exit_signal) 시 SELL,
                미보유는 aggregate.action=="BUY" and total>=ENTRY_SCORE and can_open 시 BUY.
run_paper(): analyze 로 워치리스트를 반복 분석하며 매매 루프(킬스위치 발동 시 중단).

⚠️ 실제 주문은 client.place_order 의 DRY_RUN 게이트에 위임합니다. 임의 실주문 강제 금지.
교육용 모의이며 투자 권유가 아닙니다.
"""
from __future__ import annotations

import math
import time
from datetime import datetime

from . import brokers, config
from .portfolio import Portfolio
from .risk import RiskManager


def _now():
    return datetime.now().strftime("%H:%M:%S")


def _f(v, default=None):
    try:
        if v is None:
            return default
        value = float(v)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _log(msg):
    print(f"[trader {_now()}] {msg}")


class Trader:
    def __init__(self, client, portfolio=None, risk=None, order_size_krw=None,
                 broker=None):
        self.client = client
        # 주문 실행 브로커 — 미지정 시 활성 브로커(.broker_state.json)를 따른다.
        # 분석/시세는 계속 토스 client 로, '주문'만 브로커를 통해 나간다.
        self.broker = broker or brokers.get(client)
        self.portfolio = portfolio or Portfolio()
        self.risk = risk or RiskManager()
        self._halted = False
        self.order_size_krw = (order_size_krw
                               if order_size_krw is not None
                               else config.ORDER_SIZE_KRW)

    # ── 가격 추출 ──────────────────────────────────────────
    @staticmethod
    def _price_of(a):
        if not isinstance(a, dict):
            return None
        p = _f(a.get("price"), None)
        if p is None or p <= 0:
            p = _f(a.get("lastClose"), None)
        return p if (p and p > 0) else None

    # ── 주문 집행(공통) ───────────────────────────────────
    def _paper_order(self, symbol, side, qty, price):
        if self._halted:
            return None
        # 이 트레이더의 원장은 모의 원장이다. 실거래 체결 동기화 없이 사용하지 않는다.
        dry_run = getattr(self.broker, "dry_run", config.DRY_RUN)
        if dry_run is False:
            self._halted = True
            _log("모의 트레이더는 DRY_RUN 모드에서만 실행할 수 있습니다.")
            return None
        try:
            res = self.broker.place_order(symbol, side, qty, price=price)
        except Exception as e:
            _log(f"{side} 실패 {symbol} [{self.broker.name}]: {e}")
            return None
        if not isinstance(res, dict) or res.get("dryRun") is not True:
            self._halted = True
            _log("모의 체결 응답이 아닙니다 — 원장 반영과 추가 주문을 중단합니다.")
            return None
        return res

    def _execute_buy(self, symbol, name, price, qty):
        if qty <= 0 or price <= 0:
            return None
        res = self._paper_order(symbol, "BUY", qty, price)
        if res is None:
            return None
        self.portfolio.open(symbol, qty, price, name=name)
        tag = "DRY" if isinstance(res, dict) and res.get("dryRun") else "LIVE"
        _log(f"BUY  [{tag}·{self.broker.name}] {symbol} {name}  {qty}주 @ {price:,.0f}  "
             f"(≈{qty * price:,.0f}KRW)")
        return res

    def _execute_sell(self, symbol, name, price, qty, reason):
        if qty <= 0 or price <= 0:
            return None
        res = self._paper_order(symbol, "SELL", qty, price)
        if res is None:
            return None
        realized = self.portfolio.reduce(symbol, qty, price)
        tag = "DRY" if isinstance(res, dict) and res.get("dryRun") else "LIVE"
        rstr = f"  실현 {realized:+,.0f}KRW" if realized is not None else ""
        _log(f"SELL [{tag}·{self.broker.name}] {symbol} {name}  {qty}주 @ {price:,.0f}  "
             f"({reason}){rstr}")
        return res

    # ── 한 사이클 ──────────────────────────────────────────
    def step(self, analyses):
        """analyses: analyze() 결과(Features+aggregate) 리스트. 반환: 실행 액션 리스트."""
        actions = []
        if not analyses or self._halted:
            return actions

        # 현재가 맵(킬스위치/평가용)
        prices = {}
        for a in analyses:
            if isinstance(a, dict) and not a.get("error"):
                p = self._price_of(a)
                if p is not None:
                    prices[a.get("symbol")] = p

        # 킬스위치: 당일 손실 한도 초과 시 신규/매도 모두 중단(보호적으로 매수만 차단,
        # 청산은 허용하는 게 안전하나 명세상 '중단'이므로 신규진입을 막고 호출자에 신호).
        kill = self.risk.daily_loss_kill(self.portfolio, prices)
        if kill:
            _log("⚠️ 손실 한도 초과 또는 평가 실패 — 신규 진입 중단.")

        for a in analyses:
            if not isinstance(a, dict) or a.get("error"):
                continue
            symbol = a.get("symbol")
            if not symbol:
                continue
            name = a.get("name", "")
            agg = a.get("aggregate") or {}
            total = _f(agg.get("total"), 0.0) or 0.0
            action = agg.get("action", "HOLD")
            price = self._price_of(a)
            if price is None:
                continue

            held = self.portfolio.has(symbol)

            # ── 보유종목: 청산 검사 ──
            if held:
                pos = self.portfolio.get(symbol)
                exit_reason = self.risk.exit_signal(pos, price)
                low_score = total <= config.EXIT_SCORE
                if exit_reason or low_score:
                    reason = exit_reason or f"점수 {total:+.1f}≤{config.EXIT_SCORE:+.1f}"
                    qty = pos.qty
                    res = self._execute_sell(symbol, name, price, qty, reason)
                    if res is not None:
                        actions.append({"side": "SELL", "symbol": symbol,
                                        "qty": qty, "price": price, "reason": reason})
                continue

            # ── 미보유: 신규 진입 검사 ──
            if kill:
                continue
            if action != "BUY" or total < config.ENTRY_SCORE:
                continue
            qty = int(math.floor(self.order_size_krw / price)) if price > 0 else 0
            if qty <= 0:
                continue
            order_krw = qty * price
            ok, why = self.risk.can_open(symbol, order_krw, self.portfolio)
            if not ok:
                _log(f"진입보류 {symbol} {name}: {why}")
                continue
            res = self._execute_buy(symbol, name, price, qty)
            if res is not None:
                actions.append({"side": "BUY", "symbol": symbol,
                                "qty": qty, "price": price,
                                "reason": f"점수 {total:+.1f}≥{config.ENTRY_SCORE:+.1f}"})

        # 사이클 요약
        if actions or kill:
            s = self.portfolio.summary(prices)
            _log(f"요약 │ 보유 {s['positions']}종목  실현 {s['realizedPnl']:+,.0f}  "
                 f"미실현 {s['unrealized']:+,.0f}  당일 {s['dailyPnl']:+,.0f}KRW")
        return actions


def run_paper(client=None, watchlist=None, interval=None, loop=True):
    """페이퍼 트레이딩 루프. analyze 사용. 킬스위치 발동 시 루프 중단.

    client 미지정 시 TossClient() 생성(자격증명 필요). DRY_RUN 게이트가 실주문을 막습니다.
    """
    from .client import TossClient, TossAPIError
    from .analysis import analyze

    client = client or TossClient()
    if not config.DRY_RUN or not client.dry_run:
        raise RuntimeError("--paper는 DRY_RUN=1에서만 실행합니다. 실거래 자동 체결 동기화는 지원하지 않습니다.")
    wl = watchlist or config.WATCHLIST
    interval = interval or config.POLL_INTERVAL_SEC
    syms = [s for s, _ in wl]
    names = {s: n for s, n in wl}

    portfolio = Portfolio()
    risk = RiskManager()
    trader = Trader(client, portfolio, risk)

    _log(f"페이퍼 트레이딩 시작 — {len(syms)}종목, {interval}초 간격, "
         f"DRY_RUN={'ON' if client.dry_run else 'OFF(실주문!)'} (Ctrl+C 종료)")

    def _one_cycle():
        # 현재가 일괄 조회(실패해도 analyze 내부에서 캔들 종가 사용)
        prices = {}
        try:
            for p in client.prices(syms):
                prices[p["symbol"]] = p.get("lastPrice")
        except TossAPIError:
            prices = {}
        analyses = []
        for s in syms:
            try:
                a = analyze(client, s, names.get(s, ""), last_price=prices.get(s))
            except TossAPIError as e:
                a = {"symbol": s, "name": names.get(s, ""), "error": e.code}
            except Exception as e:  # 방어적: 분석 실패 종목은 건너뜀
                a = {"symbol": s, "name": names.get(s, ""), "error": str(e)}
            analyses.append(a)
        trader.step(analyses)
        # 사후 킬스위치 점검(루프 중단 여부)
        pmap = {s: prices.get(s) for s in syms if prices.get(s) is not None}
        return trader._halted or risk.daily_loss_kill(portfolio, pmap)

    try:
        killed = _one_cycle()
        if killed:
            _log("킬스위치 발동 상태 — 루프를 시작하지 않고 종료합니다.")
            return portfolio
        if not loop:
            return portfolio
        while True:
            time.sleep(interval)
            if _one_cycle():
                _log("킬스위치 발동 — 루프를 중단합니다.")
                break
    except KeyboardInterrupt:
        _log("종료되었습니다.")
    return portfolio
