"""토스증권 Open API 클라이언트 — 표준 라이브러리만 사용.

기능: OAuth2 토큰 자동발급/갱신, 그룹별 레이트리미터, 429 백오프, 에러 envelope 파싱,
      시세·종목·시장·계좌·자산 조회, (DRY_RUN 가드된) 주문.
"""
from __future__ import annotations
import base64
import json
import math
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import config

# 토스 엣지(WAF)가 기본 'Python-urllib' UA를 403으로 차단하므로 명시적 UA 사용.
USER_AGENT = "tossbot/0.1.0"


class TossAPIError(Exception):
    def __init__(self, status, code, message, data=None):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.data = data


class RateLimiter:
    """그룹별 최소 호출 간격(초)을 강제하는 스레드 안전 간이 리미터.

    FastAPI 동기 핸들러(스레드풀)에서 공유 전역 클라이언트로 쓰이므로
    상태 접근을 Lock 으로 보호한다. 락은 '그룹별'로 분리 — 락을 잡은 채
    sleep 해 같은 그룹은 직렬화(간격 보장)하되, 다른 그룹(예: 차트 스캔 중
    현재가 조회)은 서로 블로킹하지 않는다. 그룹 락 dict 갱신은 _guard 보호.
    """
    MIN = {
        "AUTH": 0.21, "ACCOUNT": 1.05, "ASSET": 0.21, "STOCK": 0.21,
        "MARKET_INFO": 0.34, "MARKET_DATA": 0.11, "MARKET_DATA_CHART": 0.21,
        "ORDER": 0.18, "ORDER_HISTORY": 0.21, "ORDER_INFO": 0.18,
    }

    def __init__(self):
        self._last = {}
        self._guard = threading.Lock()
        self._locks = {}

    def _group_lock(self, group):
        with self._guard:
            lk = self._locks.get(group)
            if lk is None:
                lk = self._locks[group] = threading.Lock()
            return lk

    def acquire(self, group):
        mn = self.MIN.get(group, 0.25)
        # 그룹 락 안에서 대기시간 계산→sleep→타임스탬프 갱신을 원자적으로 수행.
        with self._group_lock(group):
            wait = mn - (time.monotonic() - self._last.get(group, 0.0))
            if wait > 0:
                time.sleep(wait)
            self._last[group] = time.monotonic()


class TossClient:
    def __init__(self, client_id=None, client_secret=None, dry_run=None):
        self.cid = client_id or config.CLIENT_ID
        self.csec = client_secret or config.CLIENT_SECRET
        if not self.cid or not self.csec:
            raise RuntimeError(
                "TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 환경변수를 설정하세요 "
                "(키는 코드/파일에 저장하지 마세요)."
            )
        self.dry_run = config.DRY_RUN if dry_run is None else dry_run
        self.rate = RateLimiter()
        self._token = None
        self._exp = 0.0
        self._account_seq = None
        # 토큰 재발급(self._token/self._exp) 동시 접근 보호용 락.
        self._token_lock = threading.Lock()

    # ── 토큰 ──────────────────────────────────────────────
    def _issue_token(self):
        self.rate.acquire("AUTH")
        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        basic = base64.b64encode(f"{self.cid}:{self.csec}".encode()).decode()
        req = urllib.request.Request(
            config.BASE_URL + "/oauth2/token", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Authorization": "Basic " + basic,
                     "User-Agent": USER_AGENT, "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.load(r)
        self._token = j["access_token"]
        # client당 토큰 1개·만료 24h. 만료 60초 전부터 재발급.
        self._exp = time.time() + int(j.get("expires_in", 3600)) - 60

    def token(self):
        # 더블체크 락킹: 락 밖 빠른 경로 → 락 안 만료 재확인으로 중복 발급 방지.
        if self._token and time.time() < self._exp:
            return self._token
        with self._token_lock:
            if not self._token or time.time() >= self._exp:
                self._issue_token()
            return self._token

    # ── 공통 요청 ─────────────────────────────────────────
    # 429 백오프: min(cap, base*2**n)+지터 산식 파라미터.
    _BACKOFF_BASE = 0.5   # 1차 재시도 기준 대기(초)
    _BACKOFF_CAP = 8.0    # 지수 증가 상한(초)
    _BACKOFF_JITTER = 0.25  # 지터 최대치(초)

    def _request(self, method, path, group, params=None, body=None, account=False,
                 _retry=2, _retry429=None, _retry401=None):
        # 429/401 재시도 예산을 분리해 서로 소진하지 않게 한다.
        # _retry 는 하위호환용 시드값(둘 다 미지정 시 사용).
        if _retry429 is None:
            _retry429 = _retry
        if _retry401 is None:
            _retry401 = _retry
        self.rate.acquire(group)
        url = config.BASE_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": "Bearer " + self.token(),
                   "Accept": "application/json", "User-Agent": USER_AGENT}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if account:
            headers["X-Tossinvest-Account"] = str(self.account_seq())
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                payload = json.load(r)
            return payload.get("result", payload)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(raw).get("error", {}) or {}
            except Exception:
                err = {}
            code = err.get("code", "unknown")
            msg = err.get("message", raw[:200])
            if e.code == 429 and _retry429 > 0:
                # 소진된 횟수(이미 쓴 재시도 n) 기준으로 지수 백오프 산출.
                n = _retry - _retry429
                ra = e.headers.get("Retry-After")
                if ra is not None:
                    # Retry-After 헤더가 오면 그 값을 우선 사용.
                    try:
                        delay = float(ra)
                        delay = min(self._BACKOFF_CAP, max(delay, 0.0)) if math.isfinite(delay) else self._BACKOFF_BASE
                    except (TypeError, ValueError):
                        delay = self._BACKOFF_BASE
                else:
                    # 지수 + 소량 지터: min(cap, base*2**n) + random 지터.
                    delay = min(self._BACKOFF_CAP, self._BACKOFF_BASE * (2 ** n))
                    delay += random.uniform(0, self._BACKOFF_JITTER)
                time.sleep(delay)
                return self._request(method, path, group, params, body, account,
                                     _retry, _retry429 - 1, _retry401)
            if e.code == 401 and _retry401 > 0 and code in ("invalid-token", "expired-token", "edge-blocked"):
                self._token = None
                return self._request(method, path, group, params, body, account,
                                     _retry, _retry429, _retry401 - 1)
            raise TossAPIError(e.code, code, msg, err.get("data"))

    # ── 시세 (토큰만) ─────────────────────────────────────
    def prices(self, symbols):
        return self._request("GET", "/api/v1/prices", "MARKET_DATA", {"symbols": ",".join(symbols)})

    def orderbook(self, symbol):
        return self._request("GET", "/api/v1/orderbook", "MARKET_DATA", {"symbol": symbol})

    def trades(self, symbol, count=50):
        return self._request("GET", "/api/v1/trades", "MARKET_DATA", {"symbol": symbol, "count": count})

    def price_limits(self, symbol):
        return self._request("GET", "/api/v1/price-limits", "MARKET_DATA", {"symbol": symbol})

    def candles(self, symbol, interval="1d", count=120, before=None, adjusted=True):
        p = {"symbol": symbol, "interval": interval, "count": count, "adjusted": str(adjusted).lower()}
        if before:
            p["before"] = before
        return self._request("GET", "/api/v1/candles", "MARKET_DATA_CHART", p)

    # ── 종목/시장정보 ─────────────────────────────────────
    def stocks(self, symbols):
        return self._request("GET", "/api/v1/stocks", "STOCK", {"symbols": ",".join(symbols)})

    def market_calendar(self, country="KR"):
        return self._request("GET", f"/api/v1/market-calendar/{country}", "MARKET_INFO")

    def exchange_rate(self, base="USD", quote="KRW"):
        r = self._request("GET", "/api/v1/exchange-rate", "MARKET_INFO",
                          {"baseCurrency": base, "quoteCurrency": quote})
        try:
            return float(r.get("rate") or r.get("midRate"))
        except Exception:
            return None

    # ── 계좌/자산 (토큰 + 계좌 헤더) ──────────────────────
    def accounts(self):
        return self._request("GET", "/api/v1/accounts", "ACCOUNT")

    def account_seq(self):
        if self._account_seq is None:
            accs = self.accounts()
            if not accs:
                raise RuntimeError("조회된 BROKERAGE 계좌가 없습니다.")
            self._account_seq = accs[0]["accountSeq"]
        return self._account_seq

    def holdings(self):
        return self._request("GET", "/api/v1/holdings", "ASSET", account=True)

    def buying_power(self):
        return self._request("GET", "/api/v1/buying-power", "ORDER_INFO", account=True)

    def sellable_quantity(self, symbol):
        return self._request("GET", "/api/v1/sellable-quantity", "ORDER_INFO",
                             {"symbol": symbol}, account=True)

    # ── 주문 (DRY_RUN 가드) ───────────────────────────────
    def place_order(self, symbol, side, order_type, quantity=None, price=None,
                    order_amount=None, client_order_id=None, confirm_high_value=False):
        """매수/매도 주문. DRY_RUN=True 면 실제 전송하지 않고 '의도'만 반환."""
        body = {"symbol": symbol, "side": side, "orderType": order_type}
        if quantity is not None:
            body["quantity"] = str(quantity)
        if order_amount is not None:
            body["orderAmount"] = str(order_amount)
        if price is not None:
            body["price"] = str(price)
        # Retries of the same request must not create a second order.
        body["clientOrderId"] = client_order_id or str(uuid.uuid4())
        if confirm_high_value:
            body["confirmHighValueOrder"] = True
        if self.dry_run:
            return {"dryRun": True, "wouldSend": body}
        return self._request("POST", "/api/v1/orders", "ORDER", body=body, account=True)

    def cancel_order(self, order_id):
        if self.dry_run:
            return {"dryRun": True, "wouldCancel": order_id}
        return self._request("POST", f"/api/v1/orders/{order_id}/cancel", "ORDER", account=True)

    def order_detail(self, order_id):
        return self._request("GET", f"/api/v1/orders/{order_id}", "ORDER_HISTORY", account=True)

    def open_orders(self):
        return self._request("GET", "/api/v1/orders", "ORDER_HISTORY", {"status": "OPEN"}, account=True)
