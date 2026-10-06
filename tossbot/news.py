"""경제 뉴스 RSS 수집 + 룰 기반 중요도 스코어링 — 표준 라이브러리만 사용.

소스(모두 이 머신에서 라이브 프로브로 200 확인):
  - 연합뉴스 경제: https://www.yna.co.kr/rss/economy.xml
  - CNBC US Top News: https://www.cnbc.com/id/100003114/device/rss/rss.html
  - MarketWatch Top Stories: http://feeds.marketwatch.com/marketwatch/topstories/
개별 소스가 실패(HTTP 에러/파싱 실패)하면 조용히 스킵 — 최소 연합뉴스만으로도 동작.
"""
from __future__ import annotations

import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# 일부 피드(CNBC 등)는 기본 UA 를 차단하므로 브라우저 UA 필수.
_UA = "Mozilla/5.0"
_TIMEOUT = 10

# (source 표기, URL) — MarketWatch 는 http→https 리다이렉트를 urllib 이 자동 추적.
FEEDS = [
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch", "http://feeds.marketwatch.com/marketwatch/topstories/"),
]

# ── 룰 기반 중요도 ──────────────────────────────────────────
# 각 룰: (가점, 매칭 키워드(소문자), 태그). 영문 소스가 절반이므로 영문 동의어 포함.
_RULES = [
    # +3: 통화정책 — FOMC/연준/금리 관련은 시장 전체를 움직인다.
    (3, ("fomc", "연준", "기준금리", "금리", "fed ", "fed's", "powell", "rate cut",
         "rate hike", "interest rate", "central bank"), "연준"),
    # +3: 핵심 매크로 지표 — CPI/PPI/PCE/고용/실업률/GDP 는 정책 경로를 좌우.
    (3, ("cpi", "ppi", "pce", "고용", "실업률", "gdp", "물가", "인플레이션",
         "inflation", "jobs report", "payroll", "unemployment", "jobless"), "지표"),
    # +2: 통상 리스크 — 관세/무역/제재는 섹터·환율 파급이 크다.
    (2, ("관세", "무역", "제재", "tariff", "trade war", "sanction", "export control"), "지정학"),
    # +2: 지정학 리스크 — 전쟁/미사일/중동 등은 유가·안전자산 반응 유발.
    (2, ("전쟁", "미사일", "중동", "지정학", "우크라", "이란", "war", "missile",
         "middle east", "geopolit", "strike on", "attack"), "지정학"),
    # +2: 기업 실적 — 실적/어닝/가이던스는 개별주·지수 변동 요인.
    (2, ("실적", "어닝", "가이던스", "earnings", "guidance", "quarterly results",
         "profit forecast"), "실적"),
    # +1: 에너지 — 유가/OPEC.
    (1, ("유가", "opec", "원유", "oil price", "crude", "brent"), "에너지"),
    # +1: 반도체 — 시장 주도 섹터(전용 태그 없음 → 태그 미부여).
    (1, ("반도체", "semiconductor", "chipmaker", "chip stocks", "파운드리"), None),
    # +1: 환율 — 원/달러 등 통화 변동.
    (1, ("환율", "원화", "달러화", "엔화", "위안", "forex", "dollar index",
         "currency"), "환율"),
    # -3: 비시장성 노이즈 — 부고/인사/포토/스포츠/연예/날씨는 강등.
    (-3, ("부고", "인사]", "[인사", "포토", "스포츠", "연예", "날씨", "obituary",
          "weather", "sports"), None),
]


def _score_and_tags(title):
    """제목 한 건의 (score 0~10, tags, important) 계산 — 위 _RULES 합산."""
    low = title.lower()
    score, tags = 0, []
    for pts, keywords, tag in _RULES:
        if any(k in low for k in keywords):
            score += pts
            if pts > 0 and tag and tag not in tags:
                tags.append(tag)
    score = max(0, min(10, score))  # 0~10 클램프
    if not tags:
        tags = ["기타"]
    return score, tags, score >= 5


def _fetch_feed(source, url):
    """RSS 1개 피드를 파싱해 item dict 리스트 반환. 실패 시 빈 리스트."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept": "application/rss+xml, application/xml, */*"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title:
            continue
        # pubDate(RFC 822) → 로컬 시각. 실패해도 항목은 유지(정렬 키만 0).
        ts, time_str = 0.0, ""
        pub = (it.findtext("pubDate") or "").strip()
        if pub:
            try:
                dt = parsedate_to_datetime(pub)
                ts = dt.timestamp()
                time_str = dt.astimezone().strftime("%m-%d %H:%M")
            except Exception:
                time_str = pub[:22]
        out.append({"title": title, "link": link, "source": source,
                    "time": time_str, "_ts": ts})
    return out


def _dedup(items):
    """제목 유사 중복 제거: 공백 제거·소문자 후 한쪽이 다른쪽에 부분 일치하면 중복."""
    kept, keys = [], []
    for it in items:
        norm = "".join(it["title"].split()).lower()
        if not norm:
            continue
        if any(norm in k or k in norm for k in keys):
            continue  # 먼저 온(더 최신) 항목을 유지
        keys.append(norm)
        kept.append(it)
    return kept


def fetch_news():
    """뉴스 수집 결과.

    반환: {"generatedAt", "items":[{"title","link","source","time",
           "score"(0~10),"tags":[str],"important":bool}... 최신 40건]}
    """
    raw = []
    for source, url in FEEDS:
        try:
            raw.extend(_fetch_feed(source, url))
        except Exception:
            # 개별 소스 실패는 조용히 스킵 — 나머지 소스로 계속.
            continue

    # 최신순 정렬 → 유사 중복 제거 → 상위 40건.
    # 연합뉴스가 회당 120건을 내보내 영문 소스를 밀어내므로 소스당 20건으로 캡하고,
    # 40건 미달 시 캡에 걸려 제외된 항목으로 최신순 백필한다.
    raw.sort(key=lambda it: it["_ts"], reverse=True)
    deduped = _dedup(raw)
    picked, overflow, per_src = [], [], {}
    for it in deduped:
        if len(picked) >= 40:
            break
        n = per_src.get(it["source"], 0)
        if n >= 20:
            overflow.append(it)
            continue
        per_src[it["source"]] = n + 1
        picked.append(it)
    if len(picked) < 40:
        picked.extend(overflow[:40 - len(picked)])
        picked.sort(key=lambda it: it["_ts"], reverse=True)

    items = []
    for it in picked:
        score, tags, important = _score_and_tags(it["title"])
        items.append({"title": it["title"], "link": it["link"],
                      "source": it["source"], "time": it["time"],
                      "score": score, "tags": tags, "important": important})

    return {"generatedAt": time.strftime("%H:%M:%S"), "items": items}
