"""오프라인 셀프테스트 — 합성 캔들로 분석 엔진/전략/출력 전체를 API 없이 검증."""
import sys
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parent))

import random
from tossbot import engine


def gen_candles(n=200, start=50000, trend=0.001, vol=0.015, seed=1):
    random.seed(seed)
    closes = [float(start)]
    for _ in range(1, n):
        closes.append(max(1000.0, closes[-1] * (1 + trend + random.gauss(0, vol))))
    out = []
    for i in range(n):
        c = closes[i]
        o = closes[i - 1] if i > 0 else c
        hi = max(o, c) * (1 + abs(random.gauss(0, vol / 2)))
        lo = min(o, c) * (1 - abs(random.gauss(0, vol / 2)))
        out.append({"openPrice": str(round(o)), "highPrice": str(round(hi)),
                    "lowPrice": str(round(lo)), "closePrice": str(round(c)),
                    "volume": str(round(random.uniform(1e6, 5e6))), "currency": "KRW"})
    out.reverse()  # API는 최신→과거 순
    return out


class FakeClient:
    dry_run = True

    def __init__(self):
        self.data = {
            "TST001": gen_candles(seed=1, trend=0.0014, start=60000),
            "TST002": gen_candles(seed=7, trend=-0.0010, start=120000),
            "TST003": gen_candles(seed=3, trend=0.0001, start=200000, vol=0.022),
        }

    def market_calendar(self, country):
        return {"today": {"date": "2026-06-22", "integrated": None}}

    def prices(self, syms):
        return [{"symbol": s, "lastPrice": self.data[s][0]["closePrice"]} for s in syms]

    def candles(self, symbol, interval="1d", count=200, **k):
        return {"candles": self.data[symbol][:count], "nextBefore": None}

    def orderbook(self, symbol):
        c = float(self.data[symbol][0]["closePrice"])
        return {"bids": [{"price": str(c * 0.999), "volume": "8000"},
                         {"price": str(c * 0.998), "volume": "6000"}],
                "asks": [{"price": str(c * 1.001), "volume": "3000"},
                         {"price": str(c * 1.002), "volume": "2000"}]}


if __name__ == "__main__":
    print("※ 오프라인 셀프테스트 (합성 데이터, API 미사용)\n")
    engine.run_once(FakeClient(), [("TST001", "합성상승"), ("TST002", "합성하락"), ("TST003", "합성변동")])
