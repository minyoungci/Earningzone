"""KOSPI 유니버스 스크리너 — 전 종목을 analyze()로 평가·종합점수 랭킹.

유니버스 전 종목을 analyze()로 돌려 종합점수(aggregate.total)로 정렬하고,
상위 BUY 후보·하위 SELL 후보를 콘솔 표로 출력합니다.
레이트리밋은 client가 처리하며, 현재가는 prices()로 배치 선조회해 last_price로 전달합니다.

⚠️ 산출되는 점수·랭킹은 교육용 휴리스틱이며 투자 권유가 아닙니다. (표준 라이브러리만 사용)
"""
from __future__ import annotations

from . import config
from .analysis import analyze
from .client import TossClient, TossAPIError


def _batch_prices(client, symbols, chunk=20):
    """prices()로 현재가를 배치 선조회 → {symbol: lastPrice}. 실패는 조용히 건너뜀."""
    out = {}
    if not client or not symbols:
        return out
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        try:
            rows = client.prices(part)
        except Exception as e:  # noqa: BLE001 - 배치 일부 실패 허용
            print(f"  [warn] 현재가 배치 조회 실패({part[0]}..): {e}")
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            sym = r.get("symbol")
            lp = r.get("lastPrice")
            if sym is None or lp is None:
                continue
            try:
                out[str(sym)] = float(lp)
            except (TypeError, ValueError):
                continue
    return out


def _fmt_price(v):
    if v is None:
        return "-"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def _print_table(title, rows):
    """rows: [{rank,symbol,name,action,total,price,nBuy,nSell}] → 콘솔 표."""
    print()
    print(title)
    print("-" * 78)
    print(f"{'#':>3} {'심볼':<8} {'종목명':<14} {'판정':<5} "
          f"{'점수':>8} {'현재가':>12} {'B/S':>7}")
    print("-" * 78)
    if not rows:
        print("  (해당 없음)")
        print("-" * 78)
        return
    for r in rows:
        # 한글 폭 보정: 종목명을 14칸 기준으로 단순 패딩
        name = r.get("name") or ""
        name_disp = name if len(name) <= 14 else name[:13] + "…"
        print(f"{r['rank']:>3} {r['symbol']:<8} {name_disp:<14} "
              f"{r['action']:<5} {r['total']:>+8.2f} {_fmt_price(r['price']):>12} "
              f"{str(r['nBuy']) + '/' + str(r['nSell']):>7}")
    print("-" * 78)


def run_screener(client=None, universe=None, top_n=None):
    """유니버스 전 종목을 평가해 종합점수로 정렬한 ranked list를 반환·출력.

    반환: [{symbol,name,total,action,price,nBuy,nSell,nSignals}, ...] (점수 내림차순)
    예외/TossAPIError(stock-not-found 등)는 건너뛰고 진행상황을 로그로 남깁니다.
    """
    if universe is None:
        universe = config.KOSPI_UNIVERSE
    if top_n is None:
        top_n = config.SCREENER_TOP_N
    if client is None:
        try:
            client = TossClient()
        except Exception as e:  # noqa: BLE001 - 자격증명 미설정 등
            print(f"[screener] 클라이언트 생성 실패: {e}")
            return []

    # 유니버스 정규화: (symbol, name) 튜플 또는 symbol 문자열 모두 허용
    norm = []
    for item in (universe or []):
        if isinstance(item, (list, tuple)):
            sym = str(item[0]) if len(item) >= 1 else None
            name = str(item[1]) if len(item) >= 2 else ""
        else:
            sym = str(item)
            name = ""
        if sym:
            norm.append((sym, name))

    total_n = len(norm)
    if total_n == 0:
        print("[screener] 유니버스가 비어 있습니다.")
        return []

    print(f"[screener] KOSPI 유니버스 {total_n}종목 스크리닝 시작 "
          f"(interval={config.CANDLE_INTERVAL}, count={config.CANDLE_COUNT})")

    # 현재가 배치 선조회 (analyze가 느리므로 last_price로 전달해 캔들 1콜만 사용)
    price_map = _batch_prices(client, [s for s, _ in norm])

    ranked = []
    skipped = 0
    for i, (sym, name) in enumerate(norm, 1):
        pct = i * 100.0 / total_n
        last_price = price_map.get(sym)
        try:
            feats = analyze(client, sym, name=name, last_price=last_price)
        except TossAPIError as e:
            skipped += 1
            print(f"[{i:>3}/{total_n}] ({pct:5.1f}%) {sym} {name} "
                  f"건너뜀: API오류 {e.code}")
            continue
        except Exception as e:  # noqa: BLE001 - 개별 종목 실패는 전체 중단 금지
            skipped += 1
            print(f"[{i:>3}/{total_n}] ({pct:5.1f}%) {sym} {name} "
                  f"건너뜀: {type(e).__name__}: {e}")
            continue

        if not feats or feats.get("error"):
            skipped += 1
            reason = (feats or {}).get("error", "데이터부족")
            print(f"[{i:>3}/{total_n}] ({pct:5.1f}%) {sym} {name} "
                  f"건너뜀: {reason}")
            continue

        agg = feats.get("aggregate") or {}
        price = feats.get("price")
        if price is None:
            price = last_price
        row = {
            "symbol": sym,
            "name": feats.get("name") or name,
            "total": float(agg.get("total", 0.0) or 0.0),
            "action": agg.get("action", "HOLD"),
            "price": price,
            "nBuy": int(agg.get("nBuy", 0) or 0),
            "nSell": int(agg.get("nSell", 0) or 0),
            "nSignals": len(feats.get("signals") or []),
        }
        ranked.append(row)
        print(f"[{i:>3}/{total_n}] ({pct:5.1f}%) {sym} {row['name']} "
              f"→ {row['action']} 점수 {row['total']:+.2f} "
              f"(B{row['nBuy']}/S{row['nSell']})")

    ranked.sort(key=lambda r: r["total"], reverse=True)

    print()
    print(f"[screener] 완료: 평가 {len(ranked)}종목 / 건너뜀 {skipped}종목")

    # 상위 BUY 후보 / 하위 SELL 후보 표
    top = []
    for idx, r in enumerate(ranked[:top_n], 1):
        top.append(dict(r, rank=idx))
    _print_table(f"▲ 상위 {len(top)}종목 (BUY 후보 — 종합점수 높은 순)", top)

    bottom_src = ranked[-top_n:] if len(ranked) > top_n else []
    bottom = []
    # 하위는 점수 낮은 순(가장 약한 종목이 위로)
    for idx, r in enumerate(sorted(bottom_src, key=lambda x: x["total"]), 1):
        bottom.append(dict(r, rank=idx))
    if bottom:
        _print_table(f"▼ 하위 {len(bottom)}종목 (SELL 후보 — 종합점수 낮은 순)", bottom)

    return ranked


if __name__ == "__main__":  # 수동 실행용 (DRY_RUN 기본)
    run_screener()
