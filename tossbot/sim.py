"""모의투자(페이퍼) 계좌 — 수동 매수/매도 연습용. 원화(KRW) 계좌 기준.

미국 종목은 환율로 원화 환산(매수 시 원화 차감, 평가/손익 원화). 표시는 종목 통화(달러/원)로.
수수료(0.015%)·매도세(0.18%) 반영. 실거래 아님(교육용).

v2: 멀티계좌 지원. 상태 파일(.sim_state.json) 구조:
  {"version":2, "active":"<id>", "accounts":{ id: {"name","createdAt","cash","initialCash",
   "positions":{...}, "history":[...], "realizedPnl", ...} }}
기존 v1(top-level 에 "cash")은 로드 시 "default" 계좌로 감싸 1회 마이그레이션한다
(보유·내역·note 전부 보존, 원자적 저장 — 실패 시 원본 무손상).
모든 공개 API 는 account=None(→active 계좌) 트레일링 키워드로 하위호환을 유지한다.
"""
from __future__ import annotations
import json
import copy
import math
import os
import threading
import time

from . import paths
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 패키징(frozen) 시 %APPDATA%\tossbot 등 영구 폴더로, 소스 실행 시 프로젝트 루트로.
STATE_FILE = paths.state_path(".sim_state.json")

INITIAL_CASH = 10_000_000   # 시드머니 1,000만원(KRW)
FEE_RATE = 0.00015          # 매매 수수료 0.015%
TAX_RATE = 0.0018           # 매도 거래세 0.18%
MAX_ACCOUNTS = 8            # 계좌 최대 개수
HISTORY_MAX = 1000          # 계좌당 히스토리 보관 상한(초과분 오래된 것부터 롤링 삭제)

_lock = threading.Lock()

# _load 파싱 캐시 — 파일 (mtime_ns, size) 가 마지막 파싱/저장 시점과 같으면
# 메모리 사본을 재사용해 5초 폴링·오토파일럿 사이클의 반복 풀 파싱을 없앤다.
# 반환 객체가 공유되므로 이 모듈의 규약: _load 호출과 반환 상태의 읽기/쓰기는
# 반드시 _lock 안에서만 수행한다(모든 공개 API 가 이를 지킨다. journal.stats 포함).
_cache_key = None    # (st_mtime_ns, st_size) — None 이면 캐시 없음
_cache_state = None


def _stat_key():
    try:
        s = os.stat(STATE_FILE)
        return (s.st_mtime_ns, s.st_size)
    except OSError:
        return None


class SimError(Exception):
    pass


def _positive(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise SimError(f"{label}을 확인하세요.") from None
    if isinstance(value, bool) or not math.isfinite(number) or number <= 0:
        raise SimError(f"{label}은 유효한 양수여야 합니다.")
    return number


def _validate_state(st):
    accounts = st.get("accounts") if isinstance(st, dict) else None
    if not isinstance(accounts, dict) or not accounts:
        raise SimError("모의계좌 파일이 손상되었습니다 — 원본을 보존하고 복구하세요.")
    for acc in accounts.values():
        if not isinstance(acc, dict) or not isinstance(acc.get("positions"), dict) or not isinstance(acc.get("history"), list):
            raise SimError("모의계좌 파일의 구조를 확인하세요.")
        for key in ("cash", "initialCash", "realizedPnl"):
            value = acc.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise SimError("모의계좌 파일에 유효하지 않은 금액이 있습니다.")
        if acc["cash"] < 0 or acc["initialCash"] <= 0:
            raise SimError("모의계좌 파일의 잔고를 확인하세요.")
        for pos in acc["positions"].values():
            if not isinstance(pos, dict) or pos.get("currency", "KRW") not in ("KRW", "USD"):
                raise SimError("모의계좌 파일의 보유 종목을 확인하세요.")
            for key in ("qty", "avgPrice"):
                _positive(pos.get(key), "보유 수량/가격")
            if "avgPriceKrw" in pos:
                _positive(pos["avgPriceKrw"], "원화 매수 원가")


def _new(cash=INITIAL_CASH, name="기본 계좌"):
    # 계좌 1개 분량의 초기 상태(v1 필드 + name).
    cash = _positive(cash, "초기 자본금")
    return {"name": str(name), "cash": cash, "initialCash": cash,
            "positions": {}, "history": [], "realizedPnl": 0.0, "createdAt": int(time.time())}


def _new_state(cash=INITIAL_CASH):
    # v2 초기 상태(기본 계좌 1개).
    return {"version": 2, "active": "default", "accounts": {"default": _new(cash)}}


def _migrate_v1(raw):
    """v1(top-level cash) → v2 로 감싼 '사본' dict 반환. 원본 raw 는 건드리지 않는다.

    v1 의 모든 필드(positions/history/note/createdAt 등)를 한 바이트도 잃지 않고
    default 계좌 아래로 옮긴다. name/createdAt 은 없을 때만 채운다.
    """
    acct = {"name": "기본 계좌", "createdAt": int(time.time())}
    acct.update(raw)  # v1 전체 필드 그대로(기존 createdAt 이 있으면 그것이 우선)
    return {"version": 2, "active": "default", "accounts": {"default": acct}}


# 마이그레이션 저장 전용 락 — _lock 과 별도(재진입 데드락 방지: order/reset 등은
# 이미 _lock 을 잡은 채 _load 를 부른다). 파일이 v1 인 짧은 기간 동안 무락 읽기
# 경로(get_state 등)의 마이그레이션 저장이 락 보유 쓰기 경로(order)의 체결 저장을
# 덮어써 첫 거래가 유실되는 레이스를 막는다.
_migrate_lock = threading.Lock()


def _load():
    # 로드 + (필요 시) v1→v2 마이그레이션 1회 수행: 감지→사본 변환→원자 저장→변환본 반환.
    # 파일이 변경되지 않았으면(파싱 캐시 hit) 메모리 사본을 그대로 재사용한다.
    global _cache_key, _cache_state
    if os.path.exists(STATE_FILE):
        key = _stat_key()  # open 전에 stat — 사이에 파일이 바뀌면 다음 호출에서 재파싱(안전 방향)
        if key is not None and key == _cache_key and _cache_state is not None:
            return _cache_state
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            raise SimError("모의계좌 파일을 읽을 수 없습니다 — 원본을 보존하고 복구하세요.") from e
        if isinstance(raw, dict):
            if "cash" in raw:                       # v1 감지(top-level 에 cash)
                with _migrate_lock:
                    # 락 획득 후 재확인 — 다른 스레드가 먼저 마이그레이션·저장했을 수 있다.
                    try:
                        with open(STATE_FILE, encoding="utf-8") as f:
                            raw2 = json.load(f)
                    except Exception:
                        raw2 = raw
                    if isinstance(raw2, dict) and "cash" not in raw2 \
                            and isinstance(raw2.get("accounts"), dict) and raw2.get("accounts"):
                        return raw2  # 이미 v2 — 그대로 사용
                    st = _migrate_v1(raw2 if isinstance(raw2, dict) else raw)
                    _validate_state(st)
                    _save(st)                        # 원자적 저장(os.replace) — 실패해도 원본 무손상
                    return st
            if isinstance(raw.get("accounts"), dict) and raw.get("accounts"):
                _validate_state(raw)
                if raw.get("active") not in raw["accounts"]:
                    raw["active"] = next(iter(raw["accounts"]))  # active 꼬임 방어
                _cache_key, _cache_state = key, raw
                return raw
        raise SimError("모의계좌 파일이 손상되었습니다 — 원본을 보존하고 복구하세요.")
    return _new_state()


def _save(st):
    global _cache_key, _cache_state
    tmp = STATE_FILE + ".tmp"
    try:
        _validate_state(st)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        # Windows 파일 공유 충돌만 제한된 횟수로 재시도한다.
        for attempt in range(5):
            try:
                os.replace(tmp, STATE_FILE)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    except Exception:
        # 어떤 저장 실패에서도 변경된 공유 객체를 다시 사용하지 않는다.
        _cache_key = None
        _cache_state = None
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    _cache_state = st
    _cache_key = _stat_key()


def _acct(st, account=None):
    """account(None 이면 active) → (id, 계좌 dict). 없으면 SimError."""
    acc_id = account or st.get("active")
    acc = (st.get("accounts") or {}).get(acc_id)
    if acc is None:
        raise SimError(f"계좌를 찾을 수 없습니다: {acc_id}")
    return acc_id, acc


def _fx_of(ccy, fx):
    # fx 인자는 'USD/KRW 환율'로 해석. USD 포지션에만 적용, KRW 는 1.0(환율 미적용).
    return _positive(fx, "환율") if ccy == "USD" else 1.0


def get_state(price_map=None, fx=1.0, account=None):
    # fx = USD/KRW 환율(단일). 각 포지션 통화(ccy)에 맞춰 _fx_of 로만 환산해
    # KR(원화)+US(달러) 동시 보유 시에도 한쪽 환율이 양쪽에 잘못 곱해지지 않도록 한다.
    # account=None 이면 active 계좌 기준(반환 dict shape 는 v1 과 동일 — 서버/프론트 무회귀).
    # _load 가 파싱 캐시(공유 객체)를 반환할 수 있으므로 읽기 전체를 _lock 으로 보호한다
    # — 겸사겸사 Windows 에서 _save(os.replace)와 무락 open 이 충돌하는 창도 없앤다.
    with _lock:
        st = _load()
        _, acc = _acct(st, account)
        price_map = price_map or {}
        positions, holdings_krw, unreal_krw = [], 0.0, 0.0
        for sym, p in acc["positions"].items():
            qty = p["qty"]
            avg = p["avgPrice"]                    # 종목 통화(native)
            ccy = p.get("currency", "KRW")
            avg_krw = p.get("avgPriceKrw", avg)    # 매수 시점 원화 단가
            raw = price_map.get(sym)
            try:
                cur = _positive(raw, "현재가") if raw is not None else avg
            except SimError:
                cur = avg
            rate = _fx_of(ccy, fx)                 # 포지션 통화별 환율(USD 만 fx, KRW 는 1.0)
            val_krw = qty * cur * rate
            cost_krw = qty * avg_krw
            pnl = val_krw - cost_krw
            holdings_krw += val_krw
            unreal_krw += pnl
            positions.append({
                "symbol": sym, "name": p.get("name", ""), "qty": qty, "currency": ccy,
                "avgPrice": round(avg, 2), "currentPrice": round(cur, 2),
                "valueKrw": round(val_krw), "pnl": round(pnl),
                "pnlPct": round(pnl / cost_krw * 100, 2) if cost_krw else 0.0,
            })
        cash = acc["cash"]
        equity = cash + holdings_krw
        total_pnl = acc["realizedPnl"] + unreal_krw
        init = acc["initialCash"] or INITIAL_CASH
        return {
            "cash": round(cash), "initialCash": round(init),
            "holdingsValue": round(holdings_krw), "equity": round(equity),
            "realizedPnl": round(acc["realizedPnl"]), "unrealizedPnl": round(unreal_krw),
            "totalPnl": round(total_pnl), "totalPnlPct": round(total_pnl / init * 100, 2) if init else 0.0,
            "positions": sorted(positions, key=lambda x: -x["valueKrw"]),
            "history": list(reversed(acc["history"][-60:])),
        }


def held_symbols(account=None):
    with _lock:
        st = _load()
        _, acc = _acct(st, account)
        return list(acc["positions"].keys())


def execution_plans(account=None):
    """Persisted protective plans, isolated to this account."""
    with _lock:
        _, acc = _acct(_load(), account)
        return copy.deepcopy({s: p["executionPlan"] for s, p in acc["positions"].items()
                              if p.get("executionPlan")})


def signal_used(signal_id, account=None):
    with _lock:
        _, acc = _acct(_load(), account)
        return signal_id in acc.get("chartSignals", {})


def order(symbol, side, qty, price, currency="KRW", fx=1.0, name="", note="", account=None,
          execution_plan=None):
    # note: 매매 근거 메모(선택). 기본 "" 이므로 기존 호출부는 무영향(하위호환).
    # account: 대상 계좌 id(None 이면 active). 존재하지 않으면 SimError.
    try:
        quantity = _positive(qty, "수량")
    except SimError:
        raise SimError("수량은 1주 이상이어야 합니다.")
    if not quantity.is_integer():
        raise SimError("수량은 정수여야 합니다.")
    qty = int(quantity)
    price = _positive(price, "현재가")
    fx = _positive(fx, "환율")
    symbol = str(symbol or "").strip().upper()
    side = str(side).upper()
    if not symbol or side not in ("BUY", "SELL") or currency not in ("KRW", "USD"):
        raise SimError("종목·매매 방향·통화를 확인하세요.")
    rate = _fx_of(currency, fx)            # 1주당 원화 환율 배수(USD 만 fx, KRW 는 1.0)
    price_krw = price * rate               # 1주당 원화 가격
    if execution_plan is not None:
        try:
            execution_plan = json.loads(json.dumps(execution_plan, allow_nan=False))
            if side != "BUY" or not isinstance(execution_plan.get("signalId"), str) or not execution_plan["signalId"]:
                raise ValueError("invalid signal")
            stop, target = (_positive(execution_plan.get(k), k) for k in ("stop", "target"))
            if not stop < price < target:
                raise ValueError("invalid plan")
        except (ValueError, TypeError, AttributeError, SimError):
            raise SimError("차트 실행 계획을 확인하세요.") from None
    with _lock:
        st = _load()
        acc_id, acc = _acct(st, account)
        existing = acc["positions"].get(symbol)
        if existing and existing.get("currency", "KRW") != currency:
            raise SimError("보유 종목의 통화와 주문 통화가 다릅니다.")
        if execution_plan is not None and (existing or execution_plan["signalId"] in acc.get("chartSignals", {})):
            raise SimError("이미 보유 중이거나 사용한 차트 신호입니다.")
        realized = 0.0
        if side == "BUY":
            cost_krw = qty * price_krw
            fee_krw = cost_krw * FEE_RATE
            total_krw = cost_krw + fee_krw
            if total_krw > acc["cash"]:
                raise SimError(f"현금 부족 (필요 {int(total_krw):,}원, 보유 {int(acc['cash']):,}원)")
            acc["cash"] -= total_krw
            # 평단(원화)에는 매수 수수료까지 포함한 실제 원가(total_krw)를 반영한다.
            cost_basis_krw = total_krw         # 체결금액 + 매수수수료
            unit_cost_krw = cost_basis_krw / qty
            pos = acc["positions"].get(symbol)
            if pos:
                nq = pos["qty"] + qty
                pos["avgPrice"] = (pos["qty"] * pos["avgPrice"] + qty * price) / nq
                pos["avgPriceKrw"] = (pos["qty"] * pos.get("avgPriceKrw", pos["avgPrice"]) + cost_basis_krw) / nq
                pos["qty"] = nq
                if name:
                    pos["name"] = name
            else:
                acc["positions"][symbol] = {"qty": qty, "avgPrice": price, "avgPriceKrw": unit_cost_krw,
                                            "currency": currency, "name": name}
            if execution_plan is not None:
                acc["positions"][symbol]["executionPlan"] = copy.deepcopy(execution_plan)
                ledger = acc.setdefault("chartSignals", {})
                cutoff = time.time() - 14 * 86400  # Entry signals expire in four days.
                for key in [key for key, ts in ledger.items() if ts < cutoff]:
                    del ledger[key]
                ledger[execution_plan["signalId"]] = int(time.time())
        elif side == "SELL":
            pos = acc["positions"].get(symbol)
            if not pos or pos["qty"] < qty:
                raise SimError(f"보유 수량 부족 (보유 {pos['qty'] if pos else 0}주)")
            proceeds_krw = qty * price_krw
            net_krw = proceeds_krw - proceeds_krw * (FEE_RATE + TAX_RATE)
            acc["cash"] += net_krw
            realized = (price_krw - pos.get("avgPriceKrw", pos["avgPrice"])) * qty - proceeds_krw * (FEE_RATE + TAX_RATE)
            acc["realizedPnl"] += realized
            pos["qty"] -= qty
            if pos["qty"] == 0:
                del acc["positions"][symbol]
        else:
            raise SimError("side는 BUY 또는 SELL 이어야 합니다.")
        acc["history"].append({"ts": int(time.time()), "symbol": symbol, "name": name, "currency": currency,
                               "side": side, "qty": qty, "price": round(price, 2), "realized": round(realized),
                               "note": str(note or "")})
        if execution_plan is not None:
            acc["history"][-1]["executionPlan"] = copy.deepcopy(execution_plan)
        # 히스토리 무한 증가 방지 — 계좌당 최근 HISTORY_MAX 건만 유지(오래된 것부터 삭제).
        if len(acc["history"]) > HISTORY_MAX:
            del acc["history"][: len(acc["history"]) - HISTORY_MAX]
        _save(st)
        # 반환 상태는 보유 전 포지션을 통화별 환율로 평가해야 한다. 단일 fx 인자는
        # 'USD/KRW 환율'로 해석하되, KRW 주문(fx=1.0)이라 USD 환율 정보가 없을 땐
        # 보유 USD 포지션이 1.0 으로 잘못 평탄화되지 않도록 매수 평단의 내재 환율로 보정한다.
        # (acc 는 _load 캐시의 공유 객체일 수 있으므로 락 안에서 읽는다.)
        usd_fx = float(fx) if currency == "USD" else _infer_usd_fx(acc, fx)
    return get_state({symbol: price}, usd_fx, account=acc_id)


def _infer_usd_fx(acc, fx):
    # KRW 거래 등으로 USD/KRW 환율이 전달되지 않은(=1.0) 경우, 보유 USD 포지션의
    # 매수 평단에 내재된 환율(avgPriceKrw / avgPrice)을 추정 환율로 사용한다.
    # acc = 계좌 dict(positions 포함).
    if float(fx) != 1.0:
        return float(fx)
    for p in acc["positions"].values():
        if p.get("currency") == "USD":
            avg = p.get("avgPrice") or 0.0
            avg_krw = p.get("avgPriceKrw")
            if avg and avg_krw:
                return float(avg_krw) / float(avg)
    return float(fx)


def reset(cash=None, account=None):
    # 해당 계좌(기본 active)만 초기화. 계좌 이름은 유지한다.
    with _lock:
        st = _load()
        acc_id, acc = _acct(st, account)
        st["accounts"][acc_id] = _new(INITIAL_CASH if cash is None else cash,
                                      name=acc.get("name", "기본 계좌"))
        _save(st)
    return get_state(account=acc_id)


# ---------------- 멀티계좌 관리 API ----------------

def _slug(name):
    """계좌 id 용 안전 슬러그 — ASCII 영숫자만 남기고 소문자화. 비면 'acct'."""
    base = "".join(c for c in str(name).strip().lower() if c.isascii() and c.isalnum())
    return base or "acct"


def list_accounts():
    """{"active": id, "accounts":[{"id","name","createdAt","cash","initialCash",
       "positions": 보유 종목 수(int), "trades": 히스토리 수(int)}]}"""
    with _lock:
        st = _load()
        out = []
        for acc_id, acc in st["accounts"].items():
            out.append({
                "id": acc_id,
                "name": acc.get("name", acc_id),
                "createdAt": acc.get("createdAt", 0),
                "cash": round(acc.get("cash", 0)),
                "initialCash": round(acc.get("initialCash", 0)),
                "positions": len(acc.get("positions") or {}),
                "trades": len(acc.get("history") or []),
            })
        return {"active": st["active"], "accounts": out}


def create_account(name, cash=10_000_000):
    """새 계좌 생성 → 새 id 반환. id 는 이름의 안전 슬러그(중복 시 -2, -3 접미).

    이름이 공백이면 SimError, 계좌가 이미 8개면 SimError.
    """
    name = str(name or "").strip()
    if not name:
        raise SimError("계좌 이름을 입력하세요.")
    with _lock:
        st = _load()
        if len(st["accounts"]) >= MAX_ACCOUNTS:
            raise SimError(f"계좌는 최대 {MAX_ACCOUNTS}개까지 만들 수 있습니다.")
        base = _slug(name)
        new_id, n = base, 2
        while new_id in st["accounts"]:
            new_id = f"{base}-{n}"
            n += 1
        st["accounts"][new_id] = _new(float(cash), name=name)
        _save(st)
    return new_id


def delete_account(acc_id):
    """계좌 삭제. 없거나 마지막 남은 계좌면 SimError. active 삭제 시 남은 첫 계좌로 전환."""
    with _lock:
        st = _load()
        if acc_id not in st["accounts"]:
            raise SimError(f"계좌를 찾을 수 없습니다: {acc_id}")
        if len(st["accounts"]) <= 1:
            raise SimError("마지막 계좌는 삭제할 수 없습니다.")
        del st["accounts"][acc_id]
        if st["active"] == acc_id:
            st["active"] = next(iter(st["accounts"]))  # 남은 첫 계좌로 자동 전환
        _save(st)


def select_account(acc_id):
    """활성 계좌 전환 → id 반환. 없으면 SimError."""
    with _lock:
        st = _load()
        if acc_id not in st["accounts"]:
            raise SimError(f"계좌를 찾을 수 없습니다: {acc_id}")
        st["active"] = acc_id
        _save(st)
    return acc_id


def active_account():
    """현재 활성 계좌 id."""
    with _lock:
        return _load()["active"]
