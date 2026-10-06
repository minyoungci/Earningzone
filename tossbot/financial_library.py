"""Original public engineering articles. Private study material is never served."""
from functools import lru_cache
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs" / "public"
DOCUMENT_FILES = ("README.md", "ANALYSIS_PIPELINE.md", "CHART_METHODS.md",
                  "TRADING_POLICY.md", "RISK_AND_BACKTEST.md", "DATA_AND_LIMITS.md")
DOCUMENT_DATE = "2026-10-06"

METHODS = [
    {"id": "structure", "title": "가격 구조 · 확인 피벗", "mode": "차트 자동 계산", "docs": ["CHART_METHODS"], "description": "꼬리/몸통 기준 HH·HL·LH·LL. 좌우 2–10봉으로 확인 시점을 따로 기록합니다.", "limits": "마지막 우측 봉이 부족하면 피벗 미확정. 추세 전환과 주문 신호는 별개입니다."},
    {"id": "retest", "title": "지지·저항 · 돌파와 리테스트", "mode": "차트 자동 계산", "docs": ["CHART_METHODS", "TRADING_POLICY"], "description": "확인 피벗 ± ATR14×0.25 구간. 돌파 → 후속 봉 리테스트 → 추가 종가 확인 → 무효화를 추적합니다.", "limits": "반폭 0.25, 대기 20봉은 구현 휴리스틱. 검증된 성공률이나 거래 권고가 아닙니다."},
    {"id": "divergence", "title": "RSI · MACD 다이버전스", "mode": "차트 자동 계산", "docs": ["CHART_METHODS", "TRADING_POLICY"], "description": "같은 두 확인 피벗의 가격과 RSI14·MACD line을 비교하고 후보/무효를 구분합니다.", "limits": "지표가 뒤집혀도 가격 확인이 필요합니다. MACD 히스토그램과 line은 다른 값입니다."},
    {"id": "volume", "title": "거래량 · 갭 · 변동성", "mode": "차트 자동 계산", "docs": ["CHART_METHODS", "DATA_AND_LIMITS"], "description": "직전 20봉 대비 RVOL, 방향 거래량 대리값, 큰 음봉+거래량 반복, 갭/ATR와 종가 위치를 표시합니다.", "limits": "분봉 RVOL은 동일 시간대 비교가 아닙니다. OHLCV만으로 기관 수급이나 실적 갭을 확정하지 않습니다."},
    {"id": "geometry", "title": "피보나치 · 측정 목표 · 추세선", "mode": "수동 시나리오", "docs": ["CHART_METHODS"], "description": "직접 지정한 가격·봉 앵커로 되돌림, 삼각형 높이/더블탑·바텀 목표와 추세선을 차트에 겹칩니다.", "limits": "사용자가 지정한 앵커의 계산 결과입니다. 자동 패턴 판정이나 검증된 목표가가 아닙니다."},
    {"id": "em", "title": "예상 변동폭", "mode": "수동 입력 계산", "docs": ["CHART_METHODS", "DATA_AND_LIMITS"], "description": "현 가격 × 연율 IV × √(기간/연간 기준). 달력일365/거래일252를 명시합니다.", "limits": "만기별 실시간 IV 피드는 미연결. 직접 입력한 가정 범위이며 터치·종가 확률을 보장하지 않습니다."},
    {"id": "risk", "title": "초기 위험 · 수량 · 순손익비", "mode": "수동 입력 계산", "docs": ["RISK_AND_BACKTEST", "TRADING_POLICY"], "description": "진입·손절·목표와 환율, 예산, 현금, 위험 비율, 비용을 함께 계산합니다.", "limits": "주식 롱 시나리오. 수동 입력은 자동매매 계좌 정책에 저장되지 않습니다."},
    {"id": "context", "title": "매크로 · 옵션 · 복기 방법", "mode": "구현 설명", "docs": ["ANALYSIS_PIPELINE", "DATA_AND_LIMITS", "RISK_AND_BACKTEST"], "description": "종목 점수, 시장 레짐, 옵션 데이터와 모의매매 검증의 범위를 설명합니다.", "limits": "시장 폭·옵션 방향·실적 서프라이즈는 별도 피드가 필요합니다. 점수와 기본 임계값은 검증된 확률이 아닙니다."},
]


@lru_cache(maxsize=1)
def resources():
    docs, bodies = [], {}
    # Never discover arbitrary local files or fall back to the private archive.
    for rel in DOCUMENT_FILES:
        path = ROOT / rel
        body = path.read_text(encoding="utf-8")
        key = path.stem
        title = next((s.lstrip("# ") for s in body.splitlines() if s.startswith("# ")), key)
        docs.append({"id": key, "path": rel, "title": title, "kind": "guide",
                     "sourceUrl": None, "modifiedAt": None,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "sameBodyAs": None})
        bodies[key] = body
    return docs, bodies, {}, {}, DOCUMENT_DATE


def library(query=""):
    docs, bodies, _, _, snapshot = resources()
    q = query.strip().casefold()
    selected = [d for d in docs if not q or q in (d["title"] + " " + bodies[d["id"]]).casefold()]
    return {"snapshot": snapshot, "visibility": "public", "documents": selected, "methods": METHODS,
            "counts": {"guides": len(docs), "sources": 0, "images": 0}, "images": []}


def document(key):
    docs, bodies, *_ = resources()
    if key not in bodies:
        raise KeyError(key)
    return {**next(d for d in docs if d["id"] == key), "content": bodies[key]}


def image_path(key):
    raise KeyError(key)
