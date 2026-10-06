"""Local UI verification server. Uses synthetic quotes and an isolated ledger."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL", "KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT", "ACCESS_TOKEN"):
    os.environ[key] = ""
os.environ["TOSS_CLIENT_ID"] = "offline-fixture"
os.environ["TOSS_CLIENT_SECRET"] = "offline-fixture"
os.environ["TOSS_DRY_RUN"] = "1"
os.environ["TOSSBOT_DATA_DIR"] = tempfile.mkdtemp(prefix="tossbot-ui-")

import urllib.request
urllib.request.urlopen = Mock(side_effect=AssertionError("External network disabled"))
from selftest import gen_candles
import server.app as module


class Market:
    dry_run = True

    def candles(self, symbol, interval="1d", count=200, **kwargs):
        from datetime import datetime, timedelta, timezone
        rows = gen_candles(count, start=50000 if symbol.isdigit() else 1000, seed=2)
        latest = datetime(2026, 10, 2, 15, 30, tzinfo=timezone(timedelta(hours=9)))
        for i, row in enumerate(rows):
            step = timedelta(minutes=i) if interval == "1m" else timedelta(days=i)
            row["timestamp"] = (latest - step).isoformat()
            row["currency"] = "KRW" if symbol.isdigit() else "USD"
        return {"candles": rows}

    def prices(self, symbols):
        return [{"symbol": s, "lastPrice": self.candles(s)["candles"][0]["closePrice"], "currency": "KRW" if s.isdigit() else "USD"} for s in symbols]

    def orderbook(self, symbol):
        return {"bids": [{"volume": "2000"}], "asks": [{"volume": "1500"}]}

    def stocks(self, symbols):
        return [{"symbol": s, "name": s, "market": "US"} for s in symbols]

    def exchange_rate(self, *args):
        return 1300


module._client = Market()
module._public_ip = lambda: None
module.secrets_store.status = lambda: {"available": True, "has_id": False, "has_secret": False}
module.secrets_store.save = Mock()
module.regimemod.get_regime = lambda client: {"stage": "STABLE", "score": 10, "emoji": "🔵", "guidance": "Synthetic QA data", "components": [{"key": key, "value": 10} for key in ("vix", "vvix", "spx", "tlt", "uup", "hyg")]}
module.autopilot.notify.send = Mock()
module.newsmod.fetch_news = lambda: {"items": [], "generatedAt": "2026-10-03"}
module.calendar_feed.get_calendar = lambda days=7: {"earnings": [], "econ": [], "generatedAt": "2026-10-03"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(module.app, host="127.0.0.1", port=args.port, log_level="warning")
