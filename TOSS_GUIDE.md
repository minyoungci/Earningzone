# 토스증권(Toss Securities) Open API 통합 가이드 — TOSS_GUIDE

> **과거 시점의 참고 문서입니다.** 아래 내용은 2026-06-21 명세·관측 기록을 보존합니다. 현재 REST 명세는 2026-10-06 확인 시 1.2.19이며 허용 IP·인증 조건 등이 달라졌습니다. 연동을 시작할 때는 [Earningzone의 현재 연동 안내](README.ko.md#토스증권-api-연동)와 [최신 공식 명세](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json)를 기준으로 확인하세요.

> 토스증권 Open API 공식 명세(`developers.tossinvest.com`, OpenAPI **v1.1.1**)를 정독하여 정리한 통합 가이드입니다.
> 작성일: **2026-06-21** · 정본(Source of Truth): `https://openapi.tossinvest.com/openapi-docs/latest/openapi.json` · 본 가이드의 인증·엔드포인트는 **실제 라이브 키로 연결 검증을 마친 내용**입니다.
> (토스페이먼츠 관련 내용은 별도 파일 [TOSS_PAYMENTS_GUIDE.md](TOSS_PAYMENTS_GUIDE.md) 로 분리 보관)

---

## 0. 30초 요약

| 항목 | 값 |
| :-- | :-- |
| **Base URL** | `https://openapi.tossinvest.com` |
| **기능** | 국내(KRX)·미국 주식의 **시세·종목정보·환율·시장정보·계좌·보유주식·주문** REST API |
| **인증** | OAuth 2.0 **Client Credentials Grant** → `POST /oauth2/token` |
| **클라이언트 자격** | `client_id` = 클라이언트 키(`tsck_live_…`), `client_secret` = 시크릿 키(`tssk_live_…`) |
| **호출 인증 헤더** | `Authorization: Bearer {access_token}` (모든 API 필수) |
| **계좌 식별 헤더** | `X-Tossinvest-Account: {accountSeq}` (계좌·자산·**주문** 카테고리 필수) |
| **토큰 수명** | `expires_in` 약 86400초(24h) · refresh token 없음 · **client당 유효 토큰 1개**(재발급 시 이전 토큰 즉시 무효) |
| **발급 위치** | 토스증권 WTS 로그인 → `설정 > Open API` |
| **mTLS/IP allowlist** | 불필요 (표준 OAuth2) |
| **지원 상품 범위** | 국내(KR)·미국(US) **현물 주식** 및 ETF·ETN·REIT·DR·인프라펀드·ELW(`STOCK_WARRANTS`). **옵션·선물 등 파생상품 거래는 미지원** (계좌도 `BROKERAGE` 위탁매매만 노출) |

> ✅ **연결 검증 완료 (2026-06-21, 실제 라이브 키)**: `POST /oauth2/token` → **200**(Bearer, `expires_in:86399`, JWT에 `tier:"BASIC"` claim) → `GET /api/v1/stocks?symbols=005930`(삼성전자/KOSPI/KRW), `GET /api/v1/prices?symbols=005930`(현재가 **350,500원**, 2026-06-19 종가), `GET /api/v1/market-calendar/KR`(세션시간), `GET /api/v1/accounts`(BROKERAGE 계좌 1개) 모두 **200**. ※`tier` 는 토큰 JWT에서 관측된 값이며 공식 명세 문서에는 정의돼 있지 않습니다.

### 검증된 퀵스타트

```bash
# 1) 토큰 발급 — client_id/secret 은 Basic 헤더(-u) 또는 본문 둘 다 가능
curl -s -X POST 'https://openapi.tossinvest.com/oauth2/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -u 'tsck_live_…:tssk_live_…' \
  -d 'grant_type=client_credentials'
# → {"access_token":"<JWT>","token_type":"Bearer","expires_in":86399}

# 2) 시세·종목 호출 (토큰만)
curl -s 'https://openapi.tossinvest.com/api/v1/prices?symbols=005930' \
  -H 'Authorization: Bearer <JWT>'

# 3) 계좌·자산·주문 호출 (토큰 + 계좌 헤더)
curl -s 'https://openapi.tossinvest.com/api/v1/holdings' \
  -H 'Authorization: Bearer <JWT>' -H 'X-Tossinvest-Account: 1'
```

> ⚠️ **안전 주의**: `POST /api/v1/orders`(주문 생성)·`/modify`(정정)·`/cancel`(취소)는 **실거래가 발생**합니다. 자동화 시 소액·검증 후 운영하고, 시세/조회는 read-only라 안전합니다. 라이브 키는 외부 노출 금지(노출 시 재발급).

---

## 목차

1. [개요 · 인증 · 공통 규격 (가장 중요)](#개요--인증--공통-규격-가장-중요) — 토큰 발급, 헤더, Rate Limits, 에러 모델/코드
2. [시세 (Market Data)](#시세-market-data) — 호가·현재가·체결·상하한가·캔들
3. [종목정보 · 시장정보 (Stock & Market Info)](#종목정보--시장정보-stock--market-info) — 종목 마스터·유의사항·환율·장 운영 캘린더
4. [계좌 · 자산 (Account & Asset)](#계좌--자산-account--asset) — 계좌·보유주식·매수가능금액·판매가능수량·수수료
5. [주문 (Order) — ⚠️ 거래성 API](#주문-order--️-거래성-api) — 생성·정정·취소·조회

---


## 개요 · 인증 · 공통 규격 (가장 중요)

토스증권 Open API(공식 명세 버전 `1.1.1`)는 국내·미국 주식의 시세·종목 정보, 환율, 장 운영 시간 등 시장 데이터와 본인 계좌의 보유 주식·주문을 다루는 **REST API** 입니다. 모든 호출은 OAuth 2.0 액세스 토큰을 요구하며, 계좌·자산·주문 호출은 계좌 식별 헤더를 추가로 요구합니다.

### Base URL · 공통 규격

| 항목 | 값 |
|---|---|
| Base URL (서버) | `https://openapi.tossinvest.com` |
| 프로토콜 | REST API only |
| 인증 방식 | OAuth 2.0 Client Credentials Grant |
| 토큰 엔드포인트 | `POST /oauth2/token` |
| 호출 인증 헤더 | `Authorization: Bearer {access_token}` (모든 API 필수) |
| 계좌 식별 헤더 | `X-Tossinvest-Account: {accountSeq}` (계좌·자산·주문 카테고리 필수) |
| 토큰 요청 Content-Type | `application/x-www-form-urlencoded` |

API 카테고리는 **인증(Auth) · 시세·종목 정보(Market Data/Stock Info/Market Info) · 계좌·자산(Account/Asset) · 주문(Order/Order History/Order Info)** 네 가지입니다. 시세·종목 정보는 OAuth 토큰만으로 호출 가능하고, 계좌·자산 및 주문은 토큰 + `X-Tossinvest-Account` 가 모두 필요합니다.

#### 시작하기 (퀵스타트)

1. **클라이언트 등록** — 토스증권 WTS 로그인 후 `설정 > Open API` 에서 `client_id` 와 `client_secret` 을 발급받습니다.
2. **액세스 토큰 발급** — `POST /oauth2/token` 으로 Client Credentials Grant access token 을 발급받습니다.
3. **API 호출** — 토큰을 `Authorization: Bearer {access_token}` 헤더에 담아 호출합니다. 계좌·자산 및 주문은 `X-Tossinvest-Account: {accountSeq}` 헤더도 함께 전달합니다.

#### 공통 인증 헤더

| 헤더 | 필수 | 적용 범위 | 설명 |
|---|---|---|---|
| `Authorization: Bearer {access_token}` | 필수 | 모든 API | `/oauth2/token` 으로 발급받은 JWT access token. 누락 시 401 `edge-blocked`. |
| `X-Tossinvest-Account: {accountSeq}` | 조건부 필수 | 계좌·자산·주문 | 사용할 계좌의 `accountSeq`(정수, int64). `GET /api/v1/accounts` 응답의 `accountSeq` 값을 사용. 누락 시 400 `account-header-required`. |

> `accountSeq` 는 `integer`(format `int64`) 타입이며 헤더에 정수 문자열로 전달합니다. (예: `X-Tossinvest-Account: 1`)

### 인증 — OAuth 2.0 토큰 발급

#### `POST /oauth2/token` — 액세스 토큰 발급

OAuth 2.0 Client Credentials Grant 방식으로 access token 을 발급합니다. **Rate Limits Group**: `AUTH`. 이 엔드포인트는 자체 인증으로 발급을 수행하므로 `Authorization` 헤더가 필요 없습니다(`security: []`).

핵심 규칙(원문):
- 요청 본문은 `application/x-www-form-urlencoded` 으로 전송합니다.
- 발급된 token 은 다른 모든 API 의 `Authorization: Bearer {access_token}` 헤더에 사용합니다.
- 이 엔드포인트의 응답은 공통 envelope 이 아닌 **OAuth2 표준 형식**입니다.
- **refresh token 은 제공하지 않습니다.** 만료 시 토큰 엔드포인트로 재발급합니다.
- **client 당 유효한 access token 은 1 개입니다.** 재발급 시 이전 token 은 즉시 무효화됩니다.

**요청 본문 (`OAuth2TokenRequest`, form-urlencoded)**

| 필드 | 타입 | 필수 | 설명 / 허용 값 |
|---|---|---|---|
| `grant_type` | string | 필수 | 인증 방식. ENUM: `client_credentials` (유일) |
| `client_id` | string | 필수 | 발급받은 클라이언트 ID (예: `c_01HXYZABCDEFG123456789`) |
| `client_secret` | string (password) | 필수 | 발급받은 클라이언트 시크릿. 서버 측에서만 사용(노출 금지) |

> 표준 OAuth2 에 따라 `client_id`/`client_secret` 은 본문 대신 HTTP **Basic 인증 헤더**로도 전달할 수 있습니다. 인증 실패(401) 응답에는 `WWW-Authenticate: Basic realm="openapi"` 챌린지 헤더가 포함됩니다.

**응답 (200, `OAuth2TokenResponse`, `application/json`)**

| 필드 | 타입 | 필수 | 설명 / 값 |
|---|---|---|---|
| `access_token` | string | 필수 | JWT 형식 access token. 모든 API 요청의 `Authorization: Bearer` 헤더에 사용 |
| `token_type` | string | 필수 | 토큰 타입. ENUM: `Bearer` (항상 `Bearer`) |
| `expires_in` | integer (int64) | 필수 | 토큰 만료까지 남은 초 (예시: `86400`) |

**에러 응답 (OAuth2 표준 포맷, `OAuth2ErrorResponse`)**

`/oauth2/token` 은 공통 `ErrorResponse` envelope 이 아닌 OAuth2 표준 포맷으로 응답하므로, 클라이언트는 `code` 가 아닌 **`error` 필드**로 에러를 식별해야 합니다.

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `error` | string | 필수 | 에러 코드. ENUM: `invalid_request`, `invalid_client`, `invalid_grant`, `unauthorized_client`, `unsupported_grant_type` |
| `error_description` | string | 선택 | 에러 상세 설명. 메시지에 non-ASCII 문자가 포함되면 생략될 수 있음 |
| `error_uri` | string (uri) | 선택 | 에러 정보가 게시된 페이지 URI |

| HTTP Status | `error` | 발생 이유 |
|---|---|---|
| 400 | `invalid_request` | 필수 파라미터 누락 / 요청 형식 오류 |
| 400 | `unsupported_grant_type` | `client_credentials` 외 grant_type 요청 |
| 401 | `invalid_client` | `client_id`/`client_secret` 오류 또는 클라이언트 비활성 (응답에 `WWW-Authenticate: Basic realm="openapi"` 포함) |
| 429 | (공통 envelope) | `AUTH` 그룹 Rate limit 초과 → 공통 `ErrorResponse`(`code: rate-limit-exceeded`)로 응답 |

**최소 curl 예시 (토큰 발급)**

```bash
curl -s -X POST 'https://openapi.tossinvest.com/oauth2/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials' \
  -d 'client_id=c_01HXYZABCDEFG123456789' \
  -d 'client_secret=s_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
```

응답 예시:

```json
{
  "access_token": "eyJraWQiOiIyMDI2LTA0LTAxLWtleSIsImFsZyI6IlJTMjU2In0...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

**발급한 토큰으로 호출 (예시)**

```bash
# 시세·종목 정보 (토큰만 필요)
curl -s 'https://openapi.tossinvest.com/api/v1/stocks?symbols=005930' \
  -H 'Authorization: Bearer eyJhbGciOi...'

# 계좌·자산 / 주문 (토큰 + 계좌 헤더)
curl -s 'https://openapi.tossinvest.com/api/v1/holdings' \
  -H 'Authorization: Bearer eyJhbGciOi...' \
  -H 'X-Tossinvest-Account: 1'
```

### Rate Limits

모든 API 는 **클라이언트 × API 그룹** 단위로 초당 요청 수(TPS)가 제한됩니다. 각 API description 끝에 해당 API 의 Rate Limits Group 이 표기됩니다. 한도 수치는 운영 상황에 따라 사전 공지 없이 조정될 수 있으며, 현재 허용 한도는 응답 헤더 `X-RateLimit-Limit` 로 확인합니다.

| Rate Limits Group | 요청 한도 | 피크시간 한도 |
|---|---|---|
| `AUTH` | 초당 최대 5회 | -- |
| `ACCOUNT` | 초당 최대 1회 | -- |
| `ASSET` | 초당 최대 5회 | -- |
| `STOCK` | 초당 최대 5회 | -- |
| `MARKET_INFO` | 초당 최대 3회 | -- |
| `MARKET_DATA` | 초당 최대 10회 | -- |
| `MARKET_DATA_CHART` | 초당 최대 5회 | -- |
| `ORDER` | 초당 최대 6회 | 09:00~09:10 KST: 초당 최대 3회 |
| `ORDER_HISTORY` | 초당 최대 5회 | -- |
| `ORDER_INFO` | 초당 최대 6회 | 09:00~09:10 KST: 초당 최대 3회 |

#### Rate Limit 응답 헤더

정상 응답과 429 응답 모두에 다음 헤더가 포함됩니다(`Retry-After` 는 429 응답에만 포함).

| 헤더 | 타입 | 의미 |
|---|---|---|
| `X-RateLimit-Limit` | integer | 현재 허용된 초당 요청 수 (burst capacity) |
| `X-RateLimit-Remaining` | integer | 버킷에 남은 토큰 수 (429 시 `0`) |
| `X-RateLimit-Reset` | integer | 토큰 1개 재충전까지 예상 초 |
| `Retry-After` | integer | 재시도 권장 초 (429 응답에만 포함) |

#### 429 대응 권장 사항

- 429 수신 시 `Retry-After` 헤더 값만큼 대기 후 재시도합니다.
- 지수 백오프(1s → 2s → 4s …)와 jitter 를 함께 적용합니다.
- `X-RateLimit-Remaining` 이 낮아질 때 클라이언트 측에서 요청 속도를 선제적으로 완화합니다.

429 본문은 공통 `ErrorResponse` envelope 으로 내려갑니다(`code`: `rate-limit-exceeded`, 또는 엣지단 `edge-rate-limit-exceeded`):

```json
{
  "error": {
    "requestId": "01HXYZABCDEFG123456789",
    "code": "rate-limit-exceeded",
    "message": "요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
  }
}
```

### 공통 에러 규격 (Error Envelope)

`/oauth2/token` 을 제외한 모든 엔드포인트의 4xx/5xx 응답은 공통 `ErrorResponse` envelope 으로 내려갑니다. (성공 응답은 별도 `ApiResponse` 스키마 사용.)

**`ErrorResponse` / `ApiError` 필드**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `error` | object (`ApiError`) | 필수 | 에러 객체 |
| `error.requestId` | string | 필수 | 요청 식별 고유 ID. 응답 헤더 `X-Request-Id` 와 동일. CS 문의 시 첨부 권장. 누락 시 응답 헤더 `cf-ray` 값을 첨부 |
| `error.code` | string | 필수 | 에러 코드(flat string 식별자, 예: `invalid-request`, `order-not-found`). 클라이언트는 **unknown code 를 허용**하도록 구현 |
| `error.message` | string | 필수 | 사용자 노출 가능 메시지. 빈 문자열일 수 있으므로 `code` 기반 자체 매핑 권장 |
| `error.data` | object \| null | 선택 | 에러 해결 힌트. 코드별로 포함 여부·키 구조 상이, 없으면 필드 생략 |

**`error.data` 표준 키 (camelCase, 코드별 서브셋만 포함)**

| 키 | 타입 | 설명 |
|---|---|---|
| `field` | string | 검증 실패 필드명(외부 노출명: body JSON key 또는 query param). 복수는 쉼표 구분 (예: `"quantity,orderAmount"`) |
| `allowedValues` | string[] | enum 후보 값 전체 |
| `allowedConditions` | object | 조건부 허용 규칙 (`marketCountry`/`orderType`/`side` 등) |
| `constraint` | object | 필드 제약 (`min`/`max`/`integerOnly`/`step`) |
| `format` | string | 포맷 규칙명 (예: `decimal`) |
| `pattern` | string | 정규식 |
| `maxLength` | number | 문자열 길이 상한 |
| `limits` | object | 금액/수량 한도 (`threshold`/`minimum`/`maximum` + `currency`) |
| `retryAfterAt` | string | 절대 재시도 시각 (ISO 8601 offset, KST) |
| `retryAfterSeconds` | number | 상대 재시도 시각(초) |
| `tickSize` | string | 호가 단위 |
| `nearestPrices` | string[] | 근접 유효 가격 (`[lower, upper]`) |

에러 envelope 예시:

```json
{
  "error": {
    "requestId": "01HXYZABCDEFG123456789",
    "code": "invalid-request",
    "message": "주문 방향이 올바르지 않습니다.",
    "data": { "field": "side", "allowedValues": ["BUY", "SELL"] }
  }
}
```

#### 공통 에러 코드 표 (전체)

| HTTP Status | 에러 코드 | 발생 이유 |
|---|---|---|
| 400 BAD_REQUEST | `invalid-request` | 요청이 유효하지 않음(호가 유형·주문 방향·수량·금액·필수 파라미터 누락 등) |
| 400 BAD_REQUEST | `confirm-high-value-required` | 주문 금액 1억원 이상인데 `confirmHighValueOrder` 가 `true` 가 아님 |
| 400 BAD_REQUEST | `account-header-required` | `X-Tossinvest-Account` 헤더 미전달 |
| 401 UNAUTHORIZED | `invalid-token` | 토큰이 유효하지 않거나 형식 오류 |
| 401 UNAUTHORIZED | `edge-blocked` | `Authorization` 헤더 미전달 |
| 401 UNAUTHORIZED | `expired-token` | 액세스 토큰 만료 |
| 401 UNAUTHORIZED | `login-user-not-found` | 토큰에 대응하는 로그인 정보 없음 |
| 403 FORBIDDEN | `edge-blocked` | 허용되지 않은 요청 |
| 403 FORBIDDEN | `forbidden` | 요청에 필요한 권한 부족 |
| 404 NOT_FOUND | `edge-blocked` | 지원하지 않는 API 경로 |
| 404 NOT_FOUND | `stock-not-found` | 요청한 종목 없음 |
| 404 NOT_FOUND | `exchange-rate-not-found` | 환율 정보 없음 |
| 404 NOT_FOUND | `account-not-found` | `X-Tossinvest-Account` 가 가리키는 계좌 없음 |
| 404 NOT_FOUND | `order-not-found` | `orderId` 에 해당하는 주문 없음 |
| 409 CONFLICT | `request-in-progress` | 동일 `clientOrderId` 주문 생성 요청 처리 중 |
| 409 CONFLICT | `already-filled` | 정정/취소 대상 주문이 이미 체결됨 |
| 409 CONFLICT | `already-canceled` | 정정/취소 대상 주문이 이미 취소됨 |
| 409 CONFLICT | `already-modified` | 정정/취소 대상 주문이 이미 정정됨 |
| 409 CONFLICT | `already-rejected` | 정정/취소 대상 주문이 이미 거부됨 |
| 409 CONFLICT | `already-processing` | 동일 주문에 대한 정정/취소가 이미 처리 중 |
| 422 UNPROCESSABLE_ENTITY | `insufficient-buying-power` | 주문 가능 금액 부족 |
| 422 UNPROCESSABLE_ENTITY | `order-hours-closed` | 주문(생성/정정/취소) 접수 불가 시간 |
| 422 UNPROCESSABLE_ENTITY | `stock-restricted` | 종목 거래 제한 상태 |
| 422 UNPROCESSABLE_ENTITY | `price-out-of-range` | 주문 가격이 상/하한가 범위 초과 |
| 422 UNPROCESSABLE_ENTITY | `opposite-pending-order-exists` | 동일 종목 반대 방향 체결 대기 주문 존재 |
| 422 UNPROCESSABLE_ENTITY | `order-type-not-allowed` | 현재 사용 불가한 호가 유형 |
| 422 UNPROCESSABLE_ENTITY | `prerequisite-required` | 약관 동의·위험 고지 등 사전 자격 요건 미충족 |
| 422 UNPROCESSABLE_ENTITY | `market-not-supported-for-stock` | 해당 종목은 요청 시장에서 거래 불가 (KR) |
| 422 UNPROCESSABLE_ENTITY | `investor-exchange-not-integrated` | 투자자지시 거래소 설정이 통합(SOR) 아님 (KR) |
| 422 UNPROCESSABLE_ENTITY | `amount-order-outside-regular-hours` | 금액 주문은 정규장에만 가능 (US) |
| 422 UNPROCESSABLE_ENTITY | `modify-restricted` | 해당 주문 정정 제한 |
| 422 UNPROCESSABLE_ENTITY | `cancel-restricted` | 해당 주문 취소 제한 |
| 429 TOO_MANY_REQUESTS | `edge-rate-limit-exceeded` | Rate limit 초당 요청 수 초과 |
| 429 TOO_MANY_REQUESTS | `rate-limit-exceeded` | Rate limit 초당 요청 수 초과 |
| 500 INTERNAL_SERVER_ERROR | `internal-error` | 서버 일시 장애 |
| 500 INTERNAL_SERVER_ERROR | `maintenance` | 시스템 점검 중 |

> 참고: 공식 OpenAPI 명세(`openapi.json` v1.1.1) 및 `overview.md` 에는 `tier`(BASIC 등) 개념이 정의되어 있지 않습니다. 인증·권한은 클라이언트 단위 OAuth2 토큰과 `X-Tossinvest-Account` 헤더로만 규정됩니다.


## 시세 (Market Data)

종목의 실시간성 시세 정보(호가, 현재가, 체결, 상·하한가, 캔들 OHLCV)를 조회하는 API 그룹입니다. 사용자 계좌와 무관한 객관적 데이터이므로 **OAuth 2.0 액세스 토큰만으로 호출 가능**합니다. (계좌 식별 헤더 `X-Tossinvest-Account` 는 필요 없음 — 해당 헤더는 계좌·자산·주문 API에서만 사용)

### 공통 사항

| 항목 | 내용 |
|------|------|
| Base URL | `https://openapi.tossinvest.com` |
| 인증 헤더 | `Authorization: Bearer {access_token}` (모든 호출 필수) |
| 계좌 헤더 | 불필요 (시세 API는 계좌와 무관) |
| Rate Limits Group | `MARKET_DATA` (초당 최대 10회) — 호가·현재가·체결·상하한가 / `MARKET_DATA_CHART` (초당 최대 5회) — 캔들 |
| 응답 envelope | 성공(200) 시 `{ "result": ... }`, 실패(4xx/5xx) 시 `{ "error": { requestId, code, message, data } }`. `result` 와 `error` 는 동시에 내려가지 않음 |
| 금액·수량 타입 | 가격·잔량·거래량 등 수치 필드는 모두 **문자열(string, format decimal, maxLength 30)** 로 내려옴. 부동소수점 오차 방지를 위해 문자열/Decimal 로 파싱 권장 |
| 통화 ENUM (`Currency`) | `KRW` (한국 원화), `USD` (미국 달러). 클라이언트는 unknown enum 값도 허용하도록 구현 권장 |

#### symbol 파라미터 규칙

- **`symbol`** (단건 조회용, 호가·체결·상하한가·캔들): 종목 심볼 1개. KRX는 6자리 숫자(예: `005930`), US는 영문 티커(예: `AAPL`). 패턴 `^[A-Za-z0-9.\-]+$` — 영문 대/소문자, 숫자, `.`, `-` 허용. **필수.**
- **`symbols`** (배치 조회용, 현재가 전용): 콤마로 구분한 종목 심볼 목록(예: `005930,000660`). 패턴 `^[A-Za-z0-9.,\-]+$`. 1개 이상 최대 200개. **필수.**

#### 공통 에러 응답

| HTTP Status | 에러 코드 | 발생 이유 |
|------|------|------|
| 400 BAD_REQUEST | `invalid-request` | 필수 파라미터 누락, 잘못된 값(예: 미지원 캔들 간격, `symbols` 개수 1~200 초과) |
| 404 NOT_FOUND | `stock-not-found` | 요청한 종목을 찾을 수 없음 |
| 429 TOO_MANY_REQUESTS | `rate-limit-exceeded` | 초당 요청 수 초과. `Retry-After` 헤더만큼 대기 후 재시도 |
| 500 INTERNAL_SERVER_ERROR | `internal-error` | 시세 조회 중 일시 장애 |

> Rate limit 관련 응답 헤더: `X-RateLimit-Limit`(현재 허용 초당 요청 수), `X-RateLimit-Remaining`(남은 토큰 수, 429 시 0), `X-RateLimit-Reset`(토큰 1개 재충전 예상 초), `Retry-After`(재시도 권장 초, 429 응답에만 포함).

---

### 호가 조회

종목의 실시간 매도·매수 호가 잔량을 조회합니다.

`GET /api/v1/orderbook`

**요청 — 쿼리 파라미터**

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:---:|------|
| `symbol` | query | string | ✅ | 종목 심볼 (단건). 예: `005930`, `AAPL` |

**요청 — 헤더**

| 헤더 | 필수 | 값 |
|------|:---:|------|
| `Authorization` | ✅ | `Bearer {access_token}` |

**응답 — `result` (OrderbookResponse)**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `timestamp` | string \| null (date-time) | | 데이터 시각. 데이터가 없으면 null. 예: `2026-03-25T09:30:00.123+09:00` |
| `currency` | string (ENUM `KRW`/`USD`) | ✅ | 통화 코드 |
| `asks` | array&lt;OrderbookEntry&gt; | ✅ | 매도호가 목록 (낮은 가격순) |
| `bids` | array&lt;OrderbookEntry&gt; | ✅ | 매수호가 목록 (높은 가격순) |

**OrderbookEntry**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `price` | string (decimal) | ✅ | 호가 |
| `volume` | string (decimal) | ✅ | 잔량 |

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/orderbook?symbol=005930' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (KR)**

```json
{
  "result": {
    "timestamp": "2026-03-25T09:30:00.123+09:00",
    "currency": "KRW",
    "asks": [
      { "price": "72300", "volume": "1200" },
      { "price": "72200", "volume": "3400" },
      { "price": "72100", "volume": "8500" }
    ],
    "bids": [
      { "price": "72000", "volume": "5200" },
      { "price": "71900", "volume": "4100" },
      { "price": "71800", "volume": "2700" }
    ]
  }
}
```

---

### 현재가 조회

여러 종목의 현재가(마지막 체결가)를 한 번에 조회합니다. (배치 조회 지원)

`GET /api/v1/prices`

**요청 — 쿼리 파라미터**

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:---:|------|
| `symbols` | query | string | ✅ | 콤마 구분 종목 심볼 목록 (1~200개). 예: `005930,000660` |

**응답 — `result` (array&lt;PriceResponse&gt;)**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `symbol` | string | ✅ | 종목 심볼. 예: `005930` |
| `timestamp` | string \| null (date-time) | | 데이터 시각. 체결 미발생 등으로 시각이 없으면 null |
| `lastPrice` | string (decimal) | ✅ | 현재가(마지막 체결가) |
| `currency` | string (ENUM `KRW`/`USD`) | ✅ | 통화 코드 |

**에러 (추가)**

| HTTP Status | 에러 코드 | data | 발생 이유 |
|------|------|------|------|
| 400 | `invalid-request` | `field: symbols`, `constraint: { min: 1, max: 200 }` | `symbols` 개수가 허용 범위를 벗어남 |

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/prices?symbols=005930,000660' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (US)**

```json
{
  "result": [
    {
      "symbol": "AAPL",
      "timestamp": "2026-03-25T22:30:00.456+09:00",
      "lastPrice": "185.70",
      "currency": "USD"
    }
  ]
}
```

---

### 최근 체결 내역 조회

종목의 최근 체결 내역을 조회합니다.

`GET /api/v1/trades`

**요청 — 쿼리 파라미터**

| 이름 | 위치 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|------|------|------|:---:|------|------|------|
| `symbol` | query | string | ✅ | — | — | 종목 심볼 (단건) |
| `count` | query | integer | | `50` | 1 ~ 50 | 조회 건수 (최대 50) |

**응답 — `result` (array&lt;Trade&gt;)**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `price` | string (decimal) | ✅ | 체결가 |
| `volume` | string (decimal) | ✅ | 체결 수량 |
| `timestamp` | string (date-time) | ✅ | 체결 시각 |
| `currency` | string (ENUM `KRW`/`USD`) | ✅ | 통화 코드 |

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/trades?symbol=005930&count=3' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (KR)**

```json
{
  "result": [
    { "price": "72000", "volume": "120", "timestamp": "2026-03-25T09:30:42.000+09:00", "currency": "KRW" },
    { "price": "71900", "volume": "50",  "timestamp": "2026-03-25T09:30:41.500+09:00", "currency": "KRW" },
    { "price": "72000", "volume": "200", "timestamp": "2026-03-25T09:30:40.800+09:00", "currency": "KRW" }
  ]
}
```

---

### 상/하한가 조회

종목의 당일 상한가·하한가를 조회합니다.

`GET /api/v1/price-limits`

**요청 — 쿼리 파라미터**

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|:---:|------|
| `symbol` | query | string | ✅ | 종목 심볼 (단건) |

**응답 — `result` (PriceLimitResponse)**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `timestamp` | string (date-time) | ✅ | 데이터 시각 |
| `upperLimitPrice` | string \| null (decimal) | | 상한가. 미국 주식 등 상하한가가 없는 시장에서는 null |
| `lowerLimitPrice` | string \| null (decimal) | | 하한가. 미국 주식 등 상하한가가 없는 시장에서는 null |
| `currency` | string (ENUM `KRW`/`USD`) | ✅ | 통화 코드 |

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/price-limits?symbol=005930' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (KR / US)**

```json
{ "result": { "timestamp": "2026-03-25T09:30:00.123+09:00", "upperLimitPrice": "93000", "lowerLimitPrice": "50400", "currency": "KRW" } }
```
```json
{ "result": { "timestamp": "2026-03-25T22:30:00.456+09:00", "upperLimitPrice": null, "lowerLimitPrice": null, "currency": "USD" } }
```

---

### 캔들 차트 조회

종목의 캔들(OHLCV) 차트 데이터를 조회합니다. 한 번 호출에 **최대 200개**를 반환하며, `before` / `nextBefore` 로 과거 방향 페이징합니다. 다른 시세 API와 달리 `MARKET_DATA_CHART` Rate Limits Group(초당 최대 5회)으로 관리됩니다.

`GET /api/v1/candles`

**요청 — 쿼리 파라미터**

| 이름 | 위치 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|------|------|------|:---:|------|------|------|
| `symbol` | query | string | ✅ | — | — | 종목 심볼 (단건) |
| `interval` | query | string (ENUM) | ✅ | — | `1m` \| `1d` | 봉 간격. `1m`=1분봉, `1d`=일봉 |
| `count` | query | integer | | `100` | 1 ~ 200 | 조회할 봉 수 (최대 200) |
| `before` | query | string (date-time) | | — | ISO 8601 | 페이지네이션 커서 (exclusive). 이 시각보다 이전 봉을 반환. 생략 시 가장 최신부터 반환. 다음 페이지 요청 시 이전 응답의 `nextBefore` 값을 그대로 전달 |
| `adjusted` | query | boolean | | `true` | — | 수정주가 적용 여부. `true`=수정주가 반영, `false`=미반영 |

**응답 — `result` (CandlePageResponse)**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `candles` | array&lt;Candle&gt; | ✅ | 캔들 목록 (최신 → 과거 순) |
| `nextBefore` | string \| null (date-time) | | 다음 페이지 조회 시 `before` 쿼리 파라미터에 그대로 전달. 마지막 페이지면 null |

**Candle**

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `timestamp` | string (date-time) | ✅ | 봉 시작 시각 |
| `openPrice` | string (decimal) | ✅ | 시가 |
| `highPrice` | string (decimal) | ✅ | 고가 |
| `lowPrice` | string (decimal) | ✅ | 저가 |
| `closePrice` | string (decimal) | ✅ | 종가 |
| `volume` | string (decimal) | ✅ | 거래량 |
| `currency` | string (ENUM `KRW`/`USD`) | ✅ | 통화 코드 |

**에러 (추가)**

| HTTP Status | 에러 코드 | data | 발생 이유 |
|------|------|------|------|
| 400 | `invalid-request` | `field: interval`, `allowedValues: ["1m","1d"]` | 지원하지 않는 캔들 간격 |

**curl 예시 (일봉, 최신 50개)**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/candles?symbol=005930&interval=1d&count=50' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**curl 예시 (1분봉, 페이징 — 이전 페이지의 nextBefore 사용)**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/candles?symbol=005930&interval=1m&before=2026-03-25T09:31:00%2B09:00' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (일봉)**

```json
{
  "result": {
    "candles": [
      { "timestamp": "2026-03-25T09:00:00+09:00", "openPrice": "71600", "highPrice": "72300", "lowPrice": "71500", "closePrice": "72000", "volume": "3521000", "currency": "KRW" },
      { "timestamp": "2026-03-24T09:00:00+09:00", "openPrice": "71200", "highPrice": "71800", "lowPrice": "71000", "closePrice": "71600", "volume": "2984000", "currency": "KRW" }
    ],
    "nextBefore": "2026-03-24T09:00:00+09:00"
  }
}
```

> 페이징 종료: 마지막 페이지에서는 `nextBefore` 가 `null` 로 내려옵니다. 이를 루프 종료 조건으로 사용하세요.


## 종목정보 · 시장정보 (Stock & Market Info)

종목 마스터, 매수 유의사항, 환율, 장 운영 캘린더를 조회하는 객관적 시장 데이터 API입니다. 사용자 계좌와 무관한 정보이므로 **OAuth 2.0 액세스 토큰만으로 호출 가능**하며, 별도의 `X-Tossinvest-Account` 헤더는 필요하지 않습니다(계좌·자산·주문 API에만 필요).

### 공통 사항

- **Base URL**: `https://openapi.tossinvest.com`
- **인증 헤더**: 모든 호출에 `Authorization: Bearer {access_token}` 필요. (계좌·자산·주문 API는 추가로 `X-Tossinvest-Account: {accountSeq}` 필요 — 본 섹션 API에는 불필요)
- **응답 envelope**: 성공 시 `{ "result": ... }` (`ApiResponse`), 실패 시 `{ "error": { requestId, code, message, data? } }` (`ErrorResponse`).
- **시각 표기**: 모든 일시(`date-time`)는 ISO 8601 offset 형식이며 캘린더·환율의 시각은 **KST(+09:00)** 기준.
- **decimal 필드**: 정밀도 보존을 위해 숫자형 값(`sharesOutstanding`, `rate`, `midRate` 등)은 문자열(`string`, `format: decimal`)로 내려갑니다.
- **unknown enum 허용**: 클라이언트는 `warningType`, `code`, `currency` 등에서 명세에 없는 신규 값이 내려와도 처리 가능하도록 구현해야 합니다.

#### Rate Limits (본 섹션 관련 그룹)

| Rate Limits Group | 적용 API | 요청 한도 |
|---|---|---|
| `STOCK` | `/api/v1/stocks`, `/api/v1/stocks/{symbol}/warnings` | 초당 최대 5회 |
| `MARKET_INFO` | `/api/v1/exchange-rate`, `/api/v1/market-calendar/KR`, `/api/v1/market-calendar/US` | 초당 최대 3회 |

응답 헤더 `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset` 으로 현재 한도를 확인하고, 429 수신 시 `Retry-After` 헤더 값만큼 대기 후 재시도합니다.

#### 공통 에러 코드

| HTTP | code | 의미 |
|---|---|---|
| 400 | `invalid-request` | 요청 파라미터가 유효하지 않음 (필드 정보는 `data.field`) |
| 400 | `unsupported-date` | 지원하지 않는 조회 날짜 (캘린더) |
| 401 | `invalid-token` / `expired-token` / `login-user-not-found` / `edge-blocked` | 인증 실패. 401 응답에는 `WWW-Authenticate: Bearer ...` 헤더 동반 |
| 403 | `forbidden` / `edge-blocked` | 권한 부족 |
| 404 | `stock-not-found` | 종목을 찾을 수 없음 |
| 404 | `exchange-rate-not-found` | 환율 정보를 찾을 수 없음 |
| 429 | `rate-limit-exceeded` / `edge-rate-limit-exceeded` | 요청 한도 초과 |
| 500 | `internal-error` / `maintenance` | 서버 일시 장애 / 점검 중 |

---

### GET /api/v1/stocks — 종목 기본 정보 조회

종목 마스터(종목명·영문명·ISIN·시장·통화·상장상태·발행주식수·국내 시장 상세)를 `symbols` 콤마 구분으로 **최대 200개 일괄 조회**합니다. Rate Limits Group: `STOCK`.

**요청**

| 위치 | 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| Header | `Authorization` | string | 필수 | `Bearer {access_token}` |
| Query | `symbols` | string (`^[A-Za-z0-9.,\-]+$`) | **필수** | 종목 심볼. 콤마로 구분해 최대 200개. 예: `005930` 또는 `005930,AAPL`. 영문 대/소문자·숫자·`.`·`-` 허용 |

**응답** — `result`: `StockInfo[]`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `symbol` | string | 필수 | 종목 심볼 (예: `005930`, `AAPL`) |
| `name` | string | 필수 | 종목명 (한글) |
| `englishName` | string | 필수 | 영문 종목명 |
| `isinCode` | string | 필수 | 국제증권식별번호 (ISO 6166, 예: `KR7005930003`) |
| `market` | string enum | 필수 | 상장 시장. `KOSPI`·`KOSDAQ`·`NYSE`·`NASDAQ`·`AMEX`·`KR_ETC`·`US_ETC`. 시장 세그먼트 단위 (warnings의 `exchange`와 추상화 수준 다름) |
| `securityType` | string enum | 필수 | 종목 유형. `STOCK`·`FOREIGN_STOCK`·`DEPOSITARY_RECEIPT`·`INFRASTRUCTURE_FUND`·`REIT`·`ETF`·`FOREIGN_ETF`·`ETN`·`STOCK_WARRANTS` |
| `isCommonShare` | boolean | 필수 | 보통주 여부 (우선주는 `false`) |
| `status` | string enum | 필수 | 상장 상태. `SCHEDULED`·`ACTIVE`·`DELISTED` |
| `currency` | string enum | 필수 | 통화. `KRW`·`USD` (`Currency`) |
| `listDate` | string\|null | 선택 | 상장일 (YYYY-MM-DD, KST). 미제공 시 null |
| `delistDate` | string\|null | 선택 | 상장폐지일 (YYYY-MM-DD, KST). 활성 종목은 null |
| `sharesOutstanding` | string (decimal) | 필수 | 발행주식수 (maxLength 30) |
| `leverageFactor` | string\|null (decimal) | 선택 | 레버리지 배수. ETF/ETN에만 적용 (`1`, `2.0`, `-1.0` 등). 해당 없으면 null |
| `koreanMarketDetail` | `KrMarketDetail`\|null | 선택 | 국내 시장 상세. 국내 종목(KOSPI·KOSDAQ·KR_ETC)에만 제공, 해외 종목은 null |

**`koreanMarketDetail` (`KrMarketDetail`) 필드**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `liquidationTrading` | boolean | 필수 | 정리매매 여부 (상장폐지 절차 진행 중) |
| `nxtSupported` | boolean | 필수 | NXT 대체거래소 지원 여부 |
| `krxTradingSuspended` | boolean | 필수 | KRX 거래정지 여부 |
| `nxtTradingSuspended` | boolean\|null | 선택 | NXT 거래정지 여부. NXT 미지원 종목(`nxtSupported=false`)은 null |

**에러**: 400 `invalid-request` (심볼 1~200개 초과 시 `data.field=symbols`, `constraint:{min:1,max:200}`), 401, 403, 429, 500 `internal-error`.

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/stocks?symbols=005930,AAPL' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (발췌)**

```json
{
  "result": [
    {
      "symbol": "005930", "name": "삼성전자", "englishName": "SamsungElec",
      "isinCode": "KR7005930003", "market": "KOSPI", "securityType": "STOCK",
      "isCommonShare": true, "status": "ACTIVE", "currency": "KRW",
      "listDate": "1975-06-11", "delistDate": null,
      "sharesOutstanding": "5919637922", "leverageFactor": null,
      "koreanMarketDetail": {
        "liquidationTrading": false, "nxtSupported": true,
        "krxTradingSuspended": false, "nxtTradingSuspended": false
      }
    }
  ]
}
```

---

### GET /api/v1/stocks/{symbol}/warnings — 매수 유의사항 조회

종목의 매수 유의사항 및 변동성 완화장치(VI) 발동 정보를 조회합니다. Rate Limits Group: `STOCK`.

- **활성 판단(시간 기준)**: 현재 일자 기준 `startDate <= 오늘 <= endDate` 항목 (또는 `endDate`가 null인 진행 중 항목).
- **정렬**: `startDate` 내림차순(최근 발동순). `startDate`가 없으면 정렬 순서 보장 안 됨.
- **반영 지연**: VI 발동/해제는 체결 이벤트 발생 시 즉시, 정리매매·단기과열·투자경고/위험은 거래일 단위로 일배치 반영.
- **종목 없음 vs 빈 배열**: 미존재 종목은 `404 stock-not-found`, 존재하지만 활성 유의사항이 없으면 `200 OK` + `result: []`.

**요청**

| 위치 | 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| Header | `Authorization` | string | 필수 | `Bearer {access_token}` |
| Path | `symbol` | string (`^[A-Za-z0-9.\-]+$`) | **필수** | 종목 심볼. KRX 6자리 숫자(예: `005930`) / US 영문 티커(예: `AAPL`) |

**응답** — `result`: `StockWarning[]`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `warningType` | string enum | 필수 | 유의사항 유형 (아래 표) |
| `exchange` | string\|null | 선택 | 거래소 코드 (`KRX`·`NXT` 등 물리적 거래소 단위). `market`과 추상화 수준 다름. 거래소 무관 경고는 null |
| `startDate` | string\|null | 선택 | 적용 시작일 (inclusive, YYYY-MM-DD, KST). 미정 시 null |
| `endDate` | string\|null | 선택 | 적용 종료일 (inclusive, YYYY-MM-DD, KST). 진행 중/미정 시 null |

**`warningType` ENUM**

| 값 | 의미 |
|---|---|
| `LIQUIDATION_TRADING` | 정리매매 (상장폐지 절차 진행 중) |
| `OVERHEATED` | 단기과열종목 지정 |
| `INVESTMENT_WARNING` | 투자경고종목 지정 |
| `INVESTMENT_RISK` | 투자위험종목 지정 |
| `VI_STATIC_AND_DYNAMIC` | 변동성 완화장치(VI) 정적 + 동적 동시 발동 |
| `VI_STATIC` | 변동성 완화장치(VI) 정적 발동 |
| `VI_DYNAMIC` | 변동성 완화장치(VI) 동적 발동 |
| `STOCK_WARRANTS` | 신주인수권증서/증권 |

**에러**: 401, 403, 404 `stock-not-found`, 429, 500 `internal-error`.

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/stocks/005930/warnings' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시**

```json
{
  "result": [
    { "warningType": "OVERHEATED", "exchange": "KRX", "startDate": "2026-03-20", "endDate": "2026-03-27" },
    { "warningType": "VI_STATIC",  "exchange": "KRX", "startDate": "2026-03-26", "endDate": null }
  ]
}
```

---

### GET /api/v1/exchange-rate — 환율 조회

KRW↔USD 환율 정보를 조회합니다. Rate Limits Group: `MARKET_INFO`.

- **갱신 주기 1분**, 정보성 표준 환율. 실제 주문 시 적용되는 거래 환율과 다를 수 있음.
- `dateTime` 미지정 시 **현재 시점의 유효 환율** 반환.
- 응답의 `validFrom` ~ `validUntil` 은 해당 환율의 **유효 시간 구간**(보통 1분).

**요청**

| 위치 | 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| Header | `Authorization` | string | 필수 | `Bearer {access_token}` |
| Query | `baseCurrency` | enum (`Currency`) | **필수** | 기준 통화. `KRW`·`USD` |
| Query | `quoteCurrency` | enum (`Currency`) | **필수** | 표시 통화 (quote currency). `KRW`·`USD` |
| Query | `dateTime` | string (date-time) | 선택 | 조회할 환율 시각. 특정 시점 환율 조회 (예: `2026-03-25T09:30:00+09:00`) |

**응답** — `result`: `ExchangeRateResponse`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `baseCurrency` | enum | 필수 | 기준 통화 (`Currency`) |
| `quoteCurrency` | enum | 필수 | 표시 통화 (`Currency`) |
| `rate` | string (decimal) | 필수 | 매수 환율 (1 baseCurrency = ? quoteCurrency) |
| `midRate` | string (decimal) | 필수 | 매매기준율 (은행간 mid rate) |
| `basisPoint` | string (decimal) | 필수 | 매매기준율 대비 basis points = `(rate - midRate) / midRate * 10000` |
| `rateChangeType` | string enum | 필수 | 등락 구분. `UP`·`EQUAL`·`DOWN` |
| `validFrom` | string (date-time) | 필수 | 환율 유효 시작 시각 |
| `validUntil` | string (date-time) | 필수 | 환율 유효 종료 시각 |

**에러**: 400 `invalid-request` (지원하지 않는 통화 → `data.allowedValues:["KRW","USD"]`; 기준·표시 통화 동일 → `data.field="baseCurrency,quoteCurrency"`), 404 `exchange-rate-not-found`, 429, 500 `internal-error`.

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시**

```json
{
  "result": {
    "baseCurrency": "USD", "quoteCurrency": "KRW",
    "rate": "1380.5", "midRate": "1375", "basisPoint": "40",
    "rateChangeType": "UP",
    "validFrom": "2026-03-25T09:30:00+09:00",
    "validUntil": "2026-03-25T09:31:00+09:00"
  }
}
```

---

### GET /api/v1/market-calendar/KR — 국내 장 운영 정보

국내 종목의 거래 가능 시간을 조회합니다. **통합 모드(KRX+NXT)** 기준이며, 특수장(시간외종가/시간외단일가)은 제외됩니다. 오늘/이전/다음 3영업일 정보를 반환하고, 모든 시각은 KST(+09:00). Rate Limits Group: `MARKET_INFO`.

**요청**

| 위치 | 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| Header | `Authorization` | string | 필수 | `Bearer {access_token}` |
| Query | `date` | string (date, `YYYY-MM-DD`) | 선택 | 조회 기준일. 미지정 시 현재일 |

**응답** — `result`: `KrMarketCalendarResponse`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `today` | `KrMarketDay` | 필수 | 기준일 정보 |
| `previousBusinessDay` | `KrMarketDay` | 필수 | 직전 영업일 |
| `nextBusinessDay` | `KrMarketDay` | 필수 | 다음 영업일 |

**`KrMarketDay` 필드**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `date` | string (date) | 필수 | 영업일 (KST) |
| `integrated` | `IntegratedHour`\|null | 선택 | 거래 가능 시간(통합 KRX+NXT). 휴장일이면 null |

**`integrated` (`IntegratedHour`) — 3 세션 각각 nullable**

| 세션 | 타입 | 설명 |
|---|---|---|
| `preMarket` | `PreMarketSession`\|null | 프리마켓 (NXT 접속매매). NXT 프리마켓 휴장이면 null |
| `regularMarket` | `RegularMarketSession`\|null | 정규장 (KRX·NXT 정규장 합집합). 둘 다 휴장이면 null |
| `afterMarket` | `AfterMarketSession`\|null | 애프터마켓 (NXT). NXT 애프터마켓 휴장이면 null |

**세션 객체 시각 필드**

| 세션 스키마 | 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| `PreMarketSession` | `startTime` | date-time | 필수 | 프리마켓 시작 |
| | `singlePriceAuctionStartTime` | date-time\|null | 선택 | 시가단일가 구간 시작 (NXT 접속매매 종료). 결손 시 null |
| | `endTime` | date-time | 필수 | 프리마켓 종료 (시가단일가 종료) |
| `RegularMarketSession` | `startTime` | date-time | 필수 | 정규장 시작 (가장 이른 KRX/NXT 시작) |
| | `singlePriceAuctionStartTime` | date-time\|null | 선택 | 종가단일가 구간 시작 (KRX 기준). KRX 휴장이면 null |
| | `endTime` | date-time | 필수 | 정규장 종료 (종가단일가 종료) |
| `AfterMarketSession` | `startTime` | date-time | 필수 | 애프터마켓 시작 |
| | `singlePriceAuctionEndTime` | date-time\|null | 선택 | 시가단일가 구간 종료 |
| | `endTime` | date-time | 필수 | 애프터마켓 전체 종료 |

**에러**: 400 `unsupported-date` (`data.field=date`), 429, 500 `internal-error`.

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/market-calendar/KR?date=2026-03-25' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (today 발췌)**

```json
{
  "result": {
    "today": {
      "date": "2026-03-25",
      "integrated": {
        "preMarket":     { "startTime": "2026-03-25T08:00:00+09:00", "singlePriceAuctionStartTime": "2026-03-25T08:50:00+09:00", "endTime": "2026-03-25T09:00:00+09:00" },
        "regularMarket": { "startTime": "2026-03-25T09:00:00+09:00", "singlePriceAuctionStartTime": "2026-03-25T15:20:00+09:00", "endTime": "2026-03-25T15:30:00+09:00" },
        "afterMarket":   { "startTime": "2026-03-25T15:30:00+09:00", "singlePriceAuctionEndTime": "2026-03-25T15:40:00+09:00", "endTime": "2026-03-25T20:00:00+09:00" }
      }
    }
  }
}
```

> 휴장일은 `today.integrated`가 null. NXT 부분 휴장 시 해당 세션만 null (예: `preMarket: null`, 정규장·애프터마켓은 정상).

---

### GET /api/v1/market-calendar/US — 해외 장 운영 정보

미국 종목의 장 운영 시간을 조회합니다. **4 세션**(`dayMarket`, `preMarket`, `regularMarket`, `afterMarket`) 각각 nullable이며, 휴장일이면 4 세션 모두 null. 오늘/이전/다음 3영업일을 반환하고, 모든 시각은 KST(+09:00). Rate Limits Group: `MARKET_INFO`.

**요청**

| 위치 | 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| Header | `Authorization` | string | 필수 | `Bearer {access_token}` |
| Query | `date` | string (date, `YYYY-MM-DD`) | 선택 | 조회 기준일 (미국 현지 날짜). 미지정 시 현재일 |

**응답** — `result`: `UsMarketCalendarResponse`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `today` | `UsMarketDay` | 필수 | 기준일 정보 |
| `previousBusinessDay` | `UsMarketDay` | 필수 | 직전 영업일 |
| `nextBusinessDay` | `UsMarketDay` | 필수 | 다음 영업일 |

**`UsMarketDay` 필드**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `date` | string (date) | 필수 | 영업일 (미국 현지 기준) |
| `dayMarket` | `UsDayMarketSession`\|null | 선택 | 데이마켓 세션 (토스증권). 휴장이면 null |
| `preMarket` | `UsPreMarketSession`\|null | 선택 | 프리마켓 세션. 휴장이면 null |
| `regularMarket` | `UsRegularMarketSession`\|null | 선택 | 정규장 세션. 휴장이면 null |
| `afterMarket` | `UsAfterMarketSession`\|null | 선택 | 애프터마켓 세션. 휴장이면 null |

**각 US 세션 객체** (`UsDayMarketSession` / `UsPreMarketSession` / `UsRegularMarketSession` / `UsAfterMarketSession`)

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `startTime` | string (date-time) | 필수 | 세션 시작 (KST) |
| `endTime` | string (date-time) | 필수 | 세션 종료 (KST) |

**에러**: 429, 500 `internal-error`. (KR 캘린더와 달리 명세상 `date` 검증 400 응답은 정의되어 있지 않음)

**curl 예시**

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/market-calendar/US?date=2026-03-25' \
  -H 'Authorization: Bearer eyJhbGciOi...'
```

**응답 예시 (today 발췌)**

```json
{
  "result": {
    "today": {
      "date": "2026-03-25",
      "dayMarket":     { "startTime": "2026-03-25T09:00:00+09:00", "endTime": "2026-03-25T16:50:00+09:00" },
      "preMarket":     { "startTime": "2026-03-25T17:00:00+09:00", "endTime": "2026-03-25T22:30:00+09:00" },
      "regularMarket": { "startTime": "2026-03-25T22:30:00+09:00", "endTime": "2026-03-26T05:00:00+09:00" },
      "afterMarket":   { "startTime": "2026-03-26T05:00:00+09:00", "endTime": "2026-03-26T07:00:00+09:00" }
    }
  }
}
```

> 휴장일은 `today`의 4 세션이 모두 null. 정규장·애프터마켓은 KST 기준 익일로 넘어가므로 `endTime`의 날짜가 `startTime`보다 +1일일 수 있음.


## 계좌 · 자산 (Account & Asset)

본인 계좌의 자산 현황과 매매 가능 정보(매수 가능 금액·판매 가능 수량·수수료)를 조회하는 API 입니다. 이 섹션의 5개 엔드포인트는 모두 **`GET` 메서드**이며 요청 본문이 없습니다.

### 공통 사항

- **Base URL**: `https://openapi.tossinvest.com`
- **인증 헤더 (모든 호출 필수)**: `Authorization: Bearer {access_token}`
- **계좌 식별 헤더**: 계좌·자산·주문 API 는 `Authorization` 에 더해 **`X-Tossinvest-Account: {accountSeq}` 헤더가 필수**입니다. 이 섹션에서는 `/api/v1/accounts` 만 예외로 계좌 헤더가 필요 없고(계좌 목록 자체를 얻는 API), 나머지 4개(`holdings`, `buying-power`, `sellable-quantity`, `commissions`)는 모두 계좌 헤더가 필수입니다.
- `accountSeq` 값은 `GET /api/v1/accounts` 응답의 `accountSeq` 필드에서 얻습니다.

#### `X-Tossinvest-Account` 헤더 정의

| 항목 | 값 |
|---|---|
| 이름 | `X-Tossinvest-Account` |
| 위치 | header |
| 필수 | true (accounts 제외) |
| 타입 | integer (int64) |
| 설명 | API 요청 시 사용할 계좌의 `accountSeq`. `GET /api/v1/accounts` 응답의 `accountSeq` 값을 사용 |

#### Rate Limits Group (초당 요청 한도)

| 엔드포인트 | Group | 한도 |
|---|---|---|
| `/api/v1/accounts` | `ACCOUNT` | 초당 최대 1회 |
| `/api/v1/holdings` | `ASSET` | 초당 최대 5회 |
| `/api/v1/buying-power` | `ORDER_INFO` | 초당 최대 6회 (09:00~09:10 KST: 초당 최대 3회) |
| `/api/v1/sellable-quantity` | `ORDER_INFO` | 초당 최대 6회 (09:00~09:10 KST: 초당 최대 3회) |
| `/api/v1/commissions` | `ORDER_INFO` | 초당 최대 6회 (09:00~09:10 KST: 초당 최대 3회) |

#### 공통 ENUM

| ENUM | 값 | 의미 |
|---|---|---|
| `Currency` | `KRW` | 한국 원화 |
| `Currency` | `USD` | 미국 달러 |
| `MarketCountry` | `KR` | 국내 주식 (KRX) |
| `MarketCountry` | `US` | 미국 주식 (NYSE, NASDAQ 등) |
| `accountType` | `BROKERAGE` | 종합매매. 국내·해외 주식 통합 매매 계좌 (현재 유일하게 노출) |
| `accountType` | `OVERSEAS_DERIVATIVES` | 해외파생 |
| `accountType` | `PENSION_SAVINGS` | 연금저축 |
| `accountType` | `RESHORING_INVESTMENT` | RIA 계좌 |

> 클라이언트는 위 모든 enum 에서 unknown 값을 허용하도록 구현해야 합니다. 금액·수량·비율 필드는 정밀도 보존을 위해 **문자열(decimal, 최대 30자)** 로 내려옵니다.

#### 공통 응답 envelope

- **성공(200)**: `{ "result": ... }` 형태 (`ApiResponse` 상속, `result` 가 엔드포인트별 타입).
- **실패(4xx/5xx)**: `{ "error": { "requestId", "code", "message", "data"? } }` (`ErrorResponse`). `result` 와 `error` 는 동시에 나타나지 않습니다.

#### 공통 에러 코드

| HTTP | code | 의미 |
|---|---|---|
| 400 | `account-header-required` | `X-Tossinvest-Account` 헤더 누락 |
| 400 | `invalid-request` | 잘못된 요청 (예: 지원하지 않는 통화) |
| 400 / 404 | `account-not-found` | 계좌를 찾을 수 없음 |
| 401 | `invalid-token` / `expired-token` / `login-user-not-found` | 인증 실패 (`WWW-Authenticate: Bearer ...` 헤더 동반) |
| 404 | `stock-not-found` | 종목을 찾을 수 없음 |
| 429 | `rate-limit-exceeded` | 요청 한도 초과 (`Retry-After`, `X-RateLimit-*` 헤더 동반) |
| 500 | `internal-error` | 일시적 서버 오류 |

---

### 1. 계좌 목록 조회 — `GET /api/v1/accounts`

사용자의 계좌 목록을 조회합니다. (현재 종합매매 `BROKERAGE` 계좌만 반환, 계좌 없으면 빈 배열, 자녀계좌 불가)

**요청**

| 구분 | 항목 | 필수 | 설명 |
|---|---|---|---|
| 헤더 | `Authorization: Bearer {token}` | ✅ | OAuth2 액세스 토큰 |
| 헤더 | `X-Tossinvest-Account` | ❌ | 이 API 는 계좌 헤더 불필요 |

경로 파라미터·쿼리 파라미터·요청 본문 없음.

**응답** — `result`: `Account[]` 배열

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `accountNo` | string | ✅ | 계좌번호 (예: `12345678901`) |
| `accountSeq` | integer(int64) | ✅ | 계좌 식별 키. 이후 API 호출의 `X-Tossinvest-Account` 값으로 사용 |
| `accountType` | string(enum) | ✅ | 계좌 유형. 현재 `BROKERAGE` 만 노출 |

**에러**: 401, 429, 500.

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/accounts' \
  -H 'Authorization: Bearer {access_token}'
```

---

### 2. 보유 주식 조회 — `GET /api/v1/holdings`

보유 주식을 종목별 상세 + 합산 평가로 조회합니다. 국내(KR)·미국(US) 주식만 포함하며 해외 옵션·채권은 제외. 보유 종목이 없으면 요약 금액은 0이고 `items` 는 빈 배열입니다.

**요청**

| 구분 | 항목 | 필수 | 타입 | 설명 |
|---|---|---|---|---|
| 헤더 | `Authorization: Bearer {token}` | ✅ | string | OAuth2 액세스 토큰 |
| 헤더 | `X-Tossinvest-Account` | ✅ | integer(int64) | 계좌 `accountSeq` |
| 쿼리 | `symbol` | ❌ | string (`^[A-Za-z0-9.\-]+$`) | 종목 심볼. KR: 6자리 숫자(예: `005930`), US: 티커(예: `AAPL`). 제공 시 해당 종목만 필터링하고 **요약 필드도 해당 종목 기준으로 재계산**. 미제공 시 전체 보유 종목 반환 |

**응답** — `result`: `HoldingsOverview` (통화별 합산 요약 + `items` 배열)

합산 요약 필드. `totalPurchaseAmount`/`marketValue.amount`/… 등 금액은 **통화별 객체(`Price`)** 로, 비율은 단일 문자열로 내려옵니다.

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `totalPurchaseAmount` | `Price` | ✅ | 투자원금. 통화별 합산 |
| `marketValue.amount` | `Price` | ✅ | 시장 평가금액 (통화별 합산) |
| `marketValue.amountAfterCost` | `Price` | ✅ | 세금/수수료 공제 후 평가금액 |
| `profitLoss.amount` | `Price` | ✅ | 손익금액 |
| `profitLoss.amountAfterCost` | `Price` | ✅ | 공제 후 손익금액 |
| `profitLoss.rate` | string(decimal) | ✅ | 손익률(소수비율). **전체 자산을 현재 환율로 원화 환산한 기준** (0.1516 = 15.16%) |
| `profitLoss.rateAfterCost` | string(decimal) | ✅ | 공제 후 손익률 (원화 환산 기준) |
| `dailyProfitLoss.amount` | `Price` | ✅ | 일간 손익금액 |
| `dailyProfitLoss.rate` | string(decimal) | ✅ | 일간 손익률 (원화 환산 기준) |
| `items` | `HoldingsItem[]` | ✅ | 보유 종목 목록 (없으면 빈 배열) |

**`Price` 객체 (통화별 합산 금액)** — 환율 환산을 통한 통화 간 합산은 미포함

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `krw` | string(decimal) | ✅ | KRW로 거래되는 국내 종목 합산. 국내 종목 없으면 `"0"` |
| `usd` | string(decimal) \| null | ❌ | USD로 거래되는 해외 종목 합산. 해외 종목 없으면 `null` |

**`items[]` (`HoldingsItem`)** — 모든 금액은 종목의 거래 통화(`currency`) 기준

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `symbol` | string | ✅ | 종목 심볼 (KR: 6자리 숫자, US: 티커) |
| `name` | string | ✅ | 종목명 |
| `marketCountry` | enum `KR`/`US` | ✅ | 시장 국가 |
| `currency` | enum `KRW`/`USD` | ✅ | 거래 통화 |
| `quantity` | string(decimal) | ✅ | 보유 수량 |
| `lastPrice` | string(decimal) | ✅ | 현재가 (거래 통화 기준) |
| `averagePurchasePrice` | string(decimal) | ✅ | 매수 평균가 (거래 통화 기준) |
| `marketValue.purchaseAmount` | string(decimal) | ✅ | 매입금액 |
| `marketValue.amount` | string(decimal) | ✅ | 시장 평가금액 |
| `marketValue.amountAfterCost` | string(decimal) | ✅ | 세금/수수료 공제 후 평가금액 |
| `profitLoss.amount` | string(decimal) | ✅ | 손익금액 |
| `profitLoss.amountAfterCost` | string(decimal) | ✅ | 공제 후 손익금액 |
| `profitLoss.rate` | string(decimal) | ✅ | 손익률 (0.1077 = 10.77%) |
| `profitLoss.rateAfterCost` | string(decimal) | ✅ | 공제 후 손익률 |
| `dailyProfitLoss.amount` | string(decimal) | ✅ | 일간 손익금액 |
| `dailyProfitLoss.rate` | string(decimal) | ✅ | 일간 손익률 |
| `cost.commission` | string(decimal) | ✅ | 수수료 |
| `cost.tax` | string(decimal) \| null | ❌ | 세금. 없으면 `null` |

**에러**: 400 (`account-header-required`), 401, 404 (`stock-not-found`), 429, 500.

```bash
# 전체 보유 종목
curl -s 'https://openapi.tossinvest.com/api/v1/holdings' \
  -H 'Authorization: Bearer {access_token}' \
  -H 'X-Tossinvest-Account: 1'

# 특정 종목 필터
curl -s 'https://openapi.tossinvest.com/api/v1/holdings?symbol=005930' \
  -H 'Authorization: Bearer {access_token}' \
  -H 'X-Tossinvest-Account: 1'
```

---

### 3. 매수 가능 금액 조회 — `GET /api/v1/buying-power`

매수 주문 시 사용할 수 있는 매수 가능 금액을 조회합니다. 미수거래를 제외한 **현금 기반(미수 미발생 기준)** 금액을 반환합니다.

**요청**

| 구분 | 항목 | 필수 | 타입 | 설명 |
|---|---|---|---|---|
| 헤더 | `Authorization: Bearer {token}` | ✅ | string | OAuth2 액세스 토큰 |
| 헤더 | `X-Tossinvest-Account` | ✅ | integer(int64) | 계좌 `accountSeq` |
| 쿼리 | `currency` | ✅ | enum `KRW`/`USD` | 통화 코드 |

**응답** — `result`: `BuyingPowerResponse`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `currency` | enum `KRW`/`USD` | ✅ | 통화 코드 |
| `cashBuyingPower` | string(decimal) | ✅ | 현금 기반 매수 가능 금액 (미수 미발생). KRW: 정수(원 단위), USD: 소수점 포함(달러 단위) |

**에러**: 400 (`invalid-request` — `data.field="currency"`, `data.allowedValues=["KRW","USD"]`; 또는 `account-header-required`), 401, 404 (`account-not-found`), 429, 500.

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/buying-power?currency=KRW' \
  -H 'Authorization: Bearer {access_token}' \
  -H 'X-Tossinvest-Account: 1'
```

---

### 4. 판매 가능 수량 조회 — `GET /api/v1/sellable-quantity`

특정 종목의 판매 가능 수량을 조회합니다.

**요청**

| 구분 | 항목 | 필수 | 타입 | 설명 |
|---|---|---|---|---|
| 헤더 | `Authorization: Bearer {token}` | ✅ | string | OAuth2 액세스 토큰 |
| 헤더 | `X-Tossinvest-Account` | ✅ | integer(int64) | 계좌 `accountSeq` |
| 쿼리 | `symbol` | ✅ | string (`^[A-Za-z0-9.\-]+$`) | 종목 심볼. KRX: 6자리 숫자(예: `005930`), US: 영문 티커(예: `AAPL`). **이 API 에서는 필수** |

**응답** — `result`: `SellableQuantityResponse`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `sellableQuantity` | string(decimal) | ✅ | 판매 가능 수량. KR: 정수(주 단위), US: 소수점 포함 가능(주 단위) |

**에러**: 400 (`account-not-found` 또는 `account-header-required`), 401, 404 (`stock-not-found`), 429, 500.

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/sellable-quantity?symbol=005930' \
  -H 'Authorization: Bearer {access_token}' \
  -H 'X-Tossinvest-Account: 1'
```

---

### 5. 매매 수수료 조회 — `GET /api/v1/commissions`

현재 계좌의 시장별 매매 수수료율을 조회합니다. 국내(KR)·해외(US) 수수료 정보를 배열로 반환합니다.

**요청**

| 구분 | 항목 | 필수 | 타입 | 설명 |
|---|---|---|---|---|
| 헤더 | `Authorization: Bearer {token}` | ✅ | string | OAuth2 액세스 토큰 |
| 헤더 | `X-Tossinvest-Account` | ✅ | integer(int64) | 계좌 `accountSeq` |

쿼리 파라미터·요청 본문 없음.

**응답** — `result`: `Commission[]` 배열

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `marketCountry` | enum `KR`/`US` | ✅ | 시장 국가 |
| `commissionRate` | string(decimal) | ✅ | 수수료율 (%). 예: `0.015` 는 0.015% |
| `startDate` | string(date) \| null | ❌ | 적용 시작일 (YYYY-MM-DD, KST). 해외주식은 `null` |
| `endDate` | string(date) \| null | ❌ | 적용 종료일 (YYYY-MM-DD, KST). 무기한 적용 시 `null` |

**에러**: 400 (`account-not-found` 또는 `account-header-required`), 401, 429, 500.

```bash
curl -s 'https://openapi.tossinvest.com/api/v1/commissions' \
  -H 'Authorization: Bearer {access_token}' \
  -H 'X-Tossinvest-Account: 1'
```


## 주문 (Order) — ⚠️ 거래성 API

> **⚠️ 실거래 발생 경고 — 신중히 사용하세요.** 이 섹션의 `POST /api/v1/orders`(생성), `POST /api/v1/orders/{orderId}/modify`(정정), `POST /api/v1/orders/{orderId}/cancel`(취소)은 **실제 계좌에서 매수·매도 주문이 즉시 접수·실행되는 거래성 API**입니다. 호출 즉시 자금이 집행되며 되돌릴 수 없습니다. **반드시 소액으로 충분히 검증한 뒤** 운영에 적용하고, 수량·가격·종목·방향(`side`)을 매 호출마다 재확인하세요. 1억원 이상 주문은 `confirmHighValueOrder=true` 가 없으면 거부되고, 30억원 이상 정정 주문은 플래그와 무관하게 거부됩니다.

### 공통 사항

- **모든 호출에 인증 필요:** `Authorization: Bearer {access_token}`
- **모든 주문 API는 계좌 헤더 필수:** `X-Tossinvest-Account: {accountSeq}` (타입 `integer`(int64), **필수**). `accountSeq` 는 `GET /api/v1/accounts` 응답의 `accountSeq` 값입니다. 누락 시 `400 account-header-required`.
- **경로 파라미터 `orderId`** (정정·취소·상세조회): `string`, 필수. 서버가 발급한 opaque token 입니다.
- **성공 응답 envelope:** `{ "result": { ... } }` (HTTP 200). **에러 응답 envelope:** `{ "error": { "requestId", "code", "message", "data?" } }` (4xx/5xx). `result` 와 `error` 는 동시에 나타나지 않습니다.
- **Rate Limits Group:** 생성·정정·취소 = `ORDER`(초당 최대 6회, 09:00~09:10 KST 피크시간 초당 최대 3회), 목록·상세 조회 = `ORDER_HISTORY`(초당 최대 5회).
- **금액·통화 필드는 모두 `string`(format `decimal`)** 으로 내려갑니다 (정밀도 손실 방지).
- **클라이언트는 unknown enum/code 값을 허용하도록 구현**해야 합니다 (서버가 새 코드를 추가할 수 있음).

#### 핵심 ENUM 값

| ENUM | 값 | 의미 |
|---|---|---|
| `side` | `BUY` / `SELL` | 매수 / 매도 |
| `orderType` | `LIMIT` / `MARKET` | 지정가 / 시장가 |
| `timeInForce` (요청) | `DAY` / `CLS` | 당일 유효 / 장 마감 주문(At the Close). 미전달 시 `DAY` |
| `timeInForce` (응답) | `DAY` / `CLS` / `OPG` | 위 + `OPG`(장 개시, 현재 미지원) |
| `currency` | `KRW` / `USD` | 한국 원화 / 미국 달러 |

> `timeInForce` 는 `orderType` 과 결합되어 주문 방식이 결정됩니다 (예: `LIMIT` + `CLS` = LOC). `CLS` 는 현재 **미국 주식 + `orderType=LIMIT`** 조합만 지원합니다.

#### 주문 상태(`status`) 값 — `OrderStatus`

| 상태 | 분류 | 설명 |
|---|---|---|
| `PENDING` | 진행 | 체결 대기. 접수되어 체결을 대기 중 |
| `PENDING_CANCEL` | 진행 | 취소 대기. 취소 요청이 접수되어 브로커 응답 대기 중 |
| `PENDING_REPLACE` | 진행 | 정정 대기. 정정 요청이 접수되어 브로커 응답 대기 중 |
| `PARTIAL_FILLED` | 진행 | 부분 체결. 주문 수량 중 일부만 체결됨 |
| `FILLED` | 종료 | 체결 완료. 전량 체결됨 |
| `CANCELED` | 종료 | 취소 완료. `execution.filledQuantity` 로 부분 체결 여부 확인 |
| `REJECTED` | 종료 | 거부됨. 브로커가 주문을 거부. `filledQuantity` 로 부분 체결 여부 확인 |
| `CANCEL_REJECTED` | 종료 | 취소 거부. 별도 주문 레코드로 생성, 원주문은 이전 상태 복귀 |
| `REPLACE_REJECTED` | 종료 | 정정 거부. 별도 주문 레코드로 생성, 원주문은 이전 상태 복귀 |
| `REPLACED` | 종료 | 정정됨. 원주문이 대체됨. `filledQuantity` 로 부분 체결 여부 확인 |

> 목록 조회의 `status` 쿼리(그룹 라벨)와 응답 `orders[].status`(개별 상태)는 값 체계가 다릅니다. `OPEN` 그룹 = `{PENDING, PARTIAL_FILLED, PENDING_CANCEL, PENDING_REPLACE}`, `CLOSED` 그룹 = `{FILLED, CANCELED, REJECTED, REPLACED, CANCEL_REJECTED, REPLACE_REJECTED, PARTIAL_FILLED}`.

---

### POST /api/v1/orders — 주문 생성

매수 또는 매도 주문을 생성합니다. (지정가·시장가 / KR·US). **Rate Limits Group: `ORDER`**

**요청 본문 (`OrderCreateRequest`, `application/json`, 필수)** — 두 변형 중 하나(`oneOf`)를 사용합니다. `quantity` 와 `orderAmount` 중 **정확히 하나**만 사용합니다.

**① 수량 기반 주문 (Quantity-based, KR·US 공통)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `clientOrderId` | string | 선택 | 멱등성 키. 최대 36자, 영숫자 및 `-`,`_`. 미전달 시 멱등성 미적용. 동일 값 재요청 시 이전 결과 재반환. 서버 자동 생성 안 함. **10분간 유효** |
| `symbol` | string | **필수** | 종목 심볼. KRX: 6자리 숫자(`005930`), US: 영문 티커(`AAPL`) |
| `side` | string(enum) | **필수** | `BUY` / `SELL` |
| `orderType` | string(enum) | **필수** | `LIMIT` / `MARKET` |
| `timeInForce` | string(enum) | 선택 | `DAY` / `CLS`. 미전달 시 `DAY`. `DAY`: 정규장 종료까지 미체결분 자동 취소. `CLS`: US + `LIMIT` 조합만 지원 |
| `quantity` | string(decimal) | **필수** | 주문 수량(주 단위). **정수만** 가능(소수점 불가 — 소수 주문은 `orderAmount` 사용) |
| `price` | string(decimal) | 선택 | `LIMIT` 시 **필수**(미전달 시 `400 invalid-request`), `MARKET` 시 **전달 불가**. KR: 정수(원), 호가 단위 준수(불일치 시 `400 invalid-request` + `data` 에 호가 단위). US: $1 미만 소수 넷째 자리·$1 이상 소수 둘째 자리까지(초과분 절삭) |
| `confirmHighValueOrder` | boolean | 선택 | 기본 `false`. 1억원 이상 주문 시 `true` 아니면 `400 confirm-high-value-required` |

**② 금액 기반 주문 (Amount-based, US `MARKET` 전용)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `clientOrderId` | string | 선택 | (위와 동일) |
| `symbol` | string | **필수** | US 종목 심볼(영문 티커). 금액 기반은 US MARKET 전용 |
| `side` | string(enum) | **필수** | `BUY` / `SELL` |
| `orderType` | string(enum) | **필수** | `MARKET` 만 허용 |
| `orderAmount` | string(decimal) | **필수** | 주문 금액(달러). 체결 수량은 체결 시점 시장가로 결정. **정규장에만 접수 가능** — 정규장 외 호출 시 `422 amount-order-outside-regular-hours` |
| `confirmHighValueOrder` | boolean | 선택 | 기본 `false`. 1억원 이상 시 `true` 아니면 `400 confirm-high-value-required` |

**응답 (200, `OrderResponse`)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `orderId` | string | 필수 | 서버 생성 주문 식별자. 정정/취소 시 사용 |
| `clientOrderId` | string\|null | 선택 | 요청 시 전달한 값 그대로 반환. 미전달 시 `null` |

**최소 curl 예시 (KR 지정가 매수)**

```bash
curl -X POST "https://openapi.tossinvest.com/api/v1/orders" \
  -H "Authorization: Bearer {access_token}" \
  -H "X-Tossinvest-Account: 1" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"005930","side":"BUY","orderType":"LIMIT","quantity":"10","price":"70000"}'
```

```bash
# US 금액 기반 시장가 매수 (정규장 전용)
curl -X POST "https://openapi.tossinvest.com/api/v1/orders" \
  -H "Authorization: Bearer {access_token}" -H "X-Tossinvest-Account: 1" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","side":"BUY","orderType":"MARKET","orderAmount":"100.5"}'
```

---

### POST /api/v1/orders/{orderId}/modify — 주문 정정

기존 주문의 가격 또는 수량을 정정합니다. **Rate Limits Group: `ORDER`**

- **KR 주식:** `quantity` **필수**(양의 정수만; 미전달/0/음수/소수점은 `400 invalid-request`).
- **US 주식:** `quantity` **제공 불가**(가격 변경만 지원). 제공 시 `400 us-modify-quantity-not-supported`.

**경로:** `orderId` (string, 필수) — 정정할 원주문 식별자. **헤더:** `X-Tossinvest-Account` 필수.

**요청 본문 (`OrderModifyRequest`, `application/json`, 필수)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `orderType` | string(enum) | **필수** | 변경할 호가 유형. `LIMIT` / `MARKET` |
| `quantity` | string(decimal) | 선택 | 변경할 수량. **KR: 필수**(양의 정수). US: 전달 불가(`400 us-modify-quantity-not-supported`) |
| `price` | string(decimal) | 선택 | 변경할 가격. `LIMIT` 시 **필수**, `MARKET` 시 **전달 불가**. KR: 정수(원)·호가 단위 준수. US: $1 미만 소수 넷째 자리·$1 이상 소수 둘째 자리(초과분 절삭) |
| `confirmHighValueOrder` | boolean | 선택 | 기본 `false`. 1억원 이상 시 `true` 아니면 `400 confirm-high-value-required`. **30억원 이상은 플래그와 무관하게 `422 max-order-amount-exceeded`** |

**응답 (200, `OrderOperationResponse`)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `orderId` | string | 필수 | 정정으로 **새로 발급**된 주문 식별자. 원주문 `orderId` 와 다름 |

**최소 curl 예시 (KR 정정)**

```bash
curl -X POST "https://openapi.tossinvest.com/api/v1/orders/{orderId}/modify" \
  -H "Authorization: Bearer {access_token}" \
  -H "X-Tossinvest-Account: 1" \
  -H "Content-Type: application/json" \
  -d '{"orderType":"LIMIT","quantity":"15","price":"71000"}'
```

---

### POST /api/v1/orders/{orderId}/cancel — 주문 취소

기존 주문을 취소합니다. **이미 체결된 주문은 취소할 수 없습니다.** **Rate Limits Group: `ORDER`**

**경로:** `orderId` (string, 필수). **헤더:** `X-Tossinvest-Account` 필수. **요청 본문:** 선택(빈 객체 `{}` 가능, `application/json`).

**응답 (200, `OrderOperationResponse`)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `orderId` | string | 필수 | 취소로 **새로 발급**된 주문 식별자. 원주문 `orderId` 와 다름 |

**최소 curl 예시**

```bash
curl -X POST "https://openapi.tossinvest.com/api/v1/orders/{orderId}/cancel" \
  -H "Authorization: Bearer {access_token}" \
  -H "X-Tossinvest-Account: 1"
```

> 취소 불가 상태는 `409`(`already-filled`, `already-canceled` 등) 또는 `422 cancel-restricted` 로 반환됩니다.

---

### GET /api/v1/orders — 주문 목록 조회

주문 목록을 조회합니다(대기중/종료). **Rate Limits Group: `ORDER_HISTORY`**

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `status` | string(enum) | **필수** | `OPEN`(진행 중 그룹) / `CLOSED`(종료 그룹). 라이프사이클 그룹 필터 |
| `symbol` | string | 선택 | 종목 필터. 패턴 `^[A-Za-z0-9.\-]+$`. KRX: 6자리 숫자, US: 영문 티커 |
| `from` | string(date) | 선택 | 조회 시작일(inclusive, KST). `orderedAt` 기준. 미지정 시 전체 기간 |
| `to` | string(date) | 선택 | 조회 종료일(inclusive, KST). `orderedAt` 기준. 미지정 시 전체 기간 |
| `cursor` | string | 선택 | 페이지네이션 커서. `OPEN` 에서는 무시, `CLOSED` 에서 다음 페이지 조회에 사용 |
| `limit` | integer | 선택 | 페이지 크기(min 1, max 100, default 20). `OPEN` 에서는 무시(전량 반환), `CLOSED` 에서 적용 |

**페이징 동작:**
- `status=OPEN`: 모든 대기 중 주문 전량 반환. `limit`·`cursor` 무시, `from`/`to` 만 적용. 응답 `nextCursor` 는 항상 `null`, `hasNext` 는 항상 `false`.
- `status=CLOSED`: `limit`·`cursor`·`from`/`to` 모두 적용.

**응답 (200, `PaginatedOrderResponse`)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `orders` | `Order[]` | 필수 | 주문 목록 (아래 `Order` 객체 참조) |
| `nextCursor` | string\|null | 필수 | 다음 페이지 커서. 없으면 `null` |
| `hasNext` | boolean | 필수 | 다음 페이지 존재 여부 |

**최소 curl 예시**

```bash
curl "https://openapi.tossinvest.com/api/v1/orders?status=OPEN" \
  -H "Authorization: Bearer {access_token}" \
  -H "X-Tossinvest-Account: 1"
```

---

### GET /api/v1/orders/{orderId} — 주문 상세 조회

특정 주문의 상세 정보를 조회합니다. **모든 상태**(체결 완료·취소·거부 등)의 주문을 조회할 수 있습니다. **Rate Limits Group: `ORDER_HISTORY`**

**경로:** `orderId` (string, 필수). **헤더:** `X-Tossinvest-Account` 필수.

**응답 (200, `Order`)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `orderId` | string | 필수 | 주문 식별자 |
| `symbol` | string | 필수 | 종목 심볼. KRX: 6자리 숫자, US: 영문 티커 |
| `side` | string(enum) | 필수 | `BUY` / `SELL` |
| `orderType` | string(enum) | 필수 | `LIMIT` / `MARKET` |
| `timeInForce` | string(enum) | 필수 | `DAY` / `CLS` / `OPG` |
| `status` | `OrderStatus` | 필수 | 주문 상태 (위 상태 표 참조) |
| `price` | string\|null (decimal) | 선택 | 주문 가격(native currency). MARKET 주문 시 `null` |
| `quantity` | string(decimal) | 필수 | 주문 수량 |
| `orderAmount` | string\|null (decimal) | 선택 | 주문 금액(USD). 금액 기반 US 시장가 주문에만 해당, 그 외 `null` |
| `currency` | `Currency` | 필수 | `KRW` / `USD` |
| `orderedAt` | string(date-time) | 필수 | 주문 시간(ISO 8601, KST) |
| `canceledAt` | string\|null (date-time) | 선택 | 취소 시간(ISO 8601, KST). 해당 없으면 `null` |
| `execution` | `OrderExecution` | 필수 | 체결 결과(아래 표). 체결 내역 없으면 `filledQuantity=0` |

**`OrderExecution` 하위 필드**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `filledQuantity` | string(decimal) | 필수 | 체결 수량 |
| `averageFilledPrice` | string\|null (decimal) | 필수 | 평균 체결 가격(native currency). 부분 체결 시 평균 |
| `filledAmount` | string\|null (decimal) | 필수 | 총 체결 금액(native currency) |
| `commission` | string\|null (decimal) | 필수 | 총 체결 수수료(native currency) |
| `tax` | string\|null (decimal) | 필수 | 총 체결 세금(native currency) |
| `filledAt` | string\|null (date-time) | 필수 | 최종 체결 시간(ISO 8601, KST) |
| `settlementDate` | string\|null (date) | 필수 | 결제 예정일(YYYY-MM-DD, KST). 미결제 시 `null` |

**최소 curl 예시**

```bash
curl "https://openapi.tossinvest.com/api/v1/orders/{orderId}" \
  -H "Authorization: Bearer {access_token}" \
  -H "X-Tossinvest-Account: 1"
```

---

### 주문 관련 주요 에러 코드

에러 응답 envelope: `{ "error": { "requestId", "code", "message", "data"? } }`. `requestId` 는 응답 헤더 `X-Request-Id` 와 동일(누락 시 `cf-ray` 헤더 첨부). `data` 는 코드별로 키 구조가 다른 해결 힌트(`field`, `allowedValues`, `tickSize`, `nearestPrices`, `limits`, `constraint`, `retryAfterAt`/`retryAfterSeconds` 등).

| HTTP | 코드 | 발생 이유 |
|---|---|---|
| 400 | `invalid-request` | 호가 유형·주문 방향·수량·금액·필수 파라미터 누락 등 |
| 400 | `confirm-high-value-required` | 1억원 이상 주문/정정인데 `confirmHighValueOrder` 가 `true` 아님 |
| 400 | `account-header-required` | `X-Tossinvest-Account` 헤더 누락 |
| 400 | `us-modify-quantity-not-supported` | US 주문 정정 시 `quantity` 를 전달함 (정정 전용) |
| 401 | `invalid-token` / `expired-token` / `login-user-not-found` | 토큰 무효·만료·로그인 정보 없음 |
| 401 | `edge-blocked` | `Authorization` 헤더 누락 |
| 403 | `forbidden` | 권한 부족 |
| 404 | `order-not-found` | `orderId` 에 해당하는 주문 없음 |
| 404 | `account-not-found` | `X-Tossinvest-Account` 가 가리키는 계좌 없음 |
| 404 | `stock-not-found` | 요청 종목 없음 |
| 409 | `request-in-progress` | 동일 `clientOrderId` 주문 생성 요청이 이미 처리 중 |
| 409 | `already-filled` / `already-canceled` / `already-modified` / `already-rejected` | 정정/취소 대상 주문이 이미 해당 상태 |
| 409 | `already-processing` | 동일 주문에 대한 정정/취소가 이미 처리 중 |
| 422 | `insufficient-buying-power` | 주문 가능 금액 부족 |
| 422 | `order-hours-closed` | 현재 주문(생성/정정/취소) 접수 불가 시간 |
| 422 | `price-out-of-range` | 주문 가격이 상/하한가 범위 초과 |
| 422 | `opposite-pending-order-exists` | 동일 종목에 반대 방향 체결 대기 주문 존재 |
| 422 | `order-type-not-allowed` | 현재 사용할 수 없는 호가 유형 |
| 422 | `stock-restricted` | 종목이 거래 제한 상태 |
| 422 | `amount-order-outside-regular-hours` | 금액 주문은 정규장에만 가능 (US) |
| 422 | `modify-restricted` / `cancel-restricted` | 해당 주문은 정정/취소가 제한됨 |
| 422 | `max-order-amount-exceeded` | 30억원 이상 정정 주문 (플래그 무관 거부) |
| 422 | `market-not-supported-for-stock` | 해당 종목은 요청 시장에서 거래 불가 (KR) |
| 422 | `prerequisite-required` | 약관 동의·위험 고지 등 사전 자격 요건 미충족 |
| 429 | `rate-limit-exceeded` / `edge-rate-limit-exceeded` | Rate limit 초당 요청 수 초과 |
| 500 | `internal-error` / `maintenance` | 서버 일시 장애 / 시스템 점검 중 |


