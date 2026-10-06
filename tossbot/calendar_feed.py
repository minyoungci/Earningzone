"""경제지표·실적 캘린더 피드 — Nasdaq 공개 캘린더 API 기반 (표준 라이브러리만 사용).

소스(무료·API 키 불필요, User-Agent 헤더 필수 — 없으면 차단됨):
- 실적:  GET https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD
         data.rows: [{symbol, name, time, epsForecast, marketCap, ...}]
         time 값은 "time-pre-market" | "time-after-hours" | "time-not-supplied".
- 지표:  GET https://api.nasdaq.com/api/calendar/economicevents?date=YYYY-MM-DD
         data.rows: [{gmt("HH:MM"), country, eventName, actual, consensus, previous, description}]

위 키 이름은 2026-07-05 이 머신에서 라이브 응답으로 직접 확인한 실제 키다.
(합의치는 문서상 'forecast'가 아니라 'consensus', 시각은 'gmt'.)
응답에 중요도(importance) 필드는 없으므로 이벤트명 키워드 룰로 자체 산출한다.

계약: get_calendar(days=7) -> {
  "generatedAt": "HH:MM:SS",
  "earnings": [{"date","symbol","name","time"}...],
  "econ":     [{"date","time","event","country","importance","actual","forecast","previous"}...],
}
- 오늘부터 days 일 반복 조회(주말은 스킵), 실패한 날짜는 조용히 스킵.
- econ 은 country 가 United States/미국인 항목을 앞에, 나머지를 뒤에 배치.
- 요청 간 0.3s 대기(무료 엔드포인트 예의 + 차단 회피).
"""
from __future__ import annotations
import datetime
import html
import json
import time
import urllib.parse
import urllib.request

# Nasdaq 엣지는 기본 'Python-urllib' UA 를 차단하므로 브라우저 UA 필수.
USER_AGENT = "Mozilla/5.0"
BASE = "https://api.nasdaq.com/api/calendar"
REQUEST_DELAY_SEC = 0.3   # 연속 요청 간 대기(초)
TIMEOUT_SEC = 10

# ── 지표 중요도 룰 (Nasdaq 응답에 중요도 필드가 없어 이벤트명 키워드로 산출) ──
# high  : 시장 전체를 움직이는 1급 이벤트(연준·물가·고용·성장률)
# medium: 방향성 참고용 2급 지표(심리·주택·PMI·재고 등)
# low   : 그 외
_HIGH_KEYWORDS = (
    "fomc", "fed interest rate", "federal funds", "interest rate decision",
    "cpi", "ppi", "pce", "nonfarm", "non-farm", "unemployment rate",
    "gdp", "retail sales", "ism manufacturing", "ism non-manufacturing",
    "ism services", "employment",
)
_MEDIUM_KEYWORDS = (
    "pmi", "jobless claims", "consumer confidence", "michigan",
    "housing", "home sales", "building permits", "durable goods",
    "trade balance", "crude oil", "industrial production", "jolts",
    "adp", "consumer sentiment", "opec",
)


def _importance(event_name):
    """이벤트명 키워드 → "high"|"medium"|"low" (룰 근거는 위 주석 참고)."""
    name = (event_name or "").lower()
    for kw in _HIGH_KEYWORDS:
        if kw in name:
            return "high"
    for kw in _MEDIUM_KEYWORDS:
        if kw in name:
            return "medium"
    return "low"


def _get_json(url):
    """UA 를 붙여 JSON GET. 실패는 예외로 올려 호출부에서 날짜 단위로 스킵."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
        return json.load(r)


def _clean(v):
    """Nasdaq 값 정리: HTML 엔티티(&nbsp; 등) 해제 + 공백 정리 → 빈 값은 ""."""
    if v is None:
        return ""
    s = html.unescape(str(v)).replace("\xa0", " ").strip()
    return s


def _earnings_time(v):
    """"time-pre-market" → "pre-market" 식으로 접두어 제거(미공급은 "")."""
    s = _clean(v)
    if s.startswith("time-"):
        s = s[len("time-"):]
    return "" if s == "not-supplied" else s


def _fetch_earnings(date_str):
    """해당 날짜 실적 발표 목록. rows 가 null 인 날(발표 없음)은 빈 리스트."""
    j = _get_json(BASE + "/earnings?" + urllib.parse.urlencode({"date": date_str}))
    rows = (j.get("data") or {}).get("rows") or []
    out = []
    for r in rows:
        sym = _clean(r.get("symbol"))
        if not sym:
            continue
        out.append({
            "date": date_str,
            "symbol": sym,
            "name": _clean(r.get("name")),
            "time": _earnings_time(r.get("time")),
        })
    return out


def _fetch_econ(date_str):
    """해당 날짜 경제지표 목록. 실제 키: gmt/country/eventName/actual/consensus/previous."""
    j = _get_json(BASE + "/economicevents?" + urllib.parse.urlencode({"date": date_str}))
    rows = (j.get("data") or {}).get("rows") or []
    out = []
    for r in rows:
        event = _clean(r.get("eventName"))
        if not event:
            continue
        out.append({
            "date": date_str,
            "time": _clean(r.get("gmt")),          # 응답 키 'gmt' == 발표 시각(HH:MM)
            "event": event,
            "country": _clean(r.get("country")),
            "importance": _importance(event),
            "actual": _clean(r.get("actual")),
            "forecast": _clean(r.get("consensus")),  # 합의치 키는 'consensus'
            "previous": _clean(r.get("previous")),
        })
    return out


def get_calendar(days=7):
    """오늘부터 days 일치 실적/지표 캘린더 수집.

    - 주말(토·일) 날짜는 조회 자체를 스킵(미국 시장 휴장·데이터 거의 없음).
    - 특정 날짜/엔드포인트 실패는 조용히 스킵(부분 결과 반환).
    - econ 은 미국(United States) 항목 우선 + 나머지 뒤에 (각 그룹 내 날짜·시각순 유지).
    """
    try:
        days = max(1, min(int(days), 14))  # 과도한 조회 방지(서버 계약과 동일 1..14)
    except (TypeError, ValueError):
        days = 7

    today = datetime.date.today()
    earnings = []
    econ_us = []
    econ_other = []

    for i in range(days):
        d = today + datetime.timedelta(days=i)
        if d.weekday() >= 5:   # 5=토, 6=일 → 주말 스킵
            continue
        date_str = d.isoformat()

        # 실적 — 실패한 날짜는 조용히 스킵
        try:
            earnings.extend(_fetch_earnings(date_str))
        except Exception:
            pass
        time.sleep(REQUEST_DELAY_SEC)

        # 지표 — 실패한 날짜는 조용히 스킵
        try:
            for item in _fetch_econ(date_str):
                # 미국 항목 우선 배치(연합 RSS 등 국문 소스 대비 '미국' 표기도 허용)
                if item["country"] in ("United States", "미국"):
                    econ_us.append(item)
                else:
                    econ_other.append(item)
        except Exception:
            pass
        time.sleep(REQUEST_DELAY_SEC)

    return {
        "generatedAt": time.strftime("%H:%M:%S"),
        "earnings": earnings,
        "econ": econ_us + econ_other,
    }
