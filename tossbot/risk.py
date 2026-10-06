"""리스크 관리 — 진입 가드 / 일일 손실 킬스위치 / 청산 트리거.

config 의 한도를 사용:
  MAX_OPEN_POSITIONS, MAX_POSITION_KRW, MAX_ORDER_KRW,
  DAILY_LOSS_LIMIT_KRW, STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_PCT.
모두 방어적: 데이터 부족 시 보수적으로 '차단' 또는 None 반환.

⚠️ 교육용 모의 가드이며 투자 권유가 아닙니다.
"""
from __future__ import annotations
import math

from . import config


def _f(v, default=None):
    try:
        if v is None:
            return default
        value = float(v)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


class RiskManager:
    def __init__(self,
                 max_open_positions=None,
                 max_position_krw=None,
                 max_order_krw=None,
                 daily_loss_limit_krw=None,
                 stop_loss_pct=None,
                 take_profit_pct=None,
                 trail_pct=None):
        self.max_open_positions = (max_open_positions
                                   if max_open_positions is not None
                                   else config.MAX_OPEN_POSITIONS)
        self.max_position_krw = (max_position_krw
                                 if max_position_krw is not None
                                 else config.MAX_POSITION_KRW)
        self.max_order_krw = (max_order_krw
                              if max_order_krw is not None
                              else config.MAX_ORDER_KRW)
        self.daily_loss_limit_krw = (daily_loss_limit_krw
                                     if daily_loss_limit_krw is not None
                                     else config.DAILY_LOSS_LIMIT_KRW)
        self.stop_loss_pct = (stop_loss_pct
                              if stop_loss_pct is not None
                              else config.STOP_LOSS_PCT)
        self.take_profit_pct = (take_profit_pct
                                if take_profit_pct is not None
                                else config.TAKE_PROFIT_PCT)
        self.trail_pct = (trail_pct
                          if trail_pct is not None
                          else config.TRAIL_PCT)

    # ── 신규 진입 가드 ─────────────────────────────────────
    def can_open(self, symbol, orderKRW, portfolio):
        """신규/추가 매수 가능 여부. 반환: (bool, reason)."""
        amt = _f(orderKRW, None)
        if amt is None or amt <= 0:
            return False, "주문금액 산정 불가"

        # 1회 주문 한도
        if amt > self.max_order_krw:
            return False, f"1회 주문한도 초과({amt:,.0f}>{self.max_order_krw:,.0f}KRW)"

        already_held = bool(portfolio and portfolio.has(symbol))

        # 동시 보유 종목 수 상한 (이미 보유 중인 종목 추가매수는 카운트 증가 없음)
        if portfolio is not None and not already_held:
            open_n = len(portfolio.positions())
            if open_n >= self.max_open_positions:
                return False, f"동시보유 한도 도달({open_n}/{self.max_open_positions})"

        # 종목당 최대 보유 금액 (기존 보유 평가/취득 + 이번 주문)
        existing_cost = 0.0
        if portfolio is not None:
            pos = portfolio.get(symbol)
            if pos and pos.qty > 0:
                existing_cost = pos.cost()
        if existing_cost + amt > self.max_position_krw:
            return False, (f"종목 보유한도 초과("
                           f"{existing_cost + amt:,.0f}>{self.max_position_krw:,.0f}KRW)")

        return True, "OK"

    # ── 일일 손실 킬스위치 ─────────────────────────────────
    def daily_loss_kill(self, portfolio, prices=None):
        """당일 손익이 한도(-)를 초과 손실하면 True(매매 중단)."""
        if portfolio is None:
            return False
        try:
            pnl = portfolio.daily_pnl(prices)
        except Exception:
            return True
        if pnl is None or not math.isfinite(pnl):
            return True
        limit = _f(self.daily_loss_limit_krw, 0.0) or 0.0
        if limit <= 0:
            return False
        return pnl <= -limit

    # ── 청산(엑싯) 트리거 ──────────────────────────────────
    def exit_signal(self, position, price):
        """보유 포지션의 손절/익절/트레일링 검사. 반환: reason(str) | None."""
        if position is None or getattr(position, "qty", 0) <= 0:
            return None
        avg = _f(getattr(position, "avgPrice", None), None)
        p = _f(price, None)
        if avg is None or avg <= 0 or p is None or p <= 0:
            return None

        change_pct = (p / avg - 1.0) * 100.0

        # 손절
        sl = _f(self.stop_loss_pct, None)
        if sl is not None and sl > 0 and change_pct <= -sl:
            return f"손절 {change_pct:+.1f}%≤-{sl:.1f}%"

        # 익절
        tp = _f(self.take_profit_pct, None)
        if tp is not None and tp > 0 and change_pct >= tp:
            return f"익절 {change_pct:+.1f}%≥+{tp:.1f}%"

        # 트레일링 스탑 (보유 중 최고가 대비 하락폭)
        tr = _f(self.trail_pct, None)
        peak = _f(getattr(position, "peakPrice", None), avg)
        if peak is None or peak < avg:
            peak = avg
        if tr is not None and tr > 0 and peak > 0 and p < peak:
            draw = (p / peak - 1.0) * 100.0
            # 수익권(고점이 평단보다 위)에서만 트레일링 적용
            if peak > avg and draw <= -tr:
                return f"트레일링 고점대비 {draw:+.1f}%≤-{tr:.1f}%"

        return None
