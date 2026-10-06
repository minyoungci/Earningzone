"""매크로 시장 반응 보드 — 미국 ETF·KODEX200·달러/원 환율 스냅샷.

데이터 소스: 토스 Open API(client.candles / client.exchange_rate)만 사용.
DXY·채권금리·유가 등 '지수' 자체는 무료 실시간 소스가 없어 미국 상장 ETF 로 대체한다:
  SPY(S&P500) QQQ(나스닥100) IWM(러셀2000) TLT(미국채20년+) HYG(하이일드)
  UUP(달러인덱스) GLD(금) USO(유가) — 모두 토스 캔들 API 로 조회 가능(라이브 프로브 확인).
한국은 069500(KODEX 200, KRW).

표준 라이브러리만 사용.
"""
from __future__ import annotations

import time

# 보드 항목 정의: (key, 토스 심볼, 한국어 라벨, 기본 통화)
# 통화는 캔들 응답의 currency 필드가 있으면 그 값을 우선 사용한다.
UNIVERSE = [
    ("spy",    "SPY",    "S&P500",     "USD"),
    ("qqq",    "QQQ",    "나스닥100",   "USD"),
    ("iwm",    "IWM",    "러셀2000",    "USD"),
    ("tlt",    "TLT",    "미국채20년+", "USD"),
    ("hyg",    "HYG",    "하이일드",    "USD"),
    ("uup",    "UUP",    "달러인덱스",  "USD"),
    ("gld",    "GLD",    "금",         "USD"),
    ("uso",    "USO",    "유가",       "USD"),
    ("kodex200", "069500", "KODEX200",  "KRW"),
]


def _f(v):
    """느슨한 float 변환 — 실패 시 None."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(new, old):
    """등락률(%) — 분모 0/None 이면 None."""
    if new is None or old is None or old == 0:
        return None
    return round((new / old - 1.0) * 100.0, 2)


def _closes_asc(res):
    """candles 응답(최신순)에서 종가 리스트를 시간 오름차순으로 추출."""
    candles = res.get("candles", []) if isinstance(res, dict) else []
    closes, currency = [], None
    # 토스 캔들은 최신순으로 오므로 뒤집어 과거→현재 순으로 만든다.
    for c in reversed(candles or []):
        cl = _f(c.get("closePrice"))
        if cl is None:
            continue
        closes.append(cl)
        currency = c.get("currency", currency)
    return closes, currency


def get_board(client):
    """시장 반응 보드 스냅샷.

    반환: {"generatedAt", "items":[{"key","symbol","label","price","currency",
           "chg1d","chg5d","spark":[최근20 종가]}...]}
    개별 종목 조회 실패는 값 None 으로 항목을 유지한다(보드 구조 불변).
    """
    items = []
    for key, symbol, label, base_ccy in UNIVERSE:
        item = {"key": key, "symbol": symbol, "label": label,
                "price": None, "currency": base_ccy,
                "chg1d": None, "chg5d": None, "spark": []}
        try:
            # 종목당 1회 호출: 일봉 25개면 가격/1일/5일 등락 + 스파크 20개가 모두 나온다.
            res = client.candles(symbol, "1d", 25)
            closes, currency = _closes_asc(res)
            if closes:
                item["price"] = closes[-1]
                item["currency"] = currency or base_ccy
                if len(closes) >= 2:
                    item["chg1d"] = _pct(closes[-1], closes[-2])
                if len(closes) >= 6:
                    # 5일 전(6번째 마지막) 종가 대비 등락.
                    item["chg5d"] = _pct(closes[-1], closes[-6])
                item["spark"] = [float(v) for v in closes[-20:]]
        except Exception:
            # 실패 종목도 None 값으로 포함 — 프런트 타일이 자리 유지.
            pass
        items.append(item)

    # 달러/원 환율 — 캔들이 아닌 exchange-rate 엔드포인트 단건.
    usdkrw = {"key": "usdkrw", "symbol": None, "label": "달러/원",
              "price": None, "currency": "KRW",
              "chg1d": None, "chg5d": None, "spark": []}
    try:
        usdkrw["price"] = client.exchange_rate("USD", "KRW")
    except Exception:
        pass
    items.append(usdkrw)

    return {"generatedAt": time.strftime("%H:%M:%S"), "items": items}


def reaction_summary(items):
    """|1일 등락| 상위 2~3개를 언급하는 한국어 한 줄 요약."""
    movers = [it for it in items
              if isinstance(it.get("chg1d"), (int, float)) and it.get("key") != "usdkrw"]
    if not movers:
        return "시장 데이터가 부족해 반응 요약을 만들 수 없습니다."
    movers.sort(key=lambda it: abs(it["chg1d"]), reverse=True)
    top = movers[:3]
    parts = "·".join(f"{it['label']} {it['chg1d']:+.1f}%" for it in top)

    # 톤 판정: 주가지수(SPY/QQQ/IWM) 방향으로 리스크온/오프를 판단.
    eq = [it["chg1d"] for it in movers if it["key"] in ("spy", "qqq", "iwm")]
    if eq and all(v > 0 for v in eq):
        tone = "위험자산 선호(리스크온) 흐름"
    elif eq and all(v < 0 for v in eq):
        tone = "위험회피(리스크오프) 기울기"
    else:
        tone = "혼조 속 종목별 차별화"

    # 최상위 변동 자산 기준 발원지 코멘트(예: 에너지發·달러發).
    lead = top[0]
    origin = {"uso": "에너지發 ", "uup": "달러發 ", "tlt": "금리發 ",
              "hyg": "크레딧發 ", "gld": "안전자산發 "}.get(lead["key"], "")
    return f"지금 시장이 반응 중: {parts} — {origin}{tone}"
