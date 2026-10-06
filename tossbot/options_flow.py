"""미국 주식 옵션 플로우 신호 — CBOE 공개 지연 데이터 기반 (표준 라이브러리만).

데이터 소스: https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json
  - 무료·API 키 불필요·15분 지연. 체인 전체(거래량·OI·IV·그릭스) 제공.
  - 계약별 '체결 테이프'(스윕/블록)는 아니므로, 유료 플로우 서비스가 잡는 신호의
    스냅샷 프록시를 계산한다: P/C 비율, vol>OI 신규 포지션 개설, 근월 콜 집중, ATM IV.

성능: 종목당 응답 ~1.5MB → 유니버스 전체가 아니라 '퀀트 상위 픽 + 수급 레이더 대상'
미국 종목에만 호출하고, 모듈 캐시(10분)로 재호출을 막는다.

한국 종목은 대상 아님(개별주 옵션 유동성 부재) — KOSPI200 지수옵션은 KIS 연동 후 과제.
교육용 참고 지표이며 투자 권유가 아닙니다.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime

CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
# CDN 이 UA 없는 요청을 차단할 수 있어 브라우저 UA 사용(공개 지연 데이터).
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) tossbot-edu"

CACHE_TTL = 600.0        # 종목당 10분 캐시(지연 데이터라 충분)
_FETCH_GAP = 0.3         # 요청 간 최소 간격(초) — CDN 예의
_HOT_MIN_VOL = 500       # '핫 계약' 최소 거래량
_HOT_VOL_OI = 1.5        # 거래량이 OI 의 몇 배면 신규 개설 의심인지
_HOT_MIN_DELTA = 0.15    # |delta| 하한 — 초저델타 로또성 노이즈 제외
_PC_BULL = 0.6           # P/C(거래량) < 0.6 → 콜 쏠림(강세)
_PC_BEAR = 1.3           # P/C(거래량) > 1.3 → 풋 쏠림(약세)
_NEAR_DAYS = 14          # '근월' 판정 일수
_NEAR_CALL_SHARE = 0.6   # 근월 콜 비중 임계

_lock = threading.Lock()
_cache: dict = {}        # {symbol: (ts, result|None)}
_inflight: dict = {}     # {symbol: threading.Event} — 같은 종목 동시 다운로드 방지
_fetch_lock = threading.Lock()   # _FETCH_GAP 스로틀 보호(레이스 방지)
_last_fetch = 0.0        # _fetch_lock 안에서만 읽고 쓴다

_OPT_RX = re.compile(r"(\d{6})([CP])(\d{8})")


def _fetch_chain(symbol):
    """CBOE 지연 체인 JSON → dict. 실패 시 None (조용히 — 옵션은 부가 신호).

    _FETCH_GAP 스로틀은 _fetch_lock 으로 직렬화 — 대기·타임스탬프 갱신을
    락 안에서 수행해 두 스레드가 동시에 발사하는 레이스를 막는다
    (요청 '시작' 간격 기준; HTTP 자체는 락 밖이라 병렬 응답 대기는 허용).
    """
    global _last_fetch
    with _fetch_lock:
        wait = _FETCH_GAP - (time.time() - _last_fetch)
        if wait > 0:
            time.sleep(wait)
        _last_fetch = time.time()
    req = urllib.request.Request(CBOE_URL.format(sym=symbol.upper()),
                                 headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return None


def _leg(sym):
    """옵션 심볼 → (만기 date, 'C'|'P', 행사가). 파싱 실패 시 (None,None,None)."""
    m = _OPT_RX.search(sym or "")
    if not m:
        return None, None, None
    try:
        exp = datetime.strptime(m.group(1), "%y%m%d").date()
    except ValueError:
        return None, None, None
    return exp, m.group(2), int(m.group(3)) / 1000.0


def analyze_options(symbol):
    """한 종목의 옵션 플로우 프록시 신호. 반환(신호 없거나 실패 시 None):
    {"pcVol","pcOI","atmIV","opinion"("BUY"|"SELL"|"WATCH"),
     "hot":[{"expiry","type","strike","volume","oi","ratio","iv","delta"}...최대3],
     "alerts":[{"label","detail"}...]}
    """
    now = time.time()
    with _lock:
        hit = _cache.get(symbol)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
        # 같은 종목 동시 요청 스탬피드 방지 — 첫 스레드만 다운로드, 나머지는 대기
        ev = _inflight.get(symbol)
        if ev is None:
            ev = threading.Event()
            _inflight[symbol] = ev
            owner = True
        else:
            owner = False

    if not owner:
        ev.wait(timeout=30.0)                 # 다운로드(~1.5MB) 완료 대기
        with _lock:
            hit = _cache.get(symbol)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return hit[1]
        return None  # 소유 스레드 실패/타임아웃 — 옵션은 부가 신호, 조용히 포기

    try:
        raw = _fetch_chain(symbol)
        try:
            result = _analyze(raw) if raw else None
        except Exception:  # noqa: BLE001 - 비정상 응답(volume="N/A" 등)도 None 으로 캐시(재다운로드 방지)
            result = None
        with _lock:
            _cache[symbol] = (time.time(), result)
    finally:
        with _lock:
            _inflight.pop(symbol, None)
        ev.set()                              # 대기자 깨움(실패 경로 포함)
    return result


def _analyze(raw):
    data = (raw or {}).get("data") or {}
    opts = data.get("options") or []
    if not opts:
        return None
    today = date.today()

    cvol = pvol = coi = poi = 0.0
    near_cvol = 0.0
    atm_ivs = []
    hot = []
    for o in opts:
        exp, cp, strike = _leg(o.get("option"))
        if cp is None:
            continue
        vol = float(o.get("volume") or 0)
        oi = float(o.get("open_interest") or 0)
        iv = float(o.get("iv") or 0)
        delta = float(o.get("delta") or 0)
        dte = (exp - today).days if exp else 9999
        if cp == "C":
            cvol += vol
            coi += oi
            if dte <= _NEAR_DAYS:
                near_cvol += vol
            # ATM 근처(델타 0.35~0.65) 콜 IV 표본
            if 0.35 <= delta <= 0.65 and iv > 0:
                atm_ivs.append(iv)
        else:
            pvol += vol
            poi += oi
        # 핫 계약: 신규 포지션 대량 개설 의심(거래량이 OI 를 크게 초과)
        if (vol >= _HOT_MIN_VOL and oi > 0 and vol >= oi * _HOT_VOL_OI
                and abs(delta) >= _HOT_MIN_DELTA and dte >= 0):
            hot.append({
                "expiry": exp.isoformat() if exp else None, "type": cp,
                "strike": strike, "volume": int(vol), "oi": int(oi),
                "ratio": round(vol / oi, 1), "iv": round(iv, 3), "delta": round(delta, 2),
            })

    if cvol + pvol < 1000:  # 옵션이 거의 안 도는 종목 — 신호 무의미
        return None

    hot.sort(key=lambda h: -h["volume"])
    hot = hot[:3]
    pc_vol = round(pvol / cvol, 2) if cvol else None
    pc_oi = round(poi / coi, 2) if coi else None
    atm_iv = round(sum(atm_ivs) / len(atm_ivs), 3) if atm_ivs else None
    near_share = (near_cvol / cvol) if cvol else 0.0

    alerts = []
    bull = bear = 0
    if pc_vol is not None:
        if pc_vol <= _PC_BULL:
            bull += 1
            alerts.append({"label": "옵션: 콜 쏠림",
                           "detail": f"P/C(거래량) {pc_vol} — 콜 매수 우위(강세 베팅)"})
        elif pc_vol >= _PC_BEAR:
            bear += 1
            alerts.append({"label": "옵션: 풋 쏠림",
                           "detail": f"P/C(거래량) {pc_vol} — 풋 수요 우위(약세/헤지)"})
    hot_calls = [h for h in hot if h["type"] == "C"]
    hot_puts = [h for h in hot if h["type"] == "P"]
    if hot_calls:
        h = hot_calls[0]
        bull += 2
        alerts.append({"label": "옵션: 콜 신규 대량",
                       "detail": f"{h['expiry']} {h['strike']:g}콜 거래량 {h['volume']:,} (OI {h['ratio']}배) — 신규 강세 포지션 의심"})
    if hot_puts:
        h = hot_puts[0]
        bear += 2
        alerts.append({"label": "옵션: 풋 신규 대량",
                       "detail": f"{h['expiry']} {h['strike']:g}풋 거래량 {h['volume']:,} (OI {h['ratio']}배) — 하방 베팅/헤지 의심"})
    if near_share >= _NEAR_CALL_SHARE and cvol > pvol * 1.3:
        bull += 1
        alerts.append({"label": "옵션: 단기 콜 집중",
                       "detail": f"만기 {_NEAR_DAYS}일 이내 콜이 콜 거래량의 {near_share:.0%} — 단기 이벤트 베팅"})

    if not alerts:
        return None
    opinion = "BUY" if bull > bear else ("SELL" if bear > bull else "WATCH")
    return {"pcVol": pc_vol, "pcOI": pc_oi, "atmIV": atm_iv,
            "opinion": opinion, "hot": hot, "alerts": alerts}


def _is_us(item):
    """USD 종목 판정 — currency 우선, 없으면 심볼이 알파벳이면 미국으로 간주."""
    ccy = (item.get("currency") or "").upper()
    if ccy:
        return ccy == "USD"
    return bool(re.fullmatch(r"[A-Z.\-]+", item.get("symbol") or ""))


def enrich(screen_result, max_symbols=10):
    """quant.screen() 결과에 옵션 신호를 병합(미국 종목만, 실패는 조용히 skip).

    - 픽 상위부터 최대 max_symbols 개 미국 종목: pick["options"] 부착.
    - 수급 레이더(flowAlerts): 같은 종목이 있으면 alerts 병합 + flowScore 가산,
      옵션 단독 신호(레이더 미포함)면 새 항목 추가. 점수순 재정렬(최대 12 유지).
    반환: screen_result (제자리 수정).
    """
    if not isinstance(screen_result, dict):
        return screen_result
    picks = screen_result.get("picks") or []
    flow = list(screen_result.get("flowAlerts") or [])
    flow_by_sym = {f.get("symbol"): f for f in flow}

    done = 0
    for pick in picks:
        if done >= max_symbols:
            break
        if not _is_us(pick):
            continue
        sym = pick.get("symbol")
        try:
            sig = analyze_options(sym)
        except Exception:  # noqa: BLE001 - 옵션은 부가 신호: 어떤 실패도 스크리닝을 막지 않는다
            sig = None
        done += 1
        if not sig:
            continue
        pick["options"] = sig
        pts = 2 if sig["opinion"] in ("BUY", "SELL") else 1
        f = flow_by_sym.get(sym)
        if f is not None:
            f["alerts"] = list(f.get("alerts") or []) + sig["alerts"]
            f["flowScore"] = (f.get("flowScore") or 0) + pts
        else:
            f = {"symbol": sym, "name": pick.get("name", ""), "price": pick.get("price"),
                 "currency": pick.get("currency", "USD"), "flowScore": pts,
                 "opinion": sig["opinion"], "alerts": list(sig["alerts"])}
            flow.append(f)
            flow_by_sym[sym] = f

    flow.sort(key=lambda f: -(f.get("flowScore") or 0))
    screen_result["flowAlerts"] = flow[:12]
    return screen_result
