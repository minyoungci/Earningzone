"""실시간 분석 엔진 — 워치리스트를 폴링하며 종목별 상세 분석/시그널 출력.

DRY_RUN(기본)에서는 주문을 내지 않고 분석/시그널만 출력합니다.
"""
from __future__ import annotations
import time

from . import config, strategies
from .analysis import analyze
from .client import TossAPIError, TossClient

MARK = {"BUY": "🟢 BUY ", "SELL": "🔴 SELL", "HOLD": "⚪ HOLD"}
STRUCT = {"uptrend": "상승추세", "downtrend": "하락추세", "range": "횡보"}


def _m(v, nd=0):
    return f"{v:,.{nd}f}" if v is not None else "-"


def _p(v, nd=1):
    return f"{v:+.{nd}f}%" if v is not None else "-"


def _print_detail(a):
    agg = a["aggregate"]
    lv = a["levels"]
    rsi, macd, st, adx = a.get("rsi"), a.get("macd"), a.get("stoch"), a.get("adx")
    cci, boll = a.get("cci"), a.get("boll")

    print(f"■ {a['symbol']} {a['name']}  {_m(a['price'])}{a['currency']}  "
          f"(D {_p(a['ret']['1'])} / 5D {_p(a['ret']['5'])} / 20D {_p(a['ret']['20'])})  "
          f"[{STRUCT.get(a['structure'], a['structure'])}]")
    print(f"    {MARK[agg['action']]} 종합점수 {agg['total']:+.1f}  "
          f"(매수 {agg['nBuy']} / 매도 {agg['nSell']} 전략)")

    di = ("+DI" if adx and adx["plusDI"] > adx["minusDI"] else "-DI") if adx else ""
    adx_v = _m(adx["adx"]) if adx else "-"
    macd_v = _p(macd["hist"], 0) if macd else "-"
    stoch_v = f"{_m(st['k'])}/{_m(st['d'])}" if st else "-"
    pctb_v = f"{boll['pctB']:.2f}" if boll else "-"
    print(f"    지표 │ ADX {adx_v}{di}  RSI {_m(rsi)}  MACD {macd_v}  "
          f"Stoch {stoch_v}  CCI {_m(cci)}  %b {pctb_v}  ATR {_p(a.get('atrPct'))}")
    print(f"    레벨 │ 지지 {_m(lv.get('nearestSupport'))} / 저항 {_m(lv.get('nearestResistance'))}  "
          f"52주 {(_m(lv.get('pos52')) + '%') if lv.get('pos52') is not None else '-'}  "
          f"이격도 {_m(a.get('disparity20'))}")

    dvg = a["divergence"]["summary"]
    cps = ", ".join(p["name"] for p in a["candlePatterns"]) or "-"
    chp = ", ".join(p["name"] for p in a["chartPatterns"]) or "-"
    print(f"    신호 │ 다이버전스 {dvg or '-'}  ·  캔들 {cps}  ·  차트 {chp}")

    buys = sorted([s for s in a["signals"] if s.action == "BUY"], key=lambda s: -s.strength)
    sells = sorted([s for s in a["signals"] if s.action == "SELL"], key=lambda s: -s.strength)
    if buys:
        print(f"    ▶ 매수 {len(buys)}: " + " · ".join(s.name for s in buys[:7]))
    if sells:
        print(f"    ▷ 매도 {len(sells)}: " + " · ".join(s.name for s in sells[:7]))
    print()


def run_once(client=None, watchlist=None):
    client = client or TossClient()
    wl = watchlist or config.WATCHLIST
    syms = [s for s, _ in wl]
    names = {s: n for s, n in wl}

    try:
        cal = client.market_calendar("KR")
        today = (cal or {}).get("today", {})
        note = "장중" if (today and today.get("integrated")) else "휴장/장외(일봉 기준)"
    except TossAPIError as e:
        note = f"캘린더실패({e.code})"

    prices = {}
    try:
        for p in client.prices(syms):
            prices[p["symbol"]] = p.get("lastPrice")
    except TossAPIError as e:
        note += f"/현재가실패({e.code})"

    n_strat = len(strategies.REGISTRY)
    print("=" * 92)
    print(f"  토스증권 KOSPI 분석엔진  |  {len(syms)}종목 × {n_strat}전략  |  {note}  |  "
          f"{config.CANDLE_INTERVAL}봉  |  DRY_RUN={'ON' if client.dry_run else 'OFF(실주문!)'}")
    print("=" * 92)

    rows = []
    for s in syms:
        try:
            a = analyze(client, s, names.get(s, ""), last_price=prices.get(s))
        except TossAPIError as e:
            a = {"symbol": s, "name": names.get(s, ""), "error": e.code}
        if a.get("error"):
            print(f"■ {s} {names.get(s,'')}  ⚠️ {a['error']}\n")
            rows.append(a)
            continue
        _print_detail(a)
        rows.append(a)

    # 랭킹 요약
    ranked = sorted([r for r in rows if not r.get("error")],
                    key=lambda r: r["aggregate"]["total"], reverse=True)
    print("-" * 92)
    print("  종합 랭킹 (점수순):")
    for r in ranked:
        agg = r["aggregate"]
        print(f"    {MARK[agg['action']]} {agg['total']:+5.1f}  {r['symbol']} {r['name']}  "
              f"(매수 {agg['nBuy']}/매도 {agg['nSell']})")
    buys = [r for r in ranked if r["aggregate"]["action"] == "BUY"]
    sells = [r for r in ranked if r["aggregate"]["action"] == "SELL"]
    print(f"  요약: BUY {len(buys)}  SELL {len(sells)}  HOLD {len(ranked)-len(buys)-len(sells)}")
    if not client.dry_run:
        print("  ⚠️  DRY_RUN=OFF — 실주문 모드. 가드/한도 확인 필수.")
    print()
    return rows


def run_loop(client=None, watchlist=None, interval=None):
    client = client or TossClient()
    interval = interval or config.POLL_INTERVAL_SEC
    print(f"[engine] 루프 시작 — {interval}초 간격 (Ctrl+C 종료)")
    try:
        while True:
            run_once(client, watchlist)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[engine] 종료되었습니다.")
