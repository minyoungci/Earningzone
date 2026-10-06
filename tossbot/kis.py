"""한국투자증권 KIS Developers API 클라이언트 (표준 라이브러리만).

주문 실행 브로커 옵션 — 분석/데이터는 토스 기반을 공유하고, 이 모듈은 '주문 집행'만 담당.

안전 계층 (둘 다 기본 ON):
  1) config.DRY_RUN         — True 면 주문 API 를 아예 호출하지 않고 의도만 반환.
  2) config.KIS_PAPER (VTS) — True 면 KIS 모의투자 서버(openapivts, 가상계좌)로만 전송.
     실전 서버는 KIS_PAPER=0 을 명시해야만 사용된다.

키 발급: https://apiportal.koreainvestment.com (KIS Developers)
  - 앱키/앱시크릿 발급 + 모의투자 신청 → 환경변수 KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT("12345678-01")
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.request

from . import config

REAL_BASE = "https://openapi.koreainvestment.com:9443"
VTS_BASE = "https://openapivts.koreainvestment.com:29443"

# 국내주식 현금주문 tr_id — (매수, 매도)
TR_ORDER_REAL = ("TTTC0802U", "TTTC0801U")
TR_ORDER_VTS = ("VTTC0802U", "VTTC0801U")
# 잔고조회 tr_id
TR_BALANCE_REAL = "TTTC8434R"
TR_BALANCE_VTS = "VTTC8434R"
# 현재가 조회 tr_id (실전/모의 동일)
TR_PRICE = "FHKST01010100"


class KISError(RuntimeError):
    """KIS API 오류 (rt_cd != '0' 또는 HTTP 오류)."""

    def __init__(self, msg, code="", status=0):
        super().__init__(msg)
        self.code = code
        self.status = status


class KISClient:
    """최소 KIS 클라이언트: 토큰 캐시 + 현재가 + 현금주문 + 잔고."""

    def __init__(self, app_key=None, app_secret=None, account=None, paper=None):
        self.app_key = (app_key or config.KIS_APP_KEY).strip()
        self.app_secret = (app_secret or config.KIS_APP_SECRET).strip()
        acct = (account or config.KIS_ACCOUNT).strip()
        self.paper = config.KIS_PAPER if paper is None else bool(paper)
        self.base = VTS_BASE if self.paper else REAL_BASE
        # "12345678-01" → CANO / ACNT_PRDT_CD
        if "-" in acct:
            self.cano, self.acnt_prdt = acct.split("-", 1)
        else:
            self.cano, self.acnt_prdt = acct[:8], (acct[8:] or "01")
        self._token = None
        self._token_exp = 0.0
        self._last_call = 0.0
        self._request_lock = threading.Lock()
        self._token_lock = threading.Lock()

    # ── 설정 여부 ────────────────────────────────────────────
    def configured(self):
        return bool(self.app_key and self.app_secret and self.cano)

    # ── 저수준 HTTP ──────────────────────────────────────────
    def _http(self, method, path, headers=None, params=None, body=None, timeout=15):
        with self._request_lock:
            return self._http_locked(method, path, headers, params, body, timeout)

    def _http_locked(self, method, path, headers=None, params=None, body=None, timeout=15):
        # KIS 는 초당 호출 제한이 있어 최소 간격을 둔다(모의 2건/s, 실전 20건/s — 보수적으로 0.6s).
        wait = 0.6 - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = self.base + path
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json; charset=utf-8")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        self._last_call = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                detail = ""
            raise KISError(f"KIS HTTP {e.code}: {detail}", status=e.code)
        except urllib.error.URLError as e:
            raise KISError(f"KIS 연결 실패: {e.reason}")

    # ── 토큰 (24h 유효, 발급 빈도 제한 있어 캐시 필수) ─────────
    def token(self):
        with self._token_lock:
            return self._token_locked()

    def _token_locked(self):
        if self._token and time.time() < self._token_exp - 300:
            return self._token
        res = self._http("POST", "/oauth2/tokenP", body={
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        })
        tok = res.get("access_token")
        if not tok:
            raise KISError(f"토큰 발급 실패: {res.get('error_description') or res}", code=str(res.get("error_code", "")))
        self._token = tok
        self._token_exp = time.time() + float(res.get("expires_in", 86400))
        return tok

    def _auth_headers(self, tr_id):
        return {
            "authorization": f"Bearer {self.token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    @staticmethod
    def _check(res):
        # KIS 공통 응답: rt_cd=="0" 성공
        if str(res.get("rt_cd", "")) != "0":
            raise KISError(f"{res.get('msg1', 'KIS 오류')} ({res.get('msg_cd', '')})",
                           code=str(res.get("msg_cd", "")))
        return res

    # ── 현재가 ──────────────────────────────────────────────
    def price(self, symbol):
        """국내주식 현재가(원). 실패 시 KISError."""
        res = self._http("GET", "/uapi/domestic-stock/v1/quotations/inquire-price",
                         headers=self._auth_headers(TR_PRICE),
                         params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol})
        self._check(res)
        out = res.get("output") or {}
        return float(out.get("stck_prpr") or 0) or None

    # ── 현금 주문 (국내주식) ─────────────────────────────────
    def place_order(self, symbol, side, qty, price=None):
        """side: BUY|SELL. price 지정 시 지정가(00), 없으면 시장가(01).

        config.DRY_RUN 이면 API 호출 없이 의도만 반환한다(토스 브로커와 동일 계약).
        """
        side = str(side).upper()
        try:
            quantity = float(qty)
            valid_price = price is None or (math.isfinite(float(price)) and float(price) > 0)
        except (TypeError, ValueError, OverflowError):
            raise KISError("수량과 가격을 확인하세요") from None
        if (side not in ("BUY", "SELL") or not str(symbol).isdigit() or len(str(symbol)) != 6
                or isinstance(qty, bool) or not math.isfinite(quantity) or quantity <= 0
                or not quantity.is_integer() or not valid_price):
            raise KISError("국내 종목 코드·매매 방향·수량·가격을 확인하세요")
        if config.DRY_RUN:
            return {"dryRun": True, "broker": "kis", "paper": self.paper,
                    "wouldSend": {"symbol": symbol, "side": side, "qty": int(qty),
                                  "price": price, "server": "VTS" if self.paper else "REAL"}}
        buy_tr, sell_tr = TR_ORDER_VTS if self.paper else TR_ORDER_REAL
        tr_id = buy_tr if side == "BUY" else sell_tr
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt,
            "PDNO": symbol,
            "ORD_DVSN": "00" if price else "01",  # 00=지정가, 01=시장가
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": str(int(price)) if price else "0",
        }
        headers = self._auth_headers(tr_id)
        # 해시키(위·변조 방지) — 실패해도 주문 자체는 시도(현행 API는 선택 헤더)
        try:
            hres = self._http("POST", "/uapi/hashkey",
                              headers={"appkey": self.app_key, "appsecret": self.app_secret},
                              body=body)
            if hres.get("HASH"):
                headers["hashkey"] = hres["HASH"]
        except Exception:
            pass
        res = self._http("POST", "/uapi/domestic-stock/v1/trading/order-cash",
                         headers=headers, body=body)
        self._check(res)
        out = res.get("output") or {}
        return {"dryRun": False, "broker": "kis", "paper": self.paper,
                "orderNo": out.get("ODNO"), "raw": out}

    # ── 잔고 ────────────────────────────────────────────────
    def balance(self):
        tr = TR_BALANCE_VTS if self.paper else TR_BALANCE_REAL
        res = self._http("GET", "/uapi/domestic-stock/v1/trading/inquire-balance",
                         headers=self._auth_headers(tr),
                         params={
                             "CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt,
                             "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
                             "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                             "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                             "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
                         })
        self._check(res)
        return res
