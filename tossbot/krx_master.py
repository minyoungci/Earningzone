"""종목 검색 마스터 — stock_master.json(한국·미국 전 종목)이 있으면 사용, 없으면 큐레이션 폴백.

전체 마스터는 `python build_master.py` 로 생성. 목록에 없는 종목도 백엔드가 코드로 토스 라이브 검증.
"""
from __future__ import annotations
import json
import os
import unicodedata

from . import config

_HERE = os.path.dirname(os.path.abspath(__file__))
_MASTER_JSON = os.path.join(_HERE, "stock_master.json")

# 폴백(전체 마스터 미생성 시) — KOSPI 유니버스 + 주요 KOSDAQ
_CURATED = [(s, n, "KOSPI") for s, n in config.KOSPI_UNIVERSE] + [
    ("247540", "에코프로비엠", "KOSDAQ"), ("086520", "에코프로", "KOSDAQ"),
    ("196170", "알테오젠", "KOSDAQ"), ("028300", "HLB", "KOSDAQ"),
    ("058470", "리노공업", "KOSDAQ"), ("240810", "원익IPS", "KOSDAQ"),
    ("005290", "동진쎄미켐", "KOSDAQ"), ("039030", "이오테크닉스", "KOSDAQ"),
    ("293490", "카카오게임즈", "KOSDAQ"), ("263750", "펄어비스", "KOSDAQ"),
    ("112040", "위메이드", "KOSDAQ"), ("066970", "엘앤에프", "KOSDAQ"),
    ("022100", "포스코DX", "KOSDAQ"), ("277810", "레인보우로보틱스", "KOSDAQ"),
    ("145020", "휴젤", "KOSDAQ"), ("214150", "클래시스", "KOSDAQ"),
    ("041510", "에스엠", "KOSDAQ"), ("035900", "JYP Ent.", "KOSDAQ"),
    ("357780", "솔브레인", "KOSDAQ"), ("348370", "엔켐", "KOSDAQ"),
    ("095340", "ISC", "KOSDAQ"), ("036930", "주성엔지니어링", "KOSDAQ"),
]


def _load():
    if os.path.exists(_MASTER_JSON):
        try:
            with open(_MASTER_JSON, encoding="utf-8") as f:
                data = json.load(f)
            return [(s, n, m) for s, n, m in data if s and n]
        except Exception:
            pass
    return _CURATED


MASTER = _load()


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


# 검색 가속용 사전 정규화 인덱스
_INDEX = [(s, n, m, s.lower(), _nfc(n.lower())) for s, n, m in MASTER]

# 흔한 한글 약칭/별칭 (공식 종목명과 달라도 검색되도록)
_ALIASES = {
    "네이버": "035420", "현대차": "005380", "기아차": "000270", "포스코": "005490",
    "포스코홀딩스": "005490", "하이닉스": "000660", "엘지화학": "051910",
    "엘지엔솔": "373220", "엘지에너지솔루션": "373220", "삼성바이오": "207940", "삼바": "207940",
    "삼전": "005930", "엘지전자": "066570", "한전": "015760", "카페이": "377300",
    "삼성에스디아이": "006400", "에스케이": "034730", "현대중공업": "329180",
    "현대모비스": "012330", "케이비": "105560",
}
_by_sym = {s: (n, m) for s, n, m in MASTER}
_INDEX += [(sym, _by_sym[sym][0], _by_sym[sym][1], sym.lower(), _nfc(al.lower()))
           for al, sym in _ALIASES.items() if sym in _by_sym]


def stats():
    from collections import Counter
    return {"total": len(MASTER), **dict(Counter(m for _, _, m in MASTER))}


def search(q: str, limit: int = 20):
    q = _nfc((q or "").strip().lower())
    if not q:
        return []
    exact, starts, contains = [], [], []
    for sym, name, mkt, sl, nl in _INDEX:
        if q == sl or q == nl:
            exact.append((sym, name, mkt))
        elif sl.startswith(q) or nl.startswith(q):
            starts.append((sym, name, mkt))
        elif q in sl or q in nl:
            contains.append((sym, name, mkt))
        if len(exact) + len(starts) >= limit and len(contains) >= limit:
            break
    seen, uniq = set(), []
    for s, n, m in exact + starts + contains:
        if s in seen:
            continue
        seen.add(s)
        uniq.append({"symbol": s, "name": n, "market": m})
        if len(uniq) >= limit:
            break
    return uniq
