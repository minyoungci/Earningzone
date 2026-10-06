#!/usr/bin/env python3
"""tossbot 실행기 — 토스증권 KOSPI 분석/스크리너/인트라데이/페이퍼트레이딩.

사용법 (키는 환경변수로만 주입):
  export TOSS_CLIENT_ID=tsck_live_xxx   TOSS_CLIENT_SECRET=tssk_live_xxx

  python run.py --once               # 워치리스트 1회 분석
  python run.py                      # 실시간 루프(기본 30초)
  python run.py --symbols 005930,000660
  python run.py --screen             # KOSPI 유니버스 스크리너 랭킹
  python run.py --intraday --once    # 인트라데이(분봉) 1회   (루프: --intraday)
  python run.py --paper --once       # 페이퍼 트레이딩 1사이클 (루프: --paper)

DRY_RUN 기본 ON: 주문은 내지 않고 분석/시그널/페이퍼만 동작합니다.
"""
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지
except Exception:
    pass

from tossbot import config
from tossbot.client import TossClient
from tossbot.engine import run_loop, run_once


def main():
    ap = argparse.ArgumentParser(description="토스증권 KOSPI 분석/트레이딩 엔진")
    ap.add_argument("--once", action="store_true", help="1회만 실행하고 종료")
    ap.add_argument("--interval", type=int, default=config.POLL_INTERVAL_SEC, help="루프 간격(초)")
    ap.add_argument("--symbols", type=str, default="", help="콤마 구분 심볼(임시 워치리스트)")
    ap.add_argument("--screen", action="store_true", help="KOSPI 유니버스 스크리너 랭킹")
    ap.add_argument("--intraday", action="store_true", help="인트라데이(분봉) 모드")
    ap.add_argument("--paper", action="store_true", help="페이퍼 트레이딩(DRY_RUN)")
    args = ap.parse_args()

    watchlist = None
    if args.symbols:
        watchlist = [(s.strip(), s.strip()) for s in args.symbols.split(",") if s.strip()]

    try:
        client = TossClient()
    except RuntimeError as e:
        print(f"[설정 오류] {e}", file=sys.stderr)
        sys.exit(2)

    if args.screen:
        from tossbot.screener import run_screener
        run_screener(client)
    elif args.intraday:
        from tossbot.intraday import run_intraday
        run_intraday(client, watchlist, loop_sec=(None if args.once else args.interval))
    elif args.paper:
        from tossbot.trader import run_paper
        run_paper(client, watchlist, interval=args.interval, loop=(not args.once))
    elif args.once:
        run_once(client, watchlist)
    else:
        run_loop(client, watchlist, args.interval)


if __name__ == "__main__":
    main()
