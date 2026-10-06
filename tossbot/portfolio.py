"""페이퍼 트레이딩 포트폴리오 — JSON 영속, 포지션/손익 관리.

표준 라이브러리만 사용. config.PAPER_STATE_FILE 에 상태를 저장합니다.
- Position: 보유 종목 1개(symbol, qty, avgPrice, openedAt[+트레일링 최고가]).
- Portfolio: 포지션 집합 + 실현손익 누적 + 당일 시작자산 기록.
  open/add/reduce/close, mark_to_market(prices)->미실현손익, daily_pnl().

⚠️ 산출 수치는 교육용 모의이며 투자 권유가 아닙니다.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime

from . import config


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _f(v, default=0.0):
    """안전 float 변환."""
    try:
        if v is None:
            return default
        value = float(v)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avgPrice: float = 0.0
    openedAt: str = ""
    name: str = ""
    peakPrice: float = 0.0   # 트레일링 스탑용 보유 중 최고가

    def cost(self) -> float:
        return self.qty * self.avgPrice

    def market_value(self, price) -> float:
        p = _f(price, self.avgPrice)
        return self.qty * p

    def unrealized(self, price) -> float:
        p = _f(price, self.avgPrice)
        return (p - self.avgPrice) * self.qty

    def unrealized_pct(self, price):
        if self.avgPrice <= 0:
            return None
        p = _f(price, self.avgPrice)
        return (p / self.avgPrice - 1.0) * 100.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d) -> "Position":
        if not isinstance(d, dict):
            return cls(symbol="")
        return cls(
            symbol=str(d.get("symbol", "")),
            qty=_f(d.get("qty"), 0.0),
            avgPrice=_f(d.get("avgPrice"), 0.0),
            openedAt=str(d.get("openedAt", "")),
            name=str(d.get("name", "")),
            peakPrice=_f(d.get("peakPrice"), 0.0),
        )


class Portfolio:
    """JSON 영속 모의 포트폴리오."""

    def __init__(self, state_file=None, starting_cash=None):
        self.state_file = state_file or config.PAPER_STATE_FILE
        self._positions = {}          # symbol -> Position
        self.realizedPnl = 0.0        # 실현손익 누적(전체 기간)
        self.startCash = _f(starting_cash, 0.0)
        # 일중손익 기준: 당일 시작 시점의 (실현손익누적 + 0). 미실현은 mark 시 합산.
        self.dayDate = _today_str()
        self.dayStartRealized = 0.0   # 당일 시작 시점의 누적 실현손익
        self.trades = []              # 체결 로그(간이)
        self.load()

    # ── 영속 ───────────────────────────────────────────────
    def load(self):
        try:
            if not os.path.exists(self.state_file):
                return
            with open(self.state_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.realizedPnl = _f(data.get("realizedPnl"), 0.0)
        self.startCash = _f(data.get("startCash"), self.startCash)
        self.dayDate = str(data.get("dayDate", self.dayDate))
        self.dayStartRealized = _f(data.get("dayStartRealized"), 0.0)
        poss = data.get("positions", [])
        if isinstance(poss, list):
            for pd in poss:
                pos = Position.from_dict(pd)
                if pos.symbol and pos.qty > 0:
                    self._positions[pos.symbol] = pos
        tr = data.get("trades", [])
        if isinstance(tr, list):
            self.trades = tr[-500:]
        # 날짜가 바뀌었으면 일중 기준 갱신
        self._roll_day()

    def save(self):
        data = {
            "realizedPnl": self.realizedPnl,
            "startCash": self.startCash,
            "dayDate": self.dayDate,
            "dayStartRealized": self.dayStartRealized,
            "positions": [p.to_dict() for p in self._positions.values()],
            "trades": self.trades[-500:],
            "savedAt": _now_iso(),
        }
        try:
            d = os.path.dirname(self.state_file)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            tmp = self.state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(tmp, self.state_file)
        except OSError as exc:
            raise RuntimeError("페이퍼 포트폴리오를 저장하지 못했습니다 — 거래를 중단합니다") from exc

    def _roll_day(self):
        today = _today_str()
        if today != self.dayDate:
            self.dayDate = today
            self.dayStartRealized = self.realizedPnl

    # ── 포지션 조회 ─────────────────────────────────────────
    def positions(self):
        """보유 포지션 리스트(qty>0)."""
        return [p for p in self._positions.values() if p.qty > 0]

    def get(self, symbol):
        return self._positions.get(symbol)

    def has(self, symbol) -> bool:
        p = self._positions.get(symbol)
        return bool(p and p.qty > 0)

    def __contains__(self, symbol):
        return self.has(symbol)

    # ── 거래 ───────────────────────────────────────────────
    def _log_trade(self, side, symbol, qty, price, realized=None):
        self.trades.append({
            "ts": _now_iso(), "side": side, "symbol": symbol,
            "qty": _f(qty), "price": _f(price),
            "realized": None if realized is None else _f(realized),
        })

    def open(self, symbol, qty, price, name=""):
        """신규 진입(없으면 생성, 있으면 add로 위임)."""
        self._roll_day()
        qty = _f(qty); price = _f(price)
        if qty <= 0 or price <= 0:
            return None
        existing = self._positions.get(symbol)
        if existing and existing.qty > 0:
            return self.add(symbol, qty, price, name=name or existing.name)
        pos = Position(symbol=symbol, qty=qty, avgPrice=price,
                       openedAt=_now_iso(), name=name, peakPrice=price)
        self._positions[symbol] = pos
        self._log_trade("BUY", symbol, qty, price)
        self.save()
        return pos

    def add(self, symbol, qty, price, name=""):
        """기존 포지션에 추가 매수(평단가 가중평균)."""
        self._roll_day()
        qty = _f(qty); price = _f(price)
        if qty <= 0 or price <= 0:
            return None
        pos = self._positions.get(symbol)
        if not pos or pos.qty <= 0:
            return self.open(symbol, qty, price, name=name)
        total_cost = pos.cost() + qty * price
        pos.qty += qty
        pos.avgPrice = total_cost / pos.qty if pos.qty > 0 else price
        if name and not pos.name:
            pos.name = name
        if price > pos.peakPrice:
            pos.peakPrice = price
        self._log_trade("BUY", symbol, qty, price)
        self.save()
        return pos

    def reduce(self, symbol, qty, price):
        """부분 청산. 실현손익 반영. 반환: 실현손익(float) 또는 None."""
        self._roll_day()
        qty = _f(qty); price = _f(price)
        pos = self._positions.get(symbol)
        if not pos or pos.qty <= 0 or qty <= 0 or price <= 0:
            return None
        sell_qty = min(qty, pos.qty)
        realized = (price - pos.avgPrice) * sell_qty
        self.realizedPnl += realized
        pos.qty -= sell_qty
        self._log_trade("SELL", symbol, sell_qty, price, realized)
        if pos.qty <= 1e-9:
            self._positions.pop(symbol, None)
        self.save()
        return realized

    def close(self, symbol, price):
        """전량 청산. 반환: 실현손익(float) 또는 None."""
        pos = self._positions.get(symbol)
        if not pos or pos.qty <= 0:
            return None
        return self.reduce(symbol, pos.qty, price)

    # ── 손익 ───────────────────────────────────────────────
    def mark_to_market(self, prices):
        """현재가 dict({symbol:price})로 평가. 트레일링 최고가도 갱신.

        반환: {unrealized, marketValue, cost, perSymbol{...}} (미실현손익 포함).
        """
        prices = prices or {}
        total_unreal = 0.0
        total_mv = 0.0
        total_cost = 0.0
        per = {}
        for sym, pos in list(self._positions.items()):
            if pos.qty <= 0:
                continue
            price = prices.get(sym)
            if price is None:
                price = pos.avgPrice
            price = _f(price, pos.avgPrice)
            if price > pos.peakPrice:
                pos.peakPrice = price
            u = pos.unrealized(price)
            mv = pos.market_value(price)
            total_unreal += u
            total_mv += mv
            total_cost += pos.cost()
            per[sym] = {
                "qty": pos.qty, "avgPrice": pos.avgPrice, "price": price,
                "unrealized": u, "unrealizedPct": pos.unrealized_pct(price),
                "marketValue": mv,
            }
        return {
            "unrealized": total_unreal,
            "marketValue": total_mv,
            "cost": total_cost,
            "perSymbol": per,
        }

    def total_unrealized(self, prices):
        return self.mark_to_market(prices)["unrealized"]

    def daily_pnl(self, prices=None):
        """당일 실현손익 + 현재 미실현손익(가격 제공 시).

        당일 시작 시점 대비 손익. 킬스위치(risk.daily_loss_kill)에서 사용.
        """
        self._roll_day()
        realized_today = self.realizedPnl - self.dayStartRealized
        unreal = self.total_unrealized(prices) if prices else 0.0
        return realized_today + unreal

    def equity(self, prices=None):
        """평가자산 = 시작현금 + 누적실현 + 미실현."""
        unreal = self.total_unrealized(prices) if prices else 0.0
        return self.startCash + self.realizedPnl + unreal

    def summary(self, prices=None):
        m = self.mark_to_market(prices or {})
        return {
            "positions": len(self.positions()),
            "realizedPnl": self.realizedPnl,
            "unrealized": m["unrealized"],
            "marketValue": m["marketValue"],
            "dailyPnl": self.daily_pnl(prices),
            "equity": self.equity(prices),
        }
