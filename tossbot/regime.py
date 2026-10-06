"""시장 레짐(위험 단계) 산출 — CBOE 지연 스냅샷 + 토스 ETF 캔들 (표준 라이브러리만).

데이터 소스:
  - CBOE 지수 지연시세(무료·API 키 불필요·15분 지연):
    https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json (_VVIX/_SPX 동일 형식)
    → {"data":{"current_price":..., "prev_day_close":...}} — 현재가·전일종가만 제공(과거 시계열 없음).
  - 토스 client.candles(ETF, "1d", 30):
    SPY(SPX 20일선 프록시)·TLT(금리충격)·UUP(달러)·HYG(크레딧) 계산용.
  - MOVE 지수(채권 변동성)는 무료 소스가 없어 TLT 실현변동성으로 프록시한다(note 각주 필수).

스코어(0~100) → 5단계:
  0-20 STABLE 🔵 / 20-40 TENSION 🟤 / 40-60 COMPRESSION 🟡 / 60-80 FRACTURE 🟠 / 80+ TRIGGER 🔴

개별 소스 실패는 해당 컴포넌트만 signal="calm"·detail="데이터 없음" 으로 강등하고
나머지로 스코어를 산출한다. 모듈 캐시 300초 — autopilot 이 사이클마다 호출하므로
외부 요청 폭주를 막기 위해 필수. 단, 실패 결과는 정상 결과와 같은 TTL 로 고착시키지
않는다:
  - 전체 실패: 이전 정상 결과가 있으면 stale=True 로 재사용(가드 유지), 없으면
    stage=None + degraded=True 반환 — 둘 다 FAIL_TTL(30s)로만 캐시해 곧 재시도.
  - 부분 실패: '데이터 없음' 컴포넌트가 3개 이상이면 DEGRADED_TTL(60s)로 단축.
stage=None 은 autopilot._update_regime 의 실패 경로(이전 스냅샷 유지·가드 일시
해제)와 프론트 배너 숨김(!rg.stage) 계약에 맞춘 값이다 — STABLE 을 조작해 내면
실제 TRIGGER 상태에서 가짜 '레짐 변화' 알림과 가드 해제가 발생한다.

교육용 참고 지표이며 투자 권유가 아닙니다.
"""
from __future__ import annotations

import json
import statistics
import threading
import time
import urllib.error
import urllib.request

CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/{sym}.json"
# CBOE CDN 이 기본 파이썬 UA 를 차단하므로 브라우저 UA 필수(공개 지연 데이터).
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) tossbot-edu"

CACHE_TTL = 300.0     # 모듈 캐시(초) — 정상 결과
DEGRADED_TTL = 60.0   # 부분 실패(N/A 컴포넌트 3개 이상) 결과의 단축 TTL
FAIL_TTL = 30.0       # 전체 실패 결과의 단축 TTL — 곧 재시도
_DEGRADED_NA_MIN = 3  # '데이터 없음' 컴포넌트가 이 개수 이상이면 부분 실패로 간주
_FETCH_GAP = 0.25     # CBOE 요청 간 최소 간격(초) — CDN 예의

_lock = threading.Lock()
_cache = None       # (ts, result, ttl)
_last_fetch = 0.0

MOVE_NOTE = "MOVE 지수는 무료 소스가 없어 TLT 실현변동성으로 대체"

# (스코어 상한(미만), 단계, 이모지, 한국어 가이던스)
_STAGES = [
    (20, "STABLE", "🔵", "평소 기준대로 매매 가능한 구간. 정상 리스크 한도 내에서 전략을 운용하세요."),
    (40, "TENSION", "🟤", "긴장 신호가 일부 감지됩니다. 신규 진입은 가능하되 포지션 크기와 손절 라인을 점검하세요."),
    (60, "COMPRESSION", "🟡", "위험 압력이 누적되는 구간. 신규 진입을 선별하고 레버리지·집중 포지션을 줄이세요."),
    (80, "FRACTURE", "🟠", "시장 균열이 확산 중입니다. 신규 진입을 절반 이하로 축소하고 방어 위주로 전환하세요."),
    (101, "TRIGGER", "🔴", "신규 진입 중단·방어 최우선. 현금 비중 확대 권고."),
]


# ── 데이터 수집 헬퍼 ──────────────────────────────────────────────

def _cboe_quote(sym):
    """CBOE 지연 스냅샷 → (현재가, 전일종가). 실패 시 (None, None) — 조용히 강등."""
    global _last_fetch
    wait = _FETCH_GAP - (time.time() - _last_fetch)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(
        CBOE_URL.format(sym=sym),
        headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            _last_fetch = time.time()
            d = (json.loads(r.read().decode("utf-8")) or {}).get("data") or {}
        cur = d.get("current_price")
        prev = d.get("prev_day_close")
        if cur is None or prev is None:
            return None, None
        return float(cur), float(prev)
    except Exception:  # noqa: BLE001 - 레짐은 부가 신호: 어떤 실패도 전체를 막지 않는다
        _last_fetch = time.time()
        return None, None


def _closes(client, symbol, count=30):
    """토스 일봉 종가 리스트(과거→현재 오름차순). 실패/빈 응답 시 None."""
    try:
        res = client.candles(symbol, "1d", count)
        rows = res.get("candles", []) if isinstance(res, dict) else []
        closes = []
        for c in reversed(rows or []):  # candles 는 최신순 → 오름차순 정규화
            try:
                closes.append(float(c.get("closePrice")))
            except (TypeError, ValueError):
                continue
        return closes or None
    except Exception:  # noqa: BLE001 - TossAPIError 포함 모든 실패를 '데이터 없음'으로 강등
        return None


def _pct(a, b):
    """b→a 변화율(%). 분모 0/None 방어."""
    if not b:
        return None
    return (a / b - 1.0) * 100.0


def _na(key, label):
    """소스 실패 컴포넌트 — 계약대로 signal='calm', detail='데이터 없음'."""
    return {"key": key, "label": label, "value": None, "change": None,
            "signal": "calm", "detail": "데이터 없음"}


# ── 레짐 산출 ─────────────────────────────────────────────────────

def _build(client):
    pts = 0
    comps = []

    # ── VIX (CBOE 스냅샷) ─────────────────────────────────
    vix, vix_prev = _cboe_quote("_VIX")
    if vix is None:
        comps.append(_na("vix", "VIX (변동성)"))
    else:
        chg = _pct(vix, vix_prev)
        chg = round(chg, 2) if chg is not None else None
        # VIX 레벨 가중 — 통상 구간 해석에 근거:
        #   ≤14 저변동 강세장(0) / 14-18 평시(10) / 18-22 경계(20)
        #   / 22-28 조정 국면(35) / >28 패닉 영역(50)
        if vix <= 14:
            lvl = 0
        elif vix <= 18:
            lvl = 10
        elif vix <= 22:
            lvl = 20
        elif vix <= 28:
            lvl = 35
        else:
            lvl = 50
        pts += lvl
        # VIX 일변화율 가중: 하루 +10% 이상 급등은 레벨과 무관한 충격 신호 → +10.
        spike = chg is not None and chg >= 10.0
        if spike:
            pts += 10
        sig = "calm" if vix <= 18 else ("warn" if vix <= 22 else "hot")
        if spike and sig == "calm":
            sig = "warn"  # 레벨은 낮아도 급등 자체가 경고
        comps.append({
            "key": "vix", "label": "VIX (변동성)",
            "value": round(vix, 2), "change": chg, "signal": sig,
            "detail": f"공포지수 {vix:.1f} (전일 {vix_prev:.1f}) — 22 초과 시 조정 국면",
        })

    # ── VVIX (CBOE 스냅샷) ────────────────────────────────
    vvix, vvix_prev = _cboe_quote("_VVIX")
    if vvix is None:
        comps.append(_na("vvix", "VVIX (변동성의 변동성)"))
    else:
        chg = _pct(vvix, vvix_prev)
        chg = round(chg, 2) if chg is not None else None
        # VVIX 가중: >105 옵션시장 헤지 수요 확대(+10), >120 변동성 급등 경계(+20).
        # VVIX 는 VIX 옵션의 IV — VIX 급등 '가능성'을 선행 반영하는 경향.
        if vvix > 120:
            pts += 20
            sig = "hot"
        elif vvix > 105:
            pts += 10
            sig = "warn"
        else:
            sig = "calm"
        comps.append({
            "key": "vvix", "label": "VVIX (변동성의 변동성)",
            "value": round(vvix, 2), "change": chg, "signal": sig,
            "detail": f"VVIX {vvix:.1f} (전일 {vvix_prev:.1f}) — 105 초과 시 헤지 수요 확대",
        })

    # ── SPX (CBOE 스냅샷) + 20일선 이격(SPY 캔들 프록시) ──
    spx, spx_prev = _cboe_quote("_SPX")
    spy = _closes(client, "SPY", 30)
    dev = None
    if spy and len(spy) >= 20:
        ma20 = sum(spy[-20:]) / 20.0
        dev = _pct(spy[-1], ma20)
        dev = round(dev, 2) if dev is not None else None
    if spx is None and dev is None:
        comps.append(_na("spx", "S&P500 (20일선)"))
    else:
        chg = _pct(spx, spx_prev) if spx is not None else None
        chg = round(chg, 2) if chg is not None else None
        # SPX 20일선 이격 가중: 20일선 -2% 이상 이탈은 단기 추세 훼손 신호 → +10.
        # (SPX 과거 시계열이 CBOE 에 없어 SPY 캔들로 이격을 계산 — 비율이라 프록시 유효)
        if dev is not None and dev <= -2.0:
            pts += 10
            sig = "hot"
        elif dev is not None and dev < 0:
            sig = "warn"
        else:
            sig = "calm"
        if dev is not None:
            detail = f"20일선 이격 {dev:+.2f}% (SPY 프록시) — -2% 이탈 시 추세 훼손"
        else:
            detail = "20일선 데이터 없음 (지수 스냅샷만 표시)"
        value = round(spx, 2) if spx is not None else round(spy[-1], 2)
        comps.append({
            "key": "spx", "label": "S&P500 (20일선)",
            "value": value, "change": chg, "signal": sig, "detail": detail,
        })

    # ── TLT 실현변동성 (금리충격 · MOVE 프록시) ───────────
    tlt = _closes(client, "TLT", 30)
    rets = None
    if tlt and len(tlt) >= 11:  # 5일 표본 + 비교 기준 최소 5일
        rets = [_pct(tlt[i], tlt[i - 1]) for i in range(1, len(tlt))]
        rets = [r for r in rets if r is not None]
    if not rets or len(rets) < 10:
        comps.append(_na("tlt", "미 국채 TLT (MOVE 프록시)"))
    else:
        vol5 = statistics.pstdev(rets[-5:])       # 최근 5일 일간수익률 표준편차(%/일)
        base = statistics.pstdev(rets[:-5])       # 이전 구간(약 25일) 기준 변동성
        chg5 = _pct(tlt[-1], tlt[-6]) if len(tlt) >= 6 else None
        chg5 = round(chg5, 2) if chg5 is not None else None
        # TLT 실현변동성 가중: 최근 5일 변동성이 이전 구간의 1.5배 이상이면
        # 금리 충격(채권시장 스트레스) 진행 중으로 판단 → +5.
        # MOVE 지수 무료 소스 부재로 실현변동성 프록시 사용(모듈 note 참조).
        hot_vol = base > 0 and vol5 >= base * 1.5
        if hot_vol:
            pts += 5
        sig = "hot" if (base > 0 and vol5 >= base * 2.0) else ("warn" if hot_vol else "calm")
        comps.append({
            "key": "tlt", "label": "미 국채 TLT (MOVE 프록시)",
            "value": round(vol5, 2), "change": chg5, "signal": sig,
            "detail": f"5일 실현변동성 {vol5:.2f}%/일 (이전 {base:.2f}%) — 1.5배 이상이면 금리 충격",
        })

    # ── UUP 달러 (5일 변화) ───────────────────────────────
    uup = _closes(client, "UUP", 30)
    chg5 = _pct(uup[-1], uup[-6]) if uup and len(uup) >= 6 else None
    if chg5 is None:
        comps.append(_na("uup", "달러 UUP"))
    else:
        chg5 = round(chg5, 2)
        # 달러 가중: UUP 5일 +1.5% 이상 급등은 글로벌 유동성 긴축/리스크오프 신호 → +5.
        if chg5 >= 1.5:
            pts += 5
        sig = "calm" if chg5 < 1.5 else ("warn" if chg5 < 3.0 else "hot")
        comps.append({
            "key": "uup", "label": "달러 UUP",
            "value": round(uup[-1], 2), "change": chg5, "signal": sig,
            "detail": f"5일 {chg5:+.2f}% — +1.5% 이상 급등 시 리스크오프 신호",
        })

    # ── HYG 크레딧 (5일 변화) ─────────────────────────────
    hyg = _closes(client, "HYG", 30)
    chg5 = _pct(hyg[-1], hyg[-6]) if hyg and len(hyg) >= 6 else None
    if chg5 is None:
        comps.append(_na("hyg", "하이일드 HYG"))
    else:
        chg5 = round(chg5, 2)
        # 크레딧 가중: HYG 5일 -1.5% 이상 하락은 신용스프레드 확대(위험 회피) 신호 → +10.
        # 주식보다 크레딧이 스트레스를 먼저 반영하는 경향이 있어 가중을 달러보다 높게.
        if chg5 <= -1.5:
            pts += 10
        sig = "calm" if chg5 > -1.5 else ("warn" if chg5 > -3.0 else "hot")
        comps.append({
            "key": "hyg", "label": "하이일드 HYG",
            "value": round(hyg[-1], 2), "change": chg5, "signal": sig,
            "detail": f"5일 {chg5:+.2f}% — -1.5% 이상 하락 시 신용 스트레스",
        })

    # ── 합산 → 단계 (합계 이론상 최대 110 → 0~100 클램프) ─
    score = max(0, min(100, pts))
    stage, emoji, guide = _STAGES[-1][1], _STAGES[-1][2], _STAGES[-1][3]
    for ub, st, em, gd in _STAGES:
        if score < ub:  # 하한 포함·상한 미만: 20→TENSION, 40→COMPRESSION, 60→FRACTURE, 80→TRIGGER
            stage, emoji, guide = st, em, gd
            break
    return {
        "stage": stage, "emoji": emoji, "score": score,
        "generatedAt": time.strftime("%H:%M:%S"),
        "guidance": guide,
        "components": comps,
        "note": MOVE_NOTE,
    }


def get_regime(client):
    """시장 레짐 산출(모듈 캐시). 항상 stage 키를 포함한 dict 를 반환한다.

    전체 실패 시 stage 는 None 일 수 있다(degraded=True) — 절대 STABLE 을
    조작해 내지 않는다. 이전 정상 결과가 있으면 stale=True 로 재사용해
    autopilot 가드가 마지막으로 알려진 단계를 유지하게 한다.
    실패/부분 실패 결과는 단축 TTL 로만 캐시해 고착을 막는다.
    """
    global _cache
    now = time.time()
    with _lock:
        if _cache and now - _cache[0] < _cache[2]:
            return _cache[1]
        prev = _cache[1] if _cache else None

    try:
        result = _build(client)
    except Exception:  # noqa: BLE001 - 방어적: 전체 실패도 루프/서버를 죽이지 않는다
        if isinstance(prev, dict) and prev.get("stage"):
            # 마지막 정상 결과 재사용(stale 표시) — 실제 TRIGGER 중 일시 장애로
            # 가드가 평시(STABLE)로 풀리고 가짜 변화 알림이 나가는 것을 막는다.
            result = dict(prev)
            result["stale"] = True
        else:
            # 이전 결과조차 없음 — stage=None: autopilot 은 실패 경로(가드 일시
            # 해제·스냅샷 유지), 프론트 배너는 숨김(!rg.stage) 으로 처리한다.
            result = {
                "stage": None, "emoji": None, "score": None,
                "degraded": True,
                "generatedAt": time.strftime("%H:%M:%S"),
                "guidance": "레짐 데이터 조회 실패 — 잠시 후 자동 재시도",
                "components": [
                    _na("vix", "VIX (변동성)"), _na("vvix", "VVIX (변동성의 변동성)"),
                    _na("spx", "S&P500 (20일선)"), _na("tlt", "미 국채 TLT (MOVE 프록시)"),
                    _na("uup", "달러 UUP"), _na("hyg", "하이일드 HYG"),
                ],
                "note": MOVE_NOTE,
            }
        with _lock:
            _cache = (time.time(), result, FAIL_TTL)
        return result

    # 부분 실패(소스 다수 강등)면 스코어가 아래로 왜곡된 상태 — TTL 단축해 곧 재시도
    na_count = sum(1 for c in result.get("components", [])
                   if isinstance(c, dict) and c.get("value") is None)
    ttl = DEGRADED_TTL if na_count >= _DEGRADED_NA_MIN else CACHE_TTL
    with _lock:
        _cache = (time.time(), result, ttl)
    return result
