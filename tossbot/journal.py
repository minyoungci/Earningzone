"""매매 저널 — 모의투자(sim) 히스토리 기반 통계. 실거래 아님(교육용).

sim 의 저장 구조(.sim_state.json):
  history 항목 = {"ts","symbol","name","currency","side","qty","price","realized","note"}
  - realized 는 SELL 체결 시점에 원화(KRW)로 계산·저장된 실현손익(수수료·거래세 차감 후, 반올림).
    BUY 항목은 realized=0 이므로 통계는 반드시 side=="SELL" 로만 집계한다.
  - price 는 종목 통화(native) 단가. USD 종목이면 달러, KRW 종목이면 원.

통계 정의(계산 방식):
  - 트레이드 1건 = SELL 체결 1건(부분 매도도 각각 1건으로 센다).
  - wins = realized > 0, losses = realized < 0 (본전 realized==0 은 어느 쪽에도 안 센다).
  - winRate = wins / trades * 100 (%).
  - profitFactor = (이익 트레이드 realized 합) / |손실 트레이드 realized 합|.
    손실이 하나도 없으면 무한대이므로 None 으로 반환(트레이드 자체가 없으면 0.0).
  - expectancyR(기대값 R) = 트레이드별 R 의 평균(근사).
      R_i = realized_i / 투입원금_i
      투입원금 근사 = 매도대금(KRW) - realized  (매도대금 ≈ 매수원가 + 실현손익. 매도
      수수료·세금은 realized 에 이미 차감돼 있어 근사 오차는 수수료 수준으로 작다.)
      매도대금(KRW) = qty * price * 환율 — KRW 종목은 환율 1.0, USD 종목은 현재 보유 중인
      USD 포지션의 평단 내재 환율(avgPriceKrw / avgPrice)로 추정한다. 추정이 불가능한
      USD 트레이드(보유 USD 포지션 없음)는 R 평균에서 제외한다(왜곡 방지).
  - avgWinKrw = 이익 트레이드 평균 실현손익(원, 양수), avgLossKrw = 손실 트레이드 평균(원, 음수).
  - totalRealizedKrw = 히스토리 SELL realized 합(원).
"""
from __future__ import annotations
import time as _time

from . import sim


def _infer_usd_fx(st):
    """보유 USD 포지션의 평단(원화/달러)에서 USD/KRW 환율을 추정. 불가 시 None."""
    for p in (st.get("positions") or {}).values():
        if p.get("currency") == "USD":
            avg = p.get("avgPrice") or 0.0
            avg_krw = p.get("avgPriceKrw")
            if avg and avg_krw:
                return float(avg_krw) / float(avg)
    return None


def _fmt_time(ts):
    """epoch → 'MM-DD HH:MM' (로컬 시각). ts 없으면 ''."""
    try:
        return _time.strftime("%m-%d %H:%M", _time.localtime(int(ts)))
    except Exception:
        return ""


def stats(account=None):
    """sim 히스토리 기반 매매 저널 통계 — 해당 계좌(기본 active)의 히스토리만 집계.

    account: 계좌 id(None 이면 active 계좌). 없는 id 면 SimError.
    반환: {"trades","wins","losses","winRate","profitFactor","expectancyR",
           "avgWinKrw","avgLossKrw","totalRealizedKrw","recent"}
    """
    with sim._lock:
        full = sim._load()
        _, st = sim._acct(full, account)  # st = 해당 계좌 dict(v1 과 동일 구조)
        # _load 는 파싱 캐시(공유 객체)를 반환할 수 있으므로 락 안에서 필요한 값만
        # 복사해 나온다. 히스토리 항목 dict 는 append 이후 불변이라 얕은 복사로 충분.
        history = list(st.get("history") or [])
        usd_fx = _infer_usd_fx(st)        # USD 매도대금의 원화 환산용(추정 환율)

    sells = [h for h in history if h.get("side") == "SELL"]
    trades = len(sells)
    win_amts = [float(h.get("realized") or 0) for h in sells if float(h.get("realized") or 0) > 0]
    loss_amts = [float(h.get("realized") or 0) for h in sells if float(h.get("realized") or 0) < 0]
    wins, losses = len(win_amts), len(loss_amts)

    gross_profit = sum(win_amts)          # 이익 합(원)
    gross_loss = -sum(loss_amts)          # 손실 합의 절댓값(원)
    total_realized = sum(float(h.get("realized") or 0) for h in sells)

    # profitFactor: 손실 0건이면 무한대 → None (트레이드가 아예 없으면 0.0)
    if trades == 0:
        profit_factor = 0.0
    elif gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    else:
        profit_factor = None

    # expectancyR: R_i = realized / (매도대금KRW - realized) — 상단 모듈 주석의 근사식.
    r_values = []
    for h in sells:
        realized = float(h.get("realized") or 0)
        qty = float(h.get("qty") or 0)
        price = float(h.get("price") or 0)
        ccy = h.get("currency", "KRW")
        if ccy == "USD":
            if not usd_fx:
                continue                  # 환율 추정 불가 → 이 트레이드는 R 평균에서 제외
            rate = usd_fx
        else:
            rate = 1.0
        proceeds_krw = qty * price * rate # 매도대금(원, 근사)
        invested = proceeds_krw - realized  # 투입원금 근사 = 매도대금 - 실현손익
        if invested > 0:
            r_values.append(realized / invested)
    expectancy_r = round(sum(r_values) / len(r_values), 4) if r_values else 0.0

    # 최근 10건(최신순) — BUY/SELL 모두 포함, note 동반. realized 는 SELL 에만 넣는다.
    recent = []
    for h in reversed(history[-10:]):
        item = {
            "time": _fmt_time(h.get("ts")),
            "symbol": h.get("symbol", ""),
            "name": h.get("name", ""),
            "side": h.get("side", ""),
            "qty": h.get("qty", 0),
            "price": h.get("price", 0),
            "currency": h.get("currency", "KRW"),
            "note": h.get("note", ""),
        }
        if h.get("side") == "SELL":
            item["realized"] = h.get("realized", 0)
        recent.append(item)

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "winRate": round(wins / trades * 100, 1) if trades else 0.0,
        "profitFactor": profit_factor,
        "expectancyR": expectancy_r,
        "avgWinKrw": round(gross_profit / wins) if wins else 0,
        "avgLossKrw": round(-gross_loss / losses) if losses else 0,
        "totalRealizedKrw": round(total_realized),
        "recent": recent,
    }
