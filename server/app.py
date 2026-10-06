"""tossbot FastAPI 백엔드 — tossbot 분석엔진을 JSON API로 노출.

키(TOSS_CLIENT_ID/SECRET)는 이 서버 환경변수로만 주입되며, 프론트로 노출되지 않습니다.
실행: uvicorn server.app:app --port 8000  (D:/toss 에서)
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


from tossbot.environment import load_env

load_env(_ROOT)

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tossbot import autopilot
from tossbot import backtest as btmod
from tossbot import brokers
from tossbot import calendar_feed
from tossbot import config
from tossbot import journal
from tossbot import macro
from tossbot import news as newsmod
from tossbot import notify
from tossbot import options_flow
from tossbot import quant
from tossbot import regime as regimemod
from tossbot import secrets_store
from tossbot.analysis import analyze
from tossbot.client import TossAPIError, TossClient
from tossbot.cache import CacheBusy, TTLCache
from tossbot.strategies import REGISTRY

@asynccontextmanager
async def _lifespan(app):
    _start_telegram_bot()
    try:
        yield
    finally:
        await asyncio.to_thread(autopilot.stop)
        from tossbot import telegram_bot
        telegram_bot.stop_bot()


app = FastAPI(title="tossbot API", version="0.1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Access-Token"],
)

# ── 쓰기 토큰 게이트 (Cloudflare Tunnel 공개용) ─────────────────────
# env ACCESS_TOKEN 이 비어 있으면 게이트 OFF(로컬 개발 현행 동작 그대로).
# 설정돼 있으면 /api/* 의 POST/DELETE/PUT 은 토큰 소유자만 통과 — 열람(GET)은 누구나.
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "").strip()


def _req_token(request: Request) -> str:
    """요청에서 접근 토큰 추출 — 헤더 X-Access-Token 우선, 없으면 쿼리 ?token=."""
    return request.headers.get("X-Access-Token") or request.query_params.get("token") or ""


@app.middleware("http")
async def _write_gate(request: Request, call_next):
    # Prevent an unrelated website from controlling a local desktop session.
    if request.method in ("POST", "DELETE", "PUT", "PATCH") and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        own_origins = {f"http://{host}", f"https://{host}"}
        allowed = {o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()}
        if origin and origin not in own_origins and origin not in allowed and not re.fullmatch(r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?", origin):
            return JSONResponse(status_code=403, content={"detail": "허용되지 않은 요청 출처입니다"})
    # GET/HEAD/OPTIONS 와 정적(SPA) 경로는 항상 통과 — /api/* 의 쓰기 메서드만 검사
    if (ACCESS_TOKEN and request.url.path.startswith("/api/")
            and request.method in ("POST", "DELETE", "PUT", "PATCH")):
        # hmac.compare_digest — 타이밍 공격 방지 상수시간 비교.
        # bytes 로 인코딩해 비교: 비ASCII 토큰이 와도 TypeError(→500) 없이 401 처리.
        if not hmac.compare_digest(
                _req_token(request).encode("utf-8", "surrogateescape"),
                ACCESS_TOKEN.encode("utf-8")):
            return JSONResponse(status_code=401,
                                content={"detail": "컨트롤 권한이 없습니다 — 접근 토큰을 입력하세요"})
    return await call_next(request)


@app.get("/api/auth")
def auth_status(request: Request):
    """프론트 자물쇠 상태 표시용 — GET 이라 토큰 없이도 호출 가능.

    gate: ACCESS_TOKEN 설정 여부, ok: 게이트 OFF 이거나 요청 토큰이 유효.
    """
    tok = _req_token(request)
    ok = (not ACCESS_TOKEN) or hmac.compare_digest(
        tok.encode("utf-8", "surrogateescape"), ACCESS_TOKEN.encode("utf-8"))
    return {"gate": bool(ACCESS_TOKEN), "ok": ok}

_client = None
_client_lock = threading.RLock()
# Request results are bounded and concurrent callers share a single build.
_cache = TTLCache()
_HEAVY_PREFIXES = ("qt:", "screener")


def client() -> TossClient:
    global _client
    with _client_lock:
        if _client is None:
            if not (config.CLIENT_ID and config.CLIENT_SECRET):
                raise HTTPException(503, detail="토스 API 키를 먼저 설정하세요")
            _client = TossClient()
        return _client


def cached(key: str, ttl: float, fn):
    return _cache.get_or_create(key, ttl, fn, wait=not key.startswith(_HEAVY_PREFIXES))


@app.exception_handler(CacheBusy)
async def _cache_busy(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "15"})


@app.exception_handler(TossAPIError)
async def _upstream_api_error(request, exc):
    missing = exc.code == "stock-not-found"
    message = "종목을 찾을 수 없습니다" if missing else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요"
    return JSONResponse(status_code=404 if missing else 502, content={"detail": message})


@app.exception_handler(urllib.error.URLError)
async def _upstream_network_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": "토스 서버에 연결할 수 없습니다 — 연결 상태를 확인하세요"})


def _symbol(symbol):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-]{0,19}", symbol):
        raise HTTPException(400, detail="종목 코드를 확인하세요")
    return symbol.upper()


def _sig(s):
    return {"name": s.name, "category": s.category, "action": s.action,
            "strength": round(s.strength, 3), "reason": s.reason, "score": round(s.score, 3)}


def _summary(f):
    a = f["aggregate"]
    return {"symbol": f["symbol"], "name": f["name"], "price": f["price"], "currency": f["currency"],
            "ret": f["ret"], "structure": f["structure"], "rsi": f.get("rsi"),
            "action": a["action"], "score": round(a["total"], 2), "nBuy": a["nBuy"], "nSell": a["nSell"]}


def _full(f):
    a = f["aggregate"]
    macd = f.get("macd") or {}
    stoch = f.get("stoch") or {}
    adx = f.get("adx") or {}
    boll = f.get("boll") or {}
    return {
        "symbol": f["symbol"], "name": f["name"], "price": f["price"], "currency": f["currency"],
        "bars": f["bars"], "ret": f["ret"], "structure": f["structure"], "disparity20": f.get("disparity20"),
        "indicators": {
            "rsi": f.get("rsi"), "macdHist": macd.get("hist"), "stochK": stoch.get("k"), "stochD": stoch.get("d"),
            "adx": adx.get("adx"), "plusDI": adx.get("plusDI"), "minusDI": adx.get("minusDI"),
            "cci": f.get("cci"), "williamsR": f.get("williamsR"), "mfi": f.get("mfi"), "roc": f.get("roc"),
            "bollPctB": boll.get("pctB"), "atrPct": f.get("atrPct"), "obvSlope": f.get("obvSlope"),
            "volRatio": f.get("volRatio"), "vwap": f.get("vwap"),
            "sma5": f.get("sma5"), "sma20": f.get("sma20"), "sma60": f.get("sma60"), "sma120": f.get("sma120"),
        },
        "levels": f["levels"], "divergence": f["divergence"],
        "candlePatterns": f["candlePatterns"], "chartPatterns": f["chartPatterns"], "imbalance": f.get("imbalance"),
        "aggregate": {"total": round(a["total"], 2), "action": a["action"], "nBuy": a["nBuy"], "nSell": a["nSell"],
                      "buyW": round(a["buyW"], 2), "sellW": round(a["sellW"], 2)},
        "signals": [_sig(s) for s in f["signals"]],
        "strategyErrors": list(getattr(f["signals"], "errors", [])),
    }


@app.get("/api/health")
def health():
    return {"ok": True, "strategies": len(REGISTRY), "dryRun": config.DRY_RUN}


def _public_ip():
    """현재 공인 IP(허용 IP 등록 안내용). 실패 시 None."""
    import urllib.request
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as r:
            return r.read().decode("utf-8", "replace").strip() or None
    except Exception:
        return None


@app.get("/api/selftest")
def selftest():
    """토스 연결 자가진단 — 처음 실행하는 사람이 '키 오류' vs 'IP 미허용'을 즉시 구분하도록.

    stage: ok(연결 성공) | nokey(키 미설정) | auth(키 오류) | ip(IP 미허용) | api(그 외 API오류) | network(연결 실패)
    """
    def build():
        pub = None
        if not (config.CLIENT_ID and config.CLIENT_SECRET):
            return {"ok": False, "stage": "nokey", "publicIp": pub,
                    "message": "토스 Open API 키가 설정되지 않았습니다. .env 파일에 TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 을 입력하세요."}
        try:
            client().prices(["005930"])  # 토큰 발급 + 데이터 호출 1회로 인증·IP·네트워크 동시 점검
            return {"ok": True, "stage": "ok", "publicIp": pub, "message": "토스 연결 성공"}
        except Exception as e:  # noqa: BLE001 - 상태 코드로 분기해 사용자에게 정확한 안내
            # 토큰 발급(_issue_token)은 HTTPError 를, 데이터 호출은 TossAPIError 를 던진다.
            # 둘 다 HTTP 상태 코드를 갖고 있으므로(TossAPIError.status / HTTPError.code) 통일 처리.
            status = getattr(e, "status", None) or getattr(e, "code", None)
            if status == 403:
                pub = cached("public-ip", 600, _public_ip)
                return {"ok": False, "stage": "ip", "publicIp": pub,
                        "message": (f"허용되지 않은 IP입니다. 현재 공인 IP({pub or '확인 필요'})를 "
                                    "토스증권 개발자센터의 '허용 IP'에 추가한 뒤 다시 확인하세요.")}
            if status in (400, 401):
                return {"ok": False, "stage": "auth", "publicIp": pub,
                        "message": "키 인증에 실패했습니다. TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 을 다시 확인하세요."}
            if status is not None:
                return {"ok": False, "stage": "api", "publicIp": pub,
                        "message": f"토스 API 오류(HTTP {status}). 잠시 후 다시 시도하세요."}
            return {"ok": False, "stage": "network", "publicIp": pub,
                    "message": "네트워크 오류로 토스에 연결하지 못했습니다. 인터넷 연결을 확인하세요."}
    # 실패 상태가 매 폴링마다 외부 IP·토스를 때리지 않도록 20초 캐시(성공/실패 공통)
    return cached("selftest", 20, build)


@app.get("/api/watchlist")
def watchlist(market: str = "kr"):
    # market 화이트리스트: "us" 면 미국 감시목록(WATCHLIST_US), 그 외는 전부 kr 로 폴백
    if market != "us":
        market = "kr"
    wl = config.WATCHLIST_US if market == "us" else config.WATCHLIST

    def build():
        c = client()
        syms = [s for s, _ in wl]
        names = {s: n for s, n in wl}
        prices = {}
        try:
            for p in c.prices(syms):
                prices[p["symbol"]] = p.get("lastPrice")
        except TossAPIError:
            pass
        out = []
        for s in syms:
            try:
                f = analyze(c, s, names[s], last_price=prices.get(s))
                if not f.get("error"):
                    out.append(_summary(f))
            except Exception:
                pass
        return {"items": out, "generatedAt": int(time.time())}
    # 캐시 키를 시장별로 분리(kr/us). 기존 "watchlist" 단일 키는 kr 로 대체.
    return cached(f"watchlist:{market}", 30, build)


@app.get("/api/analyze/{symbol}")
def analyze_one(symbol: str, name: str = ""):
    symbol = _symbol(symbol)
    def build():
        try:
            f = analyze(client(), symbol, name)
        except TossAPIError as e:
            # 4xx(없는 종목 등) → 404, 그 외(서버/네트워크) → 502 로 매핑
            raise HTTPException(404 if e.code == "stock-not-found" else 502,
                                detail="종목을 찾을 수 없습니다" if e.code == "stock-not-found" else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요")
        if f.get("error"):
            raise HTTPException(404, detail=f["error"])
        return _full(f)
    return cached(f"an:{symbol}:{name}", 30, build)


# candles/analyze 가 허용하는 캔들 간격 화이트리스트(미스매치 시 1d 로 폴백).
# 토스 캔들 API 가 실제 지원하는 간격만 둔다(1d 일봉, 1m 분봉). 그 외(주봉·시간봉 등)는
# 토스가 404 를 내므로 화이트리스트에서 제외해 1d 로 우아하게 강등시킨다.
_VALID_INTERVALS = {"1m", "1d"}


@app.get("/api/candles/{symbol}")
def candles(symbol: str, interval: str = "1d", count: int = 200):
    symbol = _symbol(symbol)
    # 입력 검증: count 는 1..200 으로 클램프, interval 은 화이트리스트(미스매치 시 1d)
    count = max(1, min(200, count))
    if interval not in _VALID_INTERVALS:
        interval = "1d"

    def build():
        try:
            res = client().candles(symbol, interval=interval, count=count)
        except TossAPIError as e:
            raise HTTPException(404 if e.code == "stock-not-found" else 502,
                                detail="종목을 찾을 수 없습니다" if e.code == "stock-not-found" else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요")
        cs = list(reversed(res.get("candles", []) if isinstance(res, dict) else []))
        out = []
        for c in cs:
            try:
                t = c["timestamp"]
                out.append({"time": t[:10] if interval == "1d" else t,
                            "open": float(c["openPrice"]), "high": float(c["highPrice"]),
                            "low": float(c["lowPrice"]), "close": float(c["closePrice"]),
                            "volume": float(c["volume"])})
            except Exception:
                pass
        return {"symbol": symbol, "interval": interval, "candles": out}
    return cached(f"cd:{symbol}:{interval}:{count}", 30, build)


@app.get("/api/chart-study/{symbol}")
def chart_study(symbol: str, interval: str = "1d", span: int = Query(3, ge=2, le=10), basis: str = "wick"):
    from tossbot.chart_study import study
    if interval not in _VALID_INTERVALS or basis not in ("wick", "body"):
        raise HTTPException(422, detail="지원 간격: 1d/1m, 피벗 기준: wick/body")
    data = candles(symbol, interval, 200)
    return {"symbol": data["symbol"], **study(data["candles"], interval, span, basis)}


@app.get("/api/financial/library")
def financial_library(q: str = Query("", max_length=100)):
    from tossbot.financial_library import library
    return library(q)


@app.get("/api/chart-timing/{symbol}")
def chart_timing(symbol: str):
    from tossbot.chart_execution import normalize, timing
    symbol = _symbol(symbol)
    def build():
        try:
            feats = quant._analyze_cached(client(), symbol, "")
        except TossAPIError as e:
            raise HTTPException(404 if e.code == "stock-not-found" else 502, detail="차트 시점 분석 데이터 조회 실패")
        except ValueError as e:
            raise HTTPException(404, detail=str(e))
        result = timing(symbol, normalize(feats.get("chartCandles") or []))
        if feats.get("chartInterval") != "1d":
            result.update(eligible=False, phase="blocked", reason="차트 확인 전략은 일봉 전용")
        return result
    return cached(f"timing:{symbol}", 30, build)


@app.get("/api/financial/documents/{key}")
def financial_document(key: str):
    from tossbot.financial_library import document
    try:
        return document(key)
    except KeyError:
        raise HTTPException(404, detail="학습 문서를 찾을 수 없습니다")


@app.get("/api/financial/images/{key:path}")
def financial_image(key: str):
    from tossbot.financial_library import image_path
    from fastapi.responses import FileResponse
    try:
        return FileResponse(image_path(key), media_type="image/png")
    except KeyError:
        raise HTTPException(404, detail="학습 그림을 찾을 수 없습니다")


# ⚠️ 라우트 순서: "/api/backtest/{symbol}/compare" 는 "/api/backtest/{symbol}" 보다
# 먼저 선언해야 FastAPI 가 "compare" 를 심볼로 오인하지 않는다.
@app.get("/api/backtest/{symbol}/compare")
def backtest_compare(symbol: str, name: str = "", interval: str = "1d",
                     count: int = 200, stop: float = Query(0.08, ge=0.01, le=0.5, allow_inf_nan=False), capital: int = Query(10_000_000, ge=100_000, le=1_000_000_000)):
    symbol = _symbol(symbol)
    # 입력 검증: backtest_one 과 동일 클램프(count 70..200, stop 1%..50%, interval 화이트리스트)
    count = max(70, min(200, count))
    if interval not in _VALID_INTERVALS:
        interval = "1d"
    stop = max(0.01, min(0.5, stop))

    def build():
        try:
            res = btmod.compare(client(), symbol, name, interval, count, stop, capital)
        except TossAPIError as e:
            # analyze_one/backtest_one 과 동일 매핑: 4xx → 404, 그 외 → 502
            raise HTTPException(404 if e.code == "stock-not-found" else 502,
                                detail="종목을 찾을 수 없습니다" if e.code == "stock-not-found" else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요")
        if res.get("error"):
            raise HTTPException(404, detail=res["error"])
        return res
    return cached(f"btc:{symbol}:{name}:{interval}:{count}:{stop}:{capital}", 300, build)


@app.get("/api/backtest/{symbol}")
def backtest_one(symbol: str, name: str = "", interval: str = "1d",
                 count: int = 200, stop: float = Query(0.08, ge=0.01, le=0.5, allow_inf_nan=False), capital: int = Query(10_000_000, ge=100_000, le=1_000_000_000)):
    symbol = _symbol(symbol)
    # 입력 검증: 토스 캔들 상한이 200 봉이라 count 는 70..200 으로 클램프, interval 화이트리스트(미스매치 시 1d)
    count = max(70, min(200, count))
    if interval not in _VALID_INTERVALS:
        interval = "1d"
    stop = max(0.01, min(0.5, stop))  # 손절 비율 1%..50% 로 클램프

    def build():
        try:
            res = btmod.backtest(client(), symbol, name, interval, count, stop, capital)
        except TossAPIError as e:
            # backtest 내부에서 이미 잡지만, 방어적으로 analyze_one 과 동일 매핑
            raise HTTPException(404 if e.code == "stock-not-found" else 502,
                                detail="종목을 찾을 수 없습니다" if e.code == "stock-not-found" else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요")
        if res.get("error"):
            raise HTTPException(404, detail=res["error"])
        return res
    return cached(f"bt:{symbol}:{name}:{interval}:{count}:{stop}:{capital}", 120, build)


@app.get("/api/intraday/{symbol}")
def intraday(symbol: str, name: str = ""):
    symbol = _symbol(symbol)
    def build():
        try:
            f = analyze(client(), symbol, name, interval=config.INTRADAY_INTERVAL, count=config.INTRADAY_COUNT)
        except TossAPIError as e:
            raise HTTPException(404 if e.code == "stock-not-found" else 502,
                                detail="종목을 찾을 수 없습니다" if e.code == "stock-not-found" else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요")
        if f.get("error"):
            raise HTTPException(404, detail=f["error"])
        d = _full(f)
        d["interval"] = config.INTRADAY_INTERVAL
        return d
    return cached(f"id:{symbol}:{name}", 20, build)


@app.get("/api/screener")
def screener():
    def build():
        c = client()
        syms = [s for s, _ in config.KOSPI_UNIVERSE]
        names = {s: n for s, n in config.KOSPI_UNIVERSE}
        prices = {}
        try:
            for p in c.prices(syms):
                prices[p["symbol"]] = p.get("lastPrice")
        except TossAPIError:
            pass
        items = []
        for s in syms:
            try:
                f = analyze(c, s, names[s], last_price=prices.get(s))
                if f.get("error"):
                    continue
                a = f["aggregate"]
                items.append({"symbol": s, "name": names[s], "price": f["price"], "currency": f["currency"],
                              "score": round(a["total"], 2), "action": a["action"],
                              "nBuy": a["nBuy"], "nSell": a["nSell"], "ret": f["ret"], "rsi": f.get("rsi")})
            except Exception:
                pass
        items.sort(key=lambda x: x["score"], reverse=True)
        return {"items": items, "generatedAt": int(time.time())}
    return cached("screener", 120, build)


@app.get("/api/portfolio")
def portfolio():
    path = config.PAPER_STATE_FILE
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"positions": [], "realizedPnl": 0, "note": "페이퍼 트레이딩 상태 없음 (run.py --paper 실행 전)"}


# ── 종목 검색 + 모의투자(시뮬레이션) ───────────────────────────────
from typing import Literal, Optional  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402

from tossbot import krx_master  # noqa: E402
from tossbot import sim as simmod  # noqa: E402


@app.exception_handler(simmod.SimError)
async def _sim_error(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ── 설정: 토스 키 저장(데스크톱 앱 — OS 키체인) ──────────────────────
class KeysIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=512)
    client_secret: str = Field(min_length=1, max_length=512)


@app.get("/api/settings/keys")
def settings_keys_status():
    """키 저장 상태(값 비노출) + 현재 프로세스 로드 여부."""
    st = secrets_store.status()
    st["loaded"] = bool(config.CLIENT_ID and config.CLIENT_SECRET)
    return st


@app.post("/api/settings/keys")
def settings_keys_save(body: KeysIn):
    """토스 키를 OS 키체인에 저장하고 런타임에 즉시 반영(재시작 불필요)."""
    cid = (body.client_id or "").strip()
    csec = (body.client_secret or "").strip()
    if not cid or not csec:
        raise HTTPException(status_code=400, detail="CLIENT_ID / CLIENT_SECRET 를 모두 입력하세요")
    global _client
    with _client_lock:
        if autopilot.status().get("running"):
            raise HTTPException(409, detail="오토파일럿을 중지한 뒤 키를 교체하세요")
        saved = False
        try:
            secrets_store.save(cid, csec)
            saved = True
        except Exception:
            print("[warn] keyring 저장 실패 — 이번 세션에만 적용합니다", file=sys.stderr)
        os.environ["TOSS_CLIENT_ID"] = cid
        os.environ["TOSS_CLIENT_SECRET"] = csec
        config.CLIENT_ID = cid
        config.CLIENT_SECRET = csec
        _client = None
        _cache.clear()
        quant.clear_caches()
    return {"ok": True, "saved_to_keychain": saved}


class OrderIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9.\-]*$")
    side: Literal["BUY", "SELL"]
    qty: int = Field(gt=0, le=1_000_000_000, strict=True)
    name: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=2000)  # 매매 근거 메모(선택) — sim 히스토리에 저장되어 매매 저널에 표시


class ResetIn(BaseModel):
    cash: Optional[int] = Field(default=None, ge=100_000, le=1_000_000_000)


class AccountCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cash: int = Field(default=10_000_000, ge=100_000, le=1_000_000_000)  # 초기 자본금(원) — 100_000..1_000_000_000 으로 클램프


class AccountSelectIn(BaseModel):
    id: str


@app.get("/api/search")
def search(q: str = Query("", max_length=100)):
    q = q.strip()
    if not q:
        return {"items": []}
    def build():
        items = krx_master.search(q)
        # 마스터에 없으면 코드/티커로 토스 라이브 검증 → 사실상 전 종목 조회 가능
        if re.fullmatch(r"[A-Za-z0-9.\-]{1,8}", q) and not any(i["symbol"].lower() == q.lower() for i in items):
            try:
                for s in client().stocks([q.upper()]):
                    items.insert(0, {"symbol": s["symbol"], "name": s.get("name", ""), "market": s.get("market", "")})
            except Exception:
                pass
        seen, uniq = set(), []
        for it in items:
            if it["symbol"] in seen:
                continue
            seen.add(it["symbol"])
            uniq.append(it)
        return {"items": uniq[:20]}
    return cached(f"search:{q.lower()}", 60, build)


def _usdkrw_meta():
    """(환율, 추정여부) 반환. 환율 API 가 None 이면 1300 폴백 + estimated=True.

    추정여부를 캐시에 함께 담아, app 레이어/프론트가 '추정환율' 경고를 띄울 수 있게 한다.
    """
    def build():
        rate = client().exchange_rate("USD", "KRW")
        if rate is None or not math.isfinite(float(rate)) or float(rate) <= 0:
            return (1300.0, True)
        return (float(rate), False)
    try:
        return cached("fx:usdkrw", 60, build)
    except Exception:
        # exchange_rate 는 파싱 실패만 None 폴백이고 TossAPIError/URLError 등
        # 요청 예외는 전파된다 — 여기서 잡아 폴백 계약(1300, 추정=True)을 지킨다.
        # 실패는 cached 안에서 짧은 네거티브 TTL(10s)로 캐시돼 재시도 폭주도 없다.
        return (1300.0, True)


def _usdkrw():
    # 기존 호출부 호환: 환율 값만 필요한 경우(추정여부 무시)
    return _usdkrw_meta()[0]


def _drop_sim_state_cache():
    # 주문/리셋/계좌 변이 직후 신선도 보장 — simstate 짧은 캐시(4s)를 즉시 무효화
    _cache.invalidate_prefix("simstate:")


@app.get("/api/sim/state")
def sim_state():
    account = simmod.active_account()
    def build():
        syms = simmod.held_symbols(account=account)
        prices = {}
        if syms:
            try:
                for p in client().prices(syms):
                    prices[p["symbol"]] = p.get("lastPrice")
            except Exception:
                pass
        fx, fx_est = _usdkrw_meta()
        st = simmod.get_state(prices, fx, account=account)
        # sim.py 는 건드리지 않고 app 응답에 추정환율 플래그만 덧붙임
        if isinstance(st, dict):
            st["fxEstimated"] = fx_est
        return st
    # 5s 폴링(오토파일럿/Sim 페이지)이 매번 토스 prices 를 때리지 않게 짧은 TTL 캐시
    return cached(f"simstate:{account}", 4, build)


@app.post("/api/sim/order")
def sim_order(o: OrderIn):
    try:
        pr = client().prices([o.symbol])
    except TossAPIError as e:
        raise HTTPException(400, detail=e.code)
    if not pr or pr[0].get("lastPrice") is None:
        raise HTTPException(400, detail="현재가 조회 불가 (종목 코드를 확인하세요)")
    try:
        price = simmod._positive(pr[0]["lastPrice"], "현재가")
    except simmod.SimError:
        raise HTTPException(502, detail="유효한 현재가를 조회할 수 없습니다") from None
    currency = pr[0].get("currency", "KRW")
    name = o.name
    if not name:
        try:
            ss = client().stocks([o.symbol])
            name = ss[0].get("name", "") if ss else ""
        except Exception:
            pass
    if currency == "USD":
        fx, fx_est = _usdkrw_meta()
    else:
        fx, fx_est = 1.0, False
    try:
        res = simmod.order(o.symbol, o.side, o.qty, price, currency=currency, fx=fx, name=name, note=o.note)
    except simmod.SimError as e:
        raise HTTPException(400, detail=str(e))
    # 주문 직후 GET /api/sim/state 가 4s 캐시된 이전 상태를 돌려주지 않게 무효화
    _drop_sim_state_cache()
    _drop_journal_cache()
    # sim.py 응답을 변형하지 않고 추정환율 플래그만 덧붙임(USD 주문일 때만 의미)
    if isinstance(res, dict):
        res["fxEstimated"] = fx_est
    return res


@app.post("/api/sim/reset")
def sim_reset(r: ResetIn):
    with _client_lock:
        account = simmod.active_account()
        ap = autopilot.status()
        if ap.get("running") and ap.get("account") == account:
            raise HTTPException(409, detail="가동 중인 오토파일럿이 사용하는 계좌입니다 — 먼저 오토파일럿을 중지하세요")
        res = simmod.reset(r.cash, account=account)
    # 초기화 직후 저널이 옛 통계를 캐시로 돌려주지 않도록(계좌 변이와 동일 정책)
    _drop_journal_cache()
    _drop_sim_state_cache()
    return res


# ── 모의투자 다중 계좌 CRUD ─────────────────────────────────────────
# 계좌 변이(생성/선택/삭제) 후 매매 저널 캐시를 비워, 프론트 전체 reload 시
# 이전 계좌의 저널이 최대 10초간 노출되는 일이 없도록 한다.
def _drop_journal_cache():
    _cache.invalidate_prefix("journal:")


@app.get("/api/sim/accounts")
def sim_accounts():
    return simmod.list_accounts()


@app.post("/api/sim/accounts")
def sim_accounts_create(a: AccountCreateIn):
    # 초기 자본금은 10만원..10억원으로 클램프(계약 (S4))
    cash = max(100_000, min(1_000_000_000, a.cash))
    try:
        new_id = simmod.create_account(a.name, cash)
    except simmod.SimError as e:
        raise HTTPException(400, detail=str(e))
    _drop_journal_cache()
    _drop_sim_state_cache()
    # newId 를 함께 반환 — 프론트가 '방금 만든 계좌'를 휴리스틱 없이 정확히 선택하게
    return {"newId": new_id, **simmod.list_accounts()}


@app.post("/api/sim/accounts/select")
def sim_accounts_select(s: AccountSelectIn):
    try:
        simmod.select_account(s.id)
    except simmod.SimError as e:
        raise HTTPException(400, detail=str(e))
    _drop_journal_cache()
    _drop_sim_state_cache()  # 활성 계좌가 바뀌면 simstate 캐시도 즉시 무효
    return simmod.list_accounts()


@app.delete("/api/sim/accounts/{acc_id}")
def sim_accounts_delete(acc_id: str):
    # 가동 중인 오토파일럿이 고정한 계좌는 삭제 금지 — 루프가 매 사이클
    # '계좌를 찾을 수 없습니다' 오류를 무한 기록하는 상황을 막는다.
    with _client_lock:
        ap = autopilot.status()
        if ap.get("running") and ap.get("account") == acc_id:
            raise HTTPException(409, detail="가동 중인 오토파일럿이 사용하는 계좌입니다 — 먼저 오토파일럿을 중지하세요")
        # active 계좌 삭제 시 sim 내부에서 남은 첫 계좌로 자동 전환됨
        try:
            simmod.delete_account(acc_id)
        except simmod.SimError as e:
            raise HTTPException(400, detail=str(e))
    _drop_journal_cache()
    _drop_sim_state_cache()  # active 계좌가 바뀔 수 있으므로 simstate 캐시도 무효
    return simmod.list_accounts()


# ── 자동매매 실행 브로커 (토스증권 | 한국투자증권) ─────────────────
# 분석/차트/시그널은 토스 데이터 공유, 브로커는 '주문 실행'에만 적용.
class BrokerIn(BaseModel):
    broker: str


@app.get("/api/broker")
def broker_status():
    return brokers.status(client())


@app.post("/api/broker/select")
def broker_select(b: BrokerIn):
    try:
        brokers.select(b.broker)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return brokers.status(client())


# ── 퀀트 스크리닝 + 트레이드 플랜 ──────────────────────────────────
# quant/autopilot 이 허용하는 시장 화이트리스트(미스매치 시 kr 로 폴백)
_VALID_MARKETS = {"kr", "us", "kosdaq", "usgrowth", "all"}


def _quant_snapshot(top: int, market: str):
    """/api/quant 와 텔레그램 /picks 가 공유하는 스크리닝 빌더 + 캐시.

    같은 캐시 키(qt:{market}:{top})에 항상 같은 shape(enrich 포함)가 들어가도록
    두 호출 경로가 이 함수 하나를 쓴다 — 어느 쪽이 먼저 채워도 응답 계약 동일.
    """
    def build():
        try:
            res = quant.screen(client(), top_n=top, market=market)
        except TossAPIError as e:
            # analyze_one 과 동일 매핑: 4xx → 404, 그 외(서버/네트워크) → 502
            raise HTTPException(404 if e.code == "stock-not-found" else 502,
                                detail="종목을 찾을 수 없습니다" if e.code == "stock-not-found" else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요")
        # 미국 포함 시장이면 CBOE 지연 옵션 신호를 병합(부가 신호 — 실패해도 스크리닝은 정상)
        if market in ("us", "usgrowth", "all"):
            try:
                res = options_flow.enrich(res, max_symbols=10)
            except Exception:
                pass
        return res
    # 캐시 키에 market 포함(기존 qt:{top} 키 대체)
    return cached(f"qt:{market}:{top}", 120, build)


@app.get("/api/quant")
def quant_screen(top: int = 10, market: str = "kr"):
    top = max(3, min(20, top))  # top_n 은 3..20 으로 클램프
    if market not in _VALID_MARKETS:
        market = "kr"
    return _quant_snapshot(top, market)


@app.get("/api/quant/plan/{symbol}")
def quant_plan(symbol: str, name: str = ""):
    symbol = _symbol(symbol)
    def build():
        try:
            f = analyze(client(), symbol, name)
        except TossAPIError as e:
            raise HTTPException(404 if e.code == "stock-not-found" else 502,
                                detail="종목을 찾을 수 없습니다" if e.code == "stock-not-found" else "토스 API 요청에 실패했습니다 — 연결 상태를 확인하세요")
        if f.get("error"):
            raise HTTPException(404, detail=f["error"])
        return {"symbol": f["symbol"], "name": f["name"], "price": f["price"],
                "currency": f["currency"], "plan": quant.trade_plan(f)}
    return cached(f"qp:{symbol}:{name}", 30, build)


# ── 오토파일럿(모의투자 전용 자동매매 루프) ────────────────────────
class AutopilotIn(BaseModel):
    strategy: Literal["legacy", "chart_confirmed"] = "legacy"
    riskPct: float = Field(.5, ge=.1, le=2, allow_inf_nan=False)
    minRR: float = Field(1.5, ge=1, le=5, allow_inf_nan=False)
    intervalSec: Optional[int] = None
    maxPositions: Optional[int] = None
    budgetKrw: Optional[int] = None
    market: Optional[str] = None  # kr | us | kosdaq | usgrowth | all (미지정/그 외 → kr)
    regimeGuard: bool = True  # 레짐 가드 — 시장 위험 단계가 높으면 신규 진입 축소/중단(기본 on)
    account: Optional[str] = None  # 매매 대상 모의계좌 id (미지정 시 시작 시점의 active 계좌)


@app.get("/api/autopilot")
def autopilot_status():
    return autopilot.status()


@app.post("/api/autopilot/start")
def autopilot_start(a: AutopilotIn):
    # body 전부 optional — 미지정 시 기본값 후 안전 범위로 클램프
    interval = max(20, min(600, a.intervalSec if a.intervalSec is not None else 60))
    positions = max(1, min(10, a.maxPositions if a.maxPositions is not None else 3))
    budget = max(100_000, min(5_000_000, a.budgetKrw if a.budgetKrw is not None else 1_000_000))
    # market 화이트리스트(kr/us/kosdaq/usgrowth/all) — 미지정·미스매치 시 kr
    market = a.market if a.market in _VALID_MARKETS else "kr"
    # account 지정 시 실제 존재하는 계좌인지 검증(없으면 400) — 미지정이면 autopilot 이
    # 시작 시점의 active 계좌를 캡처한다(계약 (S3)).
    with _client_lock:
        if a.account is not None:
            ids = {acc["id"] for acc in simmod.list_accounts()["accounts"]}
            if a.account not in ids:
                raise HTTPException(400, detail=f"계좌를 찾을 수 없습니다: {a.account}")
        return autopilot.start(client(), interval_sec=interval, max_positions=positions,
                               budget_krw=budget, market=market, regime_guard=a.regimeGuard,
                               account=a.account, strategy=a.strategy, risk_pct=a.riskPct, min_rr=a.minRR)


@app.post("/api/autopilot/stop")
def autopilot_stop():
    return autopilot.stop()


@app.post("/api/autopilot/reset")
def autopilot_reset():
    # 로그·에러만 비움(가동 중에도 안전 — 포지션·진입계획·설정 불변)
    return autopilot.reset_logs()


# ── 마켓 인텔리전스(레짐·매크로·뉴스·캘린더) + 매매 저널 + 알림 ────────
@app.get("/api/regime")
def regime_status():
    # 시장 레짐(위험 단계) — regime 모듈 자체 캐시(300s)와 별개로 앱 레이어에서도 300s 캐시
    return cached("regime", 300, lambda: regimemod.get_regime(client()))


@app.get("/api/macro")
def macro_board():
    def build():
        board = macro.get_board(client())
        # 보드 + 반응 요약 한 줄을 함께 반환(프론트가 한 번에 렌더)
        return {**board, "reaction": macro.reaction_summary(board.get("items", []))}
    return cached("macro", 120, build)


@app.get("/api/news")
def news_feed():
    return cached("news", 300, newsmod.fetch_news)


@app.get("/api/calendar")
def calendar_feed_api(days: int = 7):
    days = max(1, min(14, days))  # days 는 1..14 로 클램프(Nasdaq 반복 조회 폭주 방지)
    return cached(f"cal:{days}", 1800, lambda: calendar_feed.get_calendar(days=days))


@app.get("/api/journal")
def journal_stats():
    # 모의투자 히스토리 기반 매매 저널 — 주문 직후 반영되도록 짧은 캐시(10s)
    account = simmod.active_account()
    return cached(f"journal:{account}", 10, lambda: journal.stats(account=account))


@app.get("/api/notify")
def notify_status():
    return notify.configured()


@app.post("/api/notify/test")
def notify_test():
    # 실제 전송 시도 — 실패/미설정이어도 예외 없이 sent=False (notify.send 는 무해 실패)
    return {"sent": notify.send("tossbot 알림 테스트"), "configured": notify.configured()}


# ── 텔레그램 컨트롤 봇 기동 ─────────────────────────────────────────
# env TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 가 모두 있으면 startup 시 봇을 띄운다.
# 봇은 데몬 스레드(tossbot/telegram_bot.py) — 실패해도 서버 기동에는 무영향.
def _tg_regime_text() -> str:
    """레짐 요약 텍스트 — /api/regime 과 동일 캐시 키(300s) 재사용."""
    r = cached("regime", 300, lambda: regimemod.get_regime(client()))
    head = f"{r.get('emoji', '')} {r.get('stage', '?')} (점수 {r.get('score', '?')}) — {r.get('guidance', '')}"
    lines = [head]
    for c in (r.get("components") or []):
        lines.append(f"· {c.get('label', '?')}: {c.get('signal', '-')} — {c.get('detail') or '데이터 없음'}")
    return "\n".join(lines)


def _tg_status_text() -> str:
    """오토파일럿 상태 한줄 요약 — '🤖 가동중 | 계좌 default | 사이클 12 | 🔵 STABLE' 식."""
    ap = autopilot.status()
    rg = ap.get("regime") or {}
    stage, emoji = rg.get("stage"), rg.get("emoji") or ""
    if not stage:
        # 오토파일럿이 아직 레짐을 조회한 적 없으면 앱 캐시(300s)에서 스냅샷
        try:
            r = cached("regime", 300, lambda: regimemod.get_regime(client()))
            stage, emoji = r.get("stage"), r.get("emoji") or ""
        except Exception:
            stage = None
    parts = ["🤖 가동중" if ap.get("running") else "⏸️ 정지",
             f"계좌 {ap.get('account') or '-'}",
             f"사이클 {ap.get('cycles', 0)}"]
    if stage:
        parts.append(f"{emoji} {stage}".strip())
    errs = ap.get("errors") or []
    if errs:
        parts.append(f"⚠️ 오류 {len(errs)}건")
    return " | ".join(parts)


def _tg_handlers() -> dict:
    """텔레그램 봇에 주입할 핸들러 — 각 fn 은 한국어 요약 텍스트를 반환.

    예외는 fn 안에서 잡아 '⚠️ 오류: ...' 문자열로 반환(봇 루프 보호).
    기존 cached()/모듈을 재사용해 신규 스캔 폭주를 막는다.
    """
    def status_fn() -> str:
        try:
            return _tg_status_text()
        except Exception as e:
            return f"⚠️ 오류: {e}"

    def regime_fn() -> str:
        try:
            return _tg_regime_text()
        except Exception as e:
            return f"⚠️ 오류: {e}"

    def picks_fn(market: str = "kr") -> str:
        try:
            m = market if market in _VALID_MARKETS else "kr"
            # /api/quant 와 동일 빌더·캐시 키(qt:{market}:10, 120s) 공유 — 어느 쪽이
            # 먼저 캐시를 채워도 옵션 신호(enrich) 포함 여부가 달라지지 않는다.
            res = _quant_snapshot(10, m)
            picks = (res.get("picks") or [])[:5]
            if not picks:
                return f"📉 {m} 스크리닝 결과가 없습니다"
            lines = [f"📈 퀀트 픽 상위 5 ({m})"]
            for i, p in enumerate(picks, 1):
                plan = p.get("plan") or {}
                name = p.get("name") or p.get("symbol", "?")
                lines.append(f"{i}. {name} — 점수 {p.get('quantScore')} | {plan.get('note') or '플랜 없음'}")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ 오류: {e}"

    def portfolio_fn() -> str:
        try:
            st = sim_state()  # 라우트 함수 재사용 — 현재가·환율 반영된 sim.get_state 요약
            lines = [f"💼 평가액 {st['equity']:,}원 | 현금 {st['cash']:,}원 | "
                     f"총손익 {st['totalPnl']:+,}원 ({st['totalPnlPct']:+.2f}%)"]
            pos = st.get("positions") or []
            for p in pos[:10]:
                nm = p.get("name") or p.get("symbol", "?")
                lines.append(f"· {nm} {p['qty']}주 — 평가 {p['valueKrw']:,}원 | {p['pnl']:+,}원 ({p['pnlPct']:+.2f}%)")
            if not pos:
                lines.append("보유 종목 없음")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ 오류: {e}"

    def autopilot_start_fn(market: str = "kr") -> str:
        try:
            m = market if market in _VALID_MARKETS else "kr"  # 화이트리스트, 기본 kr
            # /api/autopilot/start 기본값과 동일(interval 60s, 3종목, 100만원, 레짐가드 on)
            with _client_lock:
                autopilot.start(client(), interval_sec=60, max_positions=3,
                                budget_krw=1_000_000, market=m, regime_guard=True, account=None)
            return _tg_status_text()
        except Exception as e:
            return f"⚠️ 오류: {e}"

    def autopilot_stop_fn() -> str:
        try:
            autopilot.stop()
            return _tg_status_text()
        except Exception as e:
            return f"⚠️ 오류: {e}"

    def accounts_fn() -> str:
        try:
            res = simmod.list_accounts()
            active = res.get("active")
            lines = ["👤 모의계좌 목록"]
            for a in res.get("accounts", []):
                mark = "✅" if a.get("id") == active else "·"
                lines.append(f"{mark} {a.get('name')}({a.get('id')}) — 현금 {a.get('cash', 0):,}원 | "
                             f"보유 {a.get('positions', 0)}종목 | 거래 {a.get('trades', 0)}건")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ 오류: {e}"

    return {"status": status_fn, "regime": regime_fn, "picks": picks_fn,
            "portfolio": portfolio_fn, "autopilot_start": autopilot_start_fn,
            "autopilot_stop": autopilot_stop_fn, "accounts": accounts_fn}


def _start_telegram_bot():
    # 토큰/채팅 ID 는 env 로만 — 둘 중 하나라도 없으면 봇 미기동(현행 무영향)
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        return
    try:
        from tossbot import telegram_bot  # 지연 임포트 — 모듈 부재/오류가 서버를 죽이지 않게
        telegram_bot.start_bot(_tg_handlers())  # 데몬 스레드 — 서버 종료 시 함께 종료
    except Exception as e:
        print(f"[warn] 텔레그램 봇 기동 실패: {e}", file=sys.stderr)


# ── 빌드된 프론트엔드(SPA) 서빙: web/dist 있으면 같은 서버(:8000)에서 UI까지 제공 ──
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = os.path.join(_ROOT, "web", "dist")
if os.path.isdir(_DIST):
    _assets = os.path.join(_DIST, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/")
    def _spa_index():
        return FileResponse(os.path.join(_DIST, "index.html"))

    @app.get("/{full_path:path}")
    def _spa(full_path: str):
        # 매칭되지 않은 /api/* 는 SPA 폴백으로 삼키지 않고 JSON 404 — 오타/구버전
        # 경로 호출이 200 text/html 을 받아 JSON 파싱 오류로 오인되는 일을 막는다.
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "unknown api"})
        # 등록된 /api/* 라우트는 위에서 이미 매칭됨. 실제 정적파일이면 그걸, 아니면 index.html(SPA 라우팅).
        fp = os.path.abspath(os.path.join(_DIST, full_path))
        try:
            # commonpath 는 서로 다른 드라이브(예: C:\ vs D:\) 경로면 ValueError → SPA 폴백
            inside = os.path.commonpath([fp, _DIST]) == _DIST
        except ValueError:
            inside = False
        if inside and os.path.isfile(fp):
            return FileResponse(fp)
        return FileResponse(os.path.join(_DIST, "index.html"))
