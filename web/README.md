# tossbot 웹 (Glass 대시보드)

토스증권 Open API 기반 KOSPI 분석 엔진(tossbot, 94전략)을 **글래스모피즘 웹 대시보드**로 시각화.

스택: **FastAPI**(백엔드) + **React + Vite + Tailwind + Framer Motion + lightweight-charts**(프론트).

## 실행 (터미널 2개)

```bash
# 0) 키는 환경변수로만 (백엔드 쪽에서만 사용 — 프론트로 노출 안 됨)
export TOSS_CLIENT_ID=tsck_live_xxx
export TOSS_CLIENT_SECRET=tssk_live_xxx
export TOSS_DRY_RUN=1

# 1) 백엔드 (D:/toss 에서)
python -m uvicorn server.app:app --app-dir D:/toss --host 127.0.0.1 --port 8000

# 2) 프론트 (D:/toss/web 에서)
npm install        # 최초 1회
npm run dev        # http://localhost:5173
```

브라우저에서 **http://localhost:5173** 접속.

## 화면
- **대시보드** (`/`): 워치리스트 카드(종합 시그널·점수 게이지) + 스크리너 랭킹/히트맵
- **종목 상세** (`/symbol/:symbol`): 캔들차트(SMA20/60·거래량) + 종합점수 + 94전략 시그널 보드 + 지표 그리드 + 다이버전스/패턴/지지저항
- **인트라데이** (`/intraday`): 1분봉 차트 + VWAP + 종목 칩 + 인트라데이 시그널
- **포트폴리오** (`/portfolio`): 페이퍼 트레이딩 상태(`run.py --paper`로 생성)

## API (FastAPI, :8000)
`/api/health` · `/api/watchlist` · `/api/analyze/{symbol}` · `/api/candles/{symbol}` · `/api/intraday/{symbol}` · `/api/screener` · `/api/portfolio`

> 분석/시그널은 교육용 휴리스틱이며 투자 권유가 아닙니다. DRY_RUN 기본(주문 없음).
