"""인트라데이(분봉) 리포트 — 세션 VWAP·오프닝 레인지(ORB)·분봉 시그널.

워치리스트를 1분봉으로 분석하고, 세션 VWAP과 첫 OPENING_RANGE_MIN개 분봉의
고/저(오프닝 레인지)를 직접 계산해 종목별 인트라데이 상황을 출력합니다.

  python -m tossbot.intraday --once      # 1회 실행
  python -m tossbot.intraday --loop      # 반복(루프)

⚠️ DRY_RUN(기본)에서는 주문을 내지 않고 분석/시그널만 출력합니다.
산출 시그널은 교육용 휴리스틱이며 투자 권유가 아닙니다.
"""
from __future__ import annotations
import sys
import time

from . import config
from .analysis import analyze
from .client import TossAPIError, TossClient

# 분봉 전략을 별도 레지스트리에 로드한다(일봉 전략은 유지).
# (strategies/__init__.py 는 수정하지 않으므로 여기서 명시적으로 로드)
try:
    from .strategies import intraday as _intraday_strats  # noqa: F401
except Exception:
    _intraday_strats = None

MARK = {"BUY": "🟢 BUY ", "SELL": "🔴 SELL", "HOLD": "⚪ HOLD"}


def _m(v, nd=0):
    return f"{v:,.{nd}f}" if v is not None else "-"


def _p(v, nd=2):
    return f"{v:+.{nd}f}%" if v is not None else "-"


def _session_vwap(highs, lows, closes, vols):
    """세션 전체(전달된 분봉 전체) 누적 VWAP. 거래량 0 이면 None."""
    if not closes:
        return None
    num = den = 0.0
    for i in range(len(closes)):
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        v = vols[i] if i < len(vols) else 0.0
        num += tp * v
        den += v
    return num / den if den else None


def _opening_range(highs, lows, n):
    """첫 n개 분봉의 고/저(오프닝 레인지). 데이터 부족 시 가능한 만큼 사용."""
    if not highs or not lows:
        return None
    k = min(n, len(highs))
    if k <= 0:
        return None
    return {"high": max(highs[:k]), "low": min(lows[:k]), "bars": k}


def _intraday_report(a):
    """한 종목의 분봉 분석 결과(a=Features dict)를 인트라데이 관점으로 출력."""
    highs = a.get("highs") or []
    lows = a.get("lows") or []
    closes = a.get("closes") or []
    vols = a.get("volumes") or []
    price = a.get("price")
    agg = a.get("aggregate", {}) or {}
    action = agg.get("action", "HOLD")

    svwap = _session_vwap(highs, lows, closes, vols)
    orange = _opening_range(highs, lows, config.OPENING_RANGE_MIN)

    # 현재가 vs 세션 VWAP
    if svwap and price is not None:
        dev = (price - svwap) / svwap * 100.0
        vwap_side = "위" if price >= svwap else "아래"
        vwap_str = f"{_m(svwap)} ({vwap_side} {_p(dev)})"
    else:
        vwap_str = "-"

    # 오프닝 레인지 돌파(ORB) 판정
    orb = "-"
    if orange and price is not None:
        if price > orange["high"]:
            orb = f"상단돌파 ▲ (OR고 {_m(orange['high'])})"
        elif price < orange["low"]:
            orb = f"하단이탈 ▼ (OR저 {_m(orange['low'])})"
        else:
            orb = f"레인지 내 ({_m(orange['low'])}~{_m(orange['high'])})"

    print(f"■ {a['symbol']} {a.get('name','')}  {_m(price)}{a.get('currency','')}  "
          f"{MARK.get(action, action)}  종합 {agg.get('total', 0.0):+.1f}")
    print(f"    세션VWAP │ {vwap_str}")
    print(f"    오프닝레인지 │ {orb}  (첫 {orange['bars'] if orange else 0}봉)")

    sigs = a.get("signals", []) or []
    buys = sorted([s for s in sigs if s.action == "BUY"], key=lambda s: -s.strength)
    sells = sorted([s for s in sigs if s.action == "SELL"], key=lambda s: -s.strength)
    if buys:
        print("    ▶ 매수: " + " · ".join(s.name for s in buys[:6]))
    if sells:
        print("    ▷ 매도: " + " · ".join(s.name for s in sells[:6]))
    if not buys and not sells:
        print("    · 활성 분봉 시그널 없음")
    print()


def run_intraday(client=None, watchlist=None, interval=None, loop_sec=None):
    """인트라데이 분봉 리포트.

    loop_sec 가 주어지면 그 간격으로 무한 반복, 없으면 1회만 실행.
    interval 은 분석에 사용할 캔들 간격(기본 config.INTRADAY_INTERVAL='1m').
    """
    client = client or TossClient()
    wl = watchlist or config.WATCHLIST
    interval = interval or config.INTRADAY_INTERVAL
    syms = [s for s, _ in wl]
    names = {s: n for s, n in wl}

    def _cycle():
        prices = {}
        note = ""
        try:
            for p in client.prices(syms):
                prices[p["symbol"]] = p.get("lastPrice")
        except TossAPIError as e:
            note = f"현재가실패({e.code})"

        print("=" * 88)
        print(f"  토스증권 인트라데이 리포트  |  {len(syms)}종목  |  {interval}봉×{config.INTRADAY_COUNT}  |  "
              f"ORB={config.OPENING_RANGE_MIN}분  |  DRY_RUN={'ON' if client.dry_run else 'OFF(실주문!)'}"
              + (f"  |  {note}" if note else ""))
        print("=" * 88)

        rows = []
        for s in syms:
            try:
                a = analyze(client, s, names.get(s, ""), interval=interval,
                            count=config.INTRADAY_COUNT, last_price=prices.get(s))
            except TossAPIError as e:
                a = {"symbol": s, "name": names.get(s, ""), "error": e.code}
            if a.get("error"):
                print(f"■ {s} {names.get(s,'')}  ⚠️ {a['error']}\n")
                rows.append(a)
                continue
            _intraday_report(a)
            rows.append(a)

        ok = [r for r in rows if not r.get("error")]
        ranked = sorted(ok, key=lambda r: r.get("aggregate", {}).get("total", 0.0), reverse=True)
        if ranked:
            print("-" * 88)
            print("  분봉 종합 랭킹:")
            for r in ranked:
                agg = r.get("aggregate", {}) or {}
                print(f"    {MARK.get(agg.get('action','HOLD'))} {agg.get('total', 0.0):+5.1f}  "
                      f"{r['symbol']} {r.get('name','')}")
        if not client.dry_run:
            print("  ⚠️  DRY_RUN=OFF — 실주문 모드. 가드/한도 확인 필수.")
        print()
        return rows

    if loop_sec:
        print(f"[intraday] 루프 시작 — {loop_sec}초 간격 (Ctrl+C 종료)")
        try:
            while True:
                _cycle()
                time.sleep(loop_sec)
        except KeyboardInterrupt:
            print("\n[intraday] 종료되었습니다.")
            return None
    return _cycle()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    loop = "--loop" in argv
    loop_sec = config.POLL_INTERVAL_SEC if loop else None
    try:
        run_intraday(loop_sec=loop_sec)
    except RuntimeError as e:
        print(f"[intraday] 설정 오류: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
