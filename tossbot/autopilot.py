"""모의투자(sim) 전용 퀀트 자동매매 루프 — 데몬 스레드 1개로 운용.

quant.screen() 상위 후보 중 진입존(써폿존)에 들어온 고득점 종목을 모의 계좌(sim)로
매수하고, 목표/손절/시그널 청산 규칙으로 전량 매도한다. 실거래 아님(교육용).

⚠️ 안전 규칙: 이 모듈은 tossbot.sim 모의 원장만 사용한다.
   brokers / client.place_order 등 실주문 경로는 import 도, 호출도 하지 않는다.

프로 패턴 2루프:
  - 스크리닝(무거움: 종목별 analyze)은 rescreen_sec 마다 한 번만 수행해 캐시
  - 매 사이클(interval_sec)은 client.prices(보유∪후보) 한 번으로 가격만 갱신
"""
from __future__ import annotations

import threading
import math
import time
from collections import deque

# regime/notify 는 공유 계약 (R)(T), sim 계좌 API(account 트레일링 키워드,
# active_account 등)는 공유 계약 (S1) 시그니처를 신뢰하고 import 한다.
from . import chart_execution, notify, quant, regime, sim

# 진입 최소 퀀트 점수(0~100). 상위권 신호만 진입해 과매매를 줄인다.
MIN_SCORE = 60

_LOG_MAX = 50   # 체결 로그 최신 50건 유지
_ERR_MAX = 10   # 오류 메시지 최신 10건 유지

# 스레드/상태 보호 락 — start/stop 이중 호출 방지 + status 스냅샷 일관성.
_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None

_status = {
    "startedAt": None,
    "lastCycleAt": None,
    "cycles": 0,
    "settings": {},
}
_log = deque(maxlen=_LOG_MAX)
_errors = deque(maxlen=_ERR_MAX)

# 진입 시점의 매매 플랜(target/stop/entryPrice)을 포지션별로 보관 — 보유 종목이 이후
# 스크리닝 top_n 에서 빠져도 저장된 계획으로 목표/손절을 계속 평가한다(리스크 공백 방지).
# status() 가 "plans" 로 노출하므로 쓰기(추가/삭제)는 _lock 으로 보호한다.
_entry_plans: dict = {}

# 마지막 스크리닝 픽 스냅샷(모니터링용 watch) — 루프에서 락 잡고 통째로 교체,
# status() 는 락 안에서 사본을 반환한다(스레드 안전).
_watch: list = []

# 현재 레짐 스냅샷(status() 노출용) — 쓰기/읽기 모두 _lock 으로 보호.
# stage 가 None 이면 아직 조회 전(또는 가드 꺼짐/조회 실패 지속) 상태.
_regime_now = {"stage": None, "emoji": None, "score": None}

# 레짐 단계 변화 알림에 붙는 대응 요약(새 단계 기준)
_STAGE_NOTE = {
    "STABLE": "평시 운용 재개",
    "TENSION": "평시 운용·관찰 강화",
    "COMPRESSION": "변동성 압축 주의",
    "FRACTURE": "신규 진입 축소",
    "TRIGGER": "신규 진입 중단",
}

# USD/KRW 환율 조회 실패 시 폴백 환율
_FX_FALLBACK = 1300.0

# 계획이 전혀 없는 보유 종목(오토파일럿 밖에서 수동 매수 등)의 고정 손절 폴백: 평단 대비 -8%
_FALLBACK_STOP_PCT = 0.08


def _now():
    return time.strftime("%H:%M:%S")


def _push_error(msg):
    with _lock:
        _errors.append(str(msg)[:200])


def _push_log(symbol, name, side, qty, price, reason, currency="KRW"):
    with _lock:
        _log.append({
            "time": _now(), "symbol": symbol, "name": name, "side": side,
            "currency": currency,
            "qty": int(qty), "price": round(float(price), 2), "reason": reason,
        })


def _fetch_prices(client, symbols):
    """보유∪후보 심볼의 현재가를 한 번에 조회 → {symbol: lastPrice(float)}."""
    out = {}
    if not symbols:
        return out
    for row in client.prices(sorted(symbols)):
        lp = row.get("lastPrice")
        if lp is not None:
            value = float(lp)
            if math.isfinite(value) and value > 0:
                out[row["symbol"]] = value
    return out


def _get_usd_fx(client, strict=False):
    """USD/KRW 환율 1회 조회 — None/0/예외 시 폴백(1300.0). 사이클당 한 번만 호출."""
    try:
        fx = client.exchange_rate("USD", "KRW")
        if fx and math.isfinite(float(fx)) and float(fx) > 0:
            return float(fx)
        return None if strict else _FX_FALLBACK
    except Exception as e:  # noqa: BLE001 - 환율 실패가 사이클을 죽이지 않게
        _push_error(f"환율 조회 실패(폴백 {_FX_FALLBACK:.0f}): {e}")
        return None if strict else _FX_FALLBACK


def _need_usd_fx(picks, account=None):
    """픽 또는 보유 포지션에 USD 종목이 있는지 — 환율 조회 필요 여부 판단."""
    if any((p.get("currency") or "KRW") == "USD" for p in picks):
        return True
    try:
        return any(
            (pos.get("currency") or "KRW") == "USD"
            for pos in sim.get_state(account=account).get("positions", []))
    except Exception:  # noqa: BLE001 - 상태 조회 실패 시 KRW 로 간주
        return False


def _notify_safe(text):
    """알림 전송 — 어떤 실패도 매매 루프에 영향을 주지 않는다(무해)."""
    try:
        notify.send(text)
    except Exception:  # noqa: BLE001 - 알림 실패는 조용히 무시
        pass


def _notify_fill(symbol, name, side, qty, price, reason, currency="KRW"):
    """체결 알림 훅 — 예: 🤖 [모의] BUY 삼성전자 3주 @339,000원 — 퀀트 진입: 써폿존"""
    if currency == "USD":
        price_str = f"@${float(price):,.2f}"
    else:
        price_str = f"@{float(price):,.0f}원"
    _notify_safe(f"🤖 [모의] {side} {name or symbol} {int(qty)}주 {price_str} — {reason}")


def _guard_params(stage, budget_krw):
    """레짐 가드 규칙 → (신규진입 허용 여부, 적용 예산, 적용 최소점수).

    근거(공유 계약 (A)):
      FRACTURE(스코어 60-80) — 시장 균열 구간: 신규 진입 '예산 50%' 로 축소하고
        MIN_SCORE+10 으로 신호 문턱을 올려 최상위 신호만 소액 진입.
      TRIGGER(80+) — 위험 발화 구간: 신규 진입 전면 중단(방어 최우선).
        단, 청산(목표/손절/시그널)은 계속 동작해 기존 포지션을 보호한다.
      조회 실패(None): 신규 진입을 보류하고 청산은 계속한다.
    """
    if stage not in ("STABLE", "TENSION", "COMPRESSION", "FRACTURE"):
        return False, budget_krw, MIN_SCORE
    if stage == "FRACTURE":
        return True, budget_krw * 0.5, MIN_SCORE + 10
    return True, budget_krw, MIN_SCORE


def _update_regime(client, strict=False):
    """레짐 조회 + 상태 갱신 + 단계 변화 알림. 반환: stage 또는 None(실패).

    regime 모듈이 300s 캐시를 갖고 있어 매 사이클 호출해도 부담이 없다.
    조회 실패 시 None 을 반환해 신규 진입을 보류한다
    — 이때 이전 스냅샷은 지우지 않고 유지한다(마지막으로 알려진 레짐 표시).
    """
    try:
        r = regime.get_regime(client)
        stage = r.get("stage")
        emoji = r.get("emoji")
        score = r.get("score")
    except Exception as e:  # noqa: BLE001 - 레짐 실패가 루프를 죽이지 않게
        _push_error(f"레짐 조회 실패(신규 진입 보류): {e}")
        return None
    if not stage:
        return None
    if strict:
        comps = r.get("components") or []
        valid = {c.get("key") for c in comps if isinstance(c, dict)
                 and isinstance(c.get("value"), (int, float)) and math.isfinite(c["value"])}
        if r.get("stale") or r.get("degraded") or valid != {"vix", "vvix", "spx", "tlt", "uup", "hyg"}:
            with _lock:
                _regime_now.update(stage=None, emoji=None, score=None)
            _push_error("레짐 입력 누락·지연: 차트 전략 신규 진입 보류")
            return None
    with _lock:
        prev_stage = _regime_now["stage"]
        prev_emoji = _regime_now["emoji"]
        _regime_now["stage"] = stage
        _regime_now["emoji"] = emoji
        _regime_now["score"] = score
    # 단계가 실제로 바뀐 경우에만 알림(첫 조회는 제외) — 실패 무해
    if prev_stage and stage != prev_stage:
        _notify_safe(
            f"⚠️ 시장 레짐 변화: {prev_emoji or ''} {prev_stage} → "
            f"{emoji or ''} {stage} — {_STAGE_NOTE.get(stage, '대응 단계 조정')}"
        )
    return stage


def _try_exits(picks_by_sym, prices, max_positions, usd_fx=1.0, account=None):
    """보유 종목 청산 규칙: 목표 도달 / 손절 / 시그널 청산 → 전량 매도.

    후보(top_n)에서 빠진 보유 종목도 진입 시점에 저장한 _entry_plans 로 계속
    평가하고, 그마저 없으면(수동 매수 등) 평단 대비 -8% 고정 손절을 적용해
    '손절 없는 무기한 보유' 리스크 공백을 막는다.
    usd_fx: USD/KRW 환율 — USD 포지션 평가/청산에만 적용(KRW 는 1.0 그대로).
    account: 시작 시점에 고정한 sim 계좌 id — 모든 원장 접근에 전달.
    """
    # 통화별 환율은 sim 이 currency 로 구분 적용 — 계좌는 캡처한 id 로 고정
    state = sim.get_state(prices, usd_fx, account=account)
    persisted = sim.execution_plans(account=account)
    for pos in state["positions"]:
        sym = pos["symbol"]
        pick = picks_by_sym.get(sym)
        price = prices.get(sym)
        if price is None or price <= 0:
            continue
        # 계획 우선순위: 이번 스크리닝 pick → 진입 시점 저장분 → 고정 손절 폴백
        plan = (persisted.get(sym) or _entry_plans.get(sym)
                or (pick.get("plan") if pick else None) or {})
        target = plan.get("target")
        stop_lv = plan.get("stop")
        if stop_lv is None and pos.get("avgPrice"):
            stop_lv = float(pos["avgPrice"]) * (1 - _FALLBACK_STOP_PCT)
        reason = None
        if target is not None and price >= float(target):
            reason = "목표 도달"
        elif stop_lv is not None and price <= float(stop_lv):
            reason = "손절"
        elif pick is not None and pick.get("action") == "SELL":
            reason = "시그널 청산"
        if not reason:
            continue
        name = (pick.get("name", "") if pick else "") or pos.get("name", "")
        # 청산 통화는 '포지션'의 통화를 따른다(픽에서 빠진 보유분도 정확히 환산).
        ccy = pos.get("currency", "KRW") or "KRW"
        fx = usd_fx if ccy == "USD" else 1.0
        try:
            sim.order(sym, "SELL", pos["qty"], price, currency=ccy, fx=fx,
                      name=name, note=f"오토파일럿: {reason}", account=account)
            with _lock:
                _entry_plans.pop(sym, None)
            _push_log(sym, name, "SELL", pos["qty"], price, reason, currency=ccy)
            _notify_fill(sym, name, "SELL", pos["qty"], price, reason, currency=ccy)
        except sim.SimError as e:
            _push_error(f"{sym} 매도 실패: {e}")
        except Exception as e:  # noqa: BLE001 - 한 종목 실패가 루프를 죽이지 않게
            _push_error(f"{sym} 매도 오류: {e}")


def _try_entries(picks, prices, max_positions, budget_krw, usd_fx=1.0,
                 min_score=MIN_SCORE, account=None):
    """진입 규칙: BUY 시그널 + 진입존(inZone) + 점수>=min_score + 미보유 + 슬롯 여유.

    usd_fx: USD/KRW 환율 — USD 픽은 예산(원화) 환산·주문 환율에 적용, KRW 는 1.0.
    min_score: 진입 최소 점수 — 레짐 가드(FRACTURE)가 MIN_SCORE+10 으로 올려 전달.
    account: 시작 시점에 고정한 sim 계좌 id — 보유 조회/주문 모두 이 계좌로.
    """
    # 보유 목록은 루프 진입 시 1회만 로드하고 체결 시 로컬로 갱신 — pick 마다
    # 상태 파일을 재로드하던 비용(최대 top_n 회)과 파일 경합 창을 없앤다.
    held = set(sim.held_symbols(account=account))
    for pick in picks:  # picks 는 quantScore 내림차순 → 고득점부터 슬롯 채움
        if len(held) >= max_positions:
            break
        sym = pick.get("symbol")
        if not sym or sym in held:
            continue
        if pick.get("action") != "BUY":
            continue
        plan = pick.get("plan") or {}
        if not plan.get("inZone"):
            continue
        score = pick.get("quantScore")
        if score is None or float(score) < min_score:
            continue
        price = prices.get(sym)
        if price is None or not math.isfinite(float(price)) or float(price) <= 0:
            continue
        price = float(price)
        # inZone 은 스크리닝 시점 판정이므로, 캐시가 오래된 사이에 가격이 존을
        # 이탈했을 수 있다 → 진입존 레벨이 있으면 '현재가' 기준으로 재확인해
        # 존 위(심하면 목표가 위)에서 추격 매수하는 것을 막는다.
        lo, hi = plan.get("entryLow"), plan.get("entryHigh")
        if lo is not None and hi is not None and not (float(lo) <= price <= float(hi)):
            continue
        # 픽의 통화(USD 면 환율 적용)로 원화 환산 단가 → 예산 내 수량 산출
        ccy = pick.get("currency", "KRW") or "KRW"
        fx = usd_fx if ccy == "USD" else 1.0
        price_krw = price * fx
        qty = int(budget_krw // price_krw)
        if qty <= 0:
            # 1주 가격이 예산(레짐 가드로 축소된 eff_budget 포함)을 초과 — 진입 스킵.
            # 예전 max(1, …) 은 고가 종목에서 예산·FRACTURE 축소 계약을 우회했다.
            continue
        try:
            sim.order(sym, "BUY", qty, price, currency=ccy, fx=fx,
                      name=pick.get("name", ""),
                      note="오토파일럿: 퀀트 진입(써폿존)", account=account)
            held.add(sym)
            # 진입 시점 계획 보관 — 이후 후보 탈락해도 목표/손절 평가 지속
            # (entryPrice 는 진입 체결가 — status().plans 로 모니터링에 노출)
            with _lock:
                _entry_plans[sym] = {"target": plan.get("target"),
                                     "stop": plan.get("stop"),
                                     "entryPrice": price}
            _push_log(sym, pick.get("name", ""), "BUY", qty, price, "퀀트 진입: 써폿존",
                      currency=ccy)
            _notify_fill(sym, pick.get("name", ""), "BUY", qty, price,
                         "퀀트 진입: 써폿존", currency=ccy)
        except sim.SimError as e:
            _push_error(f"{sym} 매수 실패: {e}")
        except Exception as e:  # noqa: BLE001
            _push_error(f"{sym} 매수 오류: {e}")


def _try_chart_entries(picks, prices, max_positions, budget_krw, usd_fx=1.0,
                       account=None, risk_pct=.5, min_rr=1.5, check_stop=False):
    for pick in picks:
        if check_stop and _stop_event.is_set():
            break
        info = pick.get("timing") or {}
        plan = info.get("plan")
        sym = pick.get("symbol")
        if not info.get("eligible") or not sym or not plan:
            continue
        state = sim.get_state(prices, usd_fx or 1.0, account=account)
        if len(state["positions"]) >= max_positions or sym in {p["symbol"] for p in state["positions"]}:
            info["entryReason"] = "보유 중 / 최대 종목 수 도달"
            continue
        if sim.signal_used(plan["signalId"], account=account):
            info["entryReason"] = "이미 사용한 확인 신호"
            continue
        if any(not isinstance(prices.get(pos["symbol"]), (int, float))
               or not math.isfinite(prices[pos["symbol"]]) or prices[pos["symbol"]] <= 0
               for pos in state["positions"]):
            info["entryReason"] = "보유 종목 현재가 확인 실패"
            continue
        # Unknown USD valuation makes equity-based risk sizing unavailable.
        if usd_fx is None:
            info["entryReason"] = "환율 확인 실패"
            continue
        persisted = sim.execution_plans(account=account)
        open_risk = 0.0
        for pos in state["positions"]:
            protective = persisted.get(pos["symbol"]) or _entry_plans.get(pos["symbol"], {})
            stop = protective.get("stop") or pos["avgPrice"] * (1 - _FALLBACK_STOP_PCT)
            rate = usd_fx if pos["currency"] == "USD" else 1.0
            open_risk += max(0, pos["currentPrice"] - stop * (1 - sim.FEE_RATE - sim.TAX_RATE)) * pos["qty"] * rate
        fx = usd_fx if pick.get("currency") == "USD" else 1.0
        size = chart_execution.entry_size(plan, prices.get(sym), state["cash"], state["equity"],
                                          budget_krw, risk_pct, min_rr, fx, open_risk=open_risk,
                                          max_positions=max_positions)
        info.update(entryReason=size["reason"], netRR=size["netRR"], proposedQty=size["qty"])
        if size["qty"] <= 0:
            continue
        execution = {**plan, "entryPrice": prices[sym], "riskKrw": size["riskKrw"], "netRR": size["netRR"]}
        try:
            sim.order(sym, "BUY", size["qty"], prices[sym], currency=pick.get("currency", "KRW"),
                      fx=fx, name=pick.get("name", ""), note="오토파일럿: 차트 확인 진입",
                      account=account, execution_plan=execution)
            with _lock:
                _entry_plans[sym] = execution
            _push_log(sym, pick.get("name", ""), "BUY", size["qty"], prices[sym], size["reason"], pick.get("currency", "KRW"))
            _notify_fill(sym, pick.get("name", ""), "BUY", size["qty"], prices[sym], size["reason"], pick.get("currency", "KRW"))
        except Exception as e:
            info["entryReason"] = "모의 주문 실패"
            _push_error(f"{sym} 차트 매수 실패: {e}")


def _run(client, interval_sec, max_positions, budget_krw, top_n, rescreen_sec,
         market="kr", regime_guard=True, account=None, strategy="legacy", risk_pct=.5, min_rr=1.5):
    # account: start() 가 캡처해 넘긴 sim 계좌 id — 루프 내 모든 sim 호출에 고정 전달.
    #   사용자가 도중에 active 계좌를 바꿔도 이 오토파일럿은 자기 계좌만 매매한다.
    picks = []
    last_screen = None  # monotonic 기준 마지막 스크리닝 시각
    while not _stop_event.is_set():
        try:
            now = time.monotonic()

            # ⓪ 레짐 가드 — regime 모듈 캐시(300s) 덕에 매 사이클 확인해도 가볍다.
            #   조회 실패(stage=None) 시에는 신규 진입을 보류한다.
            allow_entries, eff_budget, eff_min_score = True, budget_krw, MIN_SCORE
            if regime_guard:
                stage = _update_regime(client, strict=strategy == "chart_confirmed")
                allow_entries, eff_budget, eff_min_score = _guard_params(
                    stage, budget_krw)
            # ①-0 스크리닝(market=all 이면 수 분)이 도는 동안 손절/목표 평가가 멈추지
            #     않도록, rescreen 사이클에서는 '스크리닝 전에' 캐시된 picks 기준으로
            #     가격 1콜 + 청산(_try_exits)을 먼저 수행한다(리스크 공백 제거).
            rescreen_due = last_screen is None or (now - last_screen) >= rescreen_sec
            if rescreen_due:
                try:
                    pre_by_sym = {p["symbol"]: p for p in picks if p.get("symbol")}
                    pre_syms = set(sim.held_symbols(account=account)) | set(pre_by_sym)
                    pre_prices = _fetch_prices(client, pre_syms) if pre_syms else {}
                    if pre_prices:
                        pre_fx = (_get_usd_fx(client)
                                  if _need_usd_fx(picks, account=account) else 1.0)
                        _try_exits(pre_by_sym, pre_prices, max_positions, pre_fx,
                                   account=account)
                except Exception as e:  # noqa: BLE001 - 선행 청산 실패해도 사이클 계속
                    _push_error(f"청산 선행 패스 오류: {e}")

            # ① 스크리닝은 rescreen_sec 마다만 (quant.screen 은 종목별 analyze 로 무거움)
            if rescreen_due:
                try:
                    res = quant.screen(client, top_n=top_n, market=market, strategy=strategy,
                                       include_symbols=sim.held_symbols(account=account) if strategy == "chart_confirmed" else ())
                    picks = list(res.get("picks") or [])
                    last_screen = time.monotonic()
                except Exception as e:  # noqa: BLE001 - 스크리닝 실패해도 기존 캐시로 계속
                    _push_error(f"스크리닝 실패: {e}")
                    if strategy == "chart_confirmed":
                        allow_entries = False
                        picks = []
                    last_screen = time.monotonic()  # 재시도 폭주 방지
            if _stop_event.is_set():
                break
            picks_by_sym = {p["symbol"]: p for p in picks if p.get("symbol")}

            # ② 매 사이클: 보유∪후보 가격만 일괄 갱신 (prices 1콜)
            symbols = set(sim.held_symbols(account=account)) | set(picks_by_sym.keys())
            try:
                prices = _fetch_prices(client, symbols)
            except Exception as e:  # noqa: BLE001 - 시세 실패 시 이번 사이클은 관망
                _push_error(f"시세 조회 실패: {e}")
                prices = {}

            # ②-1 USD 종목(픽 또는 보유)이 하나라도 있으면 환율을 사이클당 1회만 조회
            usd_fx = (_get_usd_fx(client, strict=strategy == "chart_confirmed")
                      if _need_usd_fx(picks, account=account) else 1.0)

            if strategy == "chart_confirmed":
                for pick in picks:
                    info = pick.get("timing") or {}
                    info.pop("entryReason", None)
                    if not allow_entries:
                        info["entryReason"] = "레짐 가드: 신규 진입 보류"

            if prices:
                # ③ 청산 먼저(슬롯 확보) — 레짐과 무관하게 항상 수행(포지션 방어)
                _try_exits(picks_by_sym, prices, max_positions, usd_fx or _FX_FALLBACK,
                           account=account)
                # ④ 진입 — TRIGGER 면 전면 중단, FRACTURE 면 예산 50%·점수 문턱 +10
                if allow_entries and not _stop_event.is_set():
                    if strategy == "chart_confirmed":
                        _try_chart_entries(picks, prices, max_positions, eff_budget, usd_fx,
                                           account=account, risk_pct=risk_pct, min_rr=min_rr, check_stop=True)
                    else:
                        _try_entries(picks, prices, max_positions, eff_budget,
                                     usd_fx, min_score=eff_min_score, account=account)

            # ⑤ 모니터링용 watch 스냅샷 갱신 — 최신 가격이 있으면 반영해 통째 교체
            watch = []
            for p in picks:
                sym = p.get("symbol")
                cur = prices.get(sym)
                watch.append({
                    "symbol": sym,
                    "name": p.get("name", ""),
                    "price": cur if cur is not None else p.get("price"),
                    "currency": p.get("currency", "KRW") or "KRW",
                    "quantScore": p.get("quantScore"),
                    "action": p.get("action", "HOLD"),
                    "inZone": bool((p.get("plan") or {}).get("inZone")),
                    "timing": dict(p.get("timing") or {}),
                })

            with _lock:
                _watch[:] = watch
                _status["cycles"] += 1
                _status["lastCycleAt"] = _now()
        except Exception as e:  # noqa: BLE001 - 어떤 예외도 루프를 죽이지 않는다
            _push_error(f"사이클 오류: {e}")
        # stop() 호출 시 즉시 깨어나도록 Event.wait 로 대기 (소수 간격도 존중해 busy-loop 방지)
        _stop_event.wait(max(0.05, float(interval_sec)))


def start(client, interval_sec=60, max_positions=3, budget_krw=1_000_000,
          top_n=10, rescreen_sec=300, market="kr", regime_guard=True,
          account=None, strategy="legacy", risk_pct=.5, min_rr=1.5):
    """자동매매 스레드 시작(이미 실행 중이면 무시하고 현재 상태 반환).

    market: 스크리닝 유니버스 — "kr"(코스피) / "us"(미국) / "all"(둘 다).
    regime_guard: 시장 레짐 가드 — FRACTURE 진입 축소 / TRIGGER 진입 중단.
    account: 매매 대상 sim 계좌 id — None 이면 '시작 시점' 의 active 계좌를 캡처해
      고정한다. 이후 사용자가 active 계좌를 바꿔도 이 오토파일럿은 자기 계좌 유지.
    """
    global _thread
    if strategy not in ("legacy", "chart_confirmed") or not (math.isfinite(risk_pct) and .1 <= risk_pct <= 2 and math.isfinite(min_rr) and 1 <= min_rr <= 5):
        raise ValueError("차트 전략·위험 비율·순손익비 설정을 확인하세요.")
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _snapshot_locked()  # 이중 start 방지
        # 계좌 고정 — 미지정이면 시작 시점의 active 계좌를 캡처(공유 계약 (S1)).
        acc = str(account) if account else str(sim.active_account())
        _stop_event.clear()
        _status["startedAt"] = _now()
        _status["lastCycleAt"] = None
        _status["cycles"] = 0
        _status["settings"] = {
            "intervalSec": int(interval_sec), "maxPositions": int(max_positions),
            "budgetKrw": int(budget_krw), "topN": int(top_n),
            "rescreenSec": int(rescreen_sec), "market": str(market),
            "regimeGuard": bool(regime_guard), "account": acc,
            "strategy": strategy, "riskPct": risk_pct, "minRR": min_rr,
        }
        _watch[:] = []  # 이전 세션의 감시 목록 잔재 제거
        # 이전 세션의 진입 계획 잔재 제거 — 다른 계좌로 재시작할 때 같은 심볼의
        # '다른 계좌 포지션'에 이전 계좌의 target/stop 이 적용되는 누수를 막는다.
        # (계획이 없는 보유 종목은 픽 계획 또는 평단 -8% 폴백 손절로 계속 평가됨)
        _entry_plans.clear()
        _entry_plans.update(sim.execution_plans(account=acc))
        # 이전 세션의 레짐 잔재 제거 — 첫 조회를 '변화 알림' 으로 오인하지 않게
        _regime_now.update({"stage": None, "emoji": None, "score": None})
        _thread = threading.Thread(
            target=_run, name="autopilot",
            args=(client, float(interval_sec), int(max_positions), int(budget_krw),
                  int(top_n), float(rescreen_sec), str(market),
                  bool(regime_guard), acc, strategy, risk_pct, min_rr),
            daemon=True,
        )
        _thread.start()
        return _snapshot_locked()


def stop():
    """자동매매 스레드 정지(graceful join). 진행 중 사이클은 마치고 종료."""
    _stop_event.set()
    with _lock:
        t = _thread
    if t is not None and t.is_alive():
        # 사이클 대기(Event.wait)는 즉시 깨어나므로 네트워크 호출 잔여분만 기다린다.
        t.join(timeout=10)
    return status()


def status():
    with _lock:
        return _snapshot_locked()


def reset_logs():
    """체결·오류 로그만 비운다. 보유 종목의 목표/손절 계획은 유지한다."""
    with _lock:
        _log.clear()
        _errors.clear()
        return _snapshot_locked()


def _snapshot_locked():
    """_lock 을 잡은 상태에서 호출 — status 스냅샷(최신 로그가 앞에 오도록).

    모니터링 확장 필드(기존 키 불변):
      market  — 스크리닝 시장 설정("kr"/"us"/"all")
      account — 시작 시 고정한 sim 계좌 id (시작 전이면 None)
      watch   — 최근 스크리닝 픽 스냅샷(최신 가격 반영)
      plans   — 오토파일럿이 진입한 포지션의 계획(target/stop/entryPrice)
      regime  — 마지막 확인한 시장 레짐 {stage, emoji, score} (미조회 시 None들)
    """
    return {
        "running": bool(_thread is not None and _thread.is_alive()),
        "startedAt": _status["startedAt"],
        "lastCycleAt": _status["lastCycleAt"],
        "cycles": _status["cycles"],
        "settings": dict(_status["settings"]),
        "market": _status["settings"].get("market"),
        "account": _status["settings"].get("account"),
        "regime": dict(_regime_now),
        "watch": [dict(w) for w in _watch],
        "plans": {s: dict(p) for s, p in _entry_plans.items()},
        "log": list(_log)[::-1],
        "errors": list(_errors)[::-1],
    }
