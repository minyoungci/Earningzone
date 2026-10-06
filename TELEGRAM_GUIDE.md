# 텔레그램 연동 가이드 (알림 + 원격 컨트롤)

tossbot 은 텔레그램으로 **알림**(오토파일럿 체결·레짐 변화)과 **원격 컨트롤**(/status, /picks …)을
지원합니다. 봇 계정만 만들면 서버가 자동으로 연결합니다. (약 2분 소요)

> Discord 는 **알림 전용**(웹훅)입니다 — 인바운드 제어는 상주 게이트웨이가 필요해 텔레그램을 권장합니다.
> Hermes 등 타인의 비공개 봇과는 연동할 수 없습니다(공식 API 없음).

---

## 1. 봇 만들기 (BotFather)

1. 텔레그램에서 **@BotFather** 검색 → 대화 시작
2. `/newbot` 입력 → 봇 표시 이름(예: `tossbot 알림`) → 봇 사용자명(예: `my_tossbot_bot`, `_bot` 으로 끝나야 함)
3. BotFather 가 주는 **봇 토큰**을 복사 — 형식: `1234567890:AAE...` (⚠️ 비밀 — 파일/채팅에 남기지 말 것)

## 2. 내 chat ID 확인

1. 방금 만든 봇에게 아무 메시지나 한 번 보냄 (예: "hi") — 이걸 해야 봇이 나에게 메시지를 보낼 수 있음
2. **@userinfobot** 에게 아무 말이나 보내면 내 **Id**(숫자)를 알려줌 — 그 값이 `TELEGRAM_CHAT_ID`

## 3. 서버에 주입하고 재시작

키는 **환경변수로만** 주입합니다(평문 파일 저장 금지 정책).
PowerShell 에서 (D:\toss 기준):

```powershell
$env:TOSS_CLIENT_ID     = '<토스 클라이언트 ID>'
$env:TOSS_CLIENT_SECRET = '<토스 시크릿>'
$env:ACCESS_TOKEN       = '<웹 컨트롤 토큰(선택)>'
$env:TELEGRAM_BOT_TOKEN = '<1번에서 받은 봇 토큰>'
$env:TELEGRAM_CHAT_ID   = '<2번에서 확인한 숫자 ID>'
python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

서버가 뜨면서 자동으로:
- **알림**: 오토파일럿 체결·시장 레짐 단계 변화가 이 봇으로 발송됨 (`POST /api/notify/test` 로 테스트)
- **컨트롤 봇**: getUpdates 롱폴링 시작 (공개 IP·포트 개방 불필요)

## 4. 사용 가능한 명령

| 명령 | 동작 |
| :-- | :-- |
| `/status` | 오토파일럿 가동 상태·계좌·사이클·현재 레짐 요약 |
| `/regime` | 리스크 전광판 (🔵~🔴 5단계 + 가이드) |
| `/picks [kr\|kosdaq\|us\|usgrowth\|all]` | 퀀트 상위 5 종목 + 플랜 한 줄 (기본 kr) |
| `/portfolio` | 활성 모의계좌 잔고·보유 요약 |
| `/autopilot_start [market]` | 오토파일럿 시작 (기본 kr, 레짐 가드 ON) |
| `/autopilot_stop` | 오토파일럿 중지 |
| `/accounts` | 모의계좌 목록 (활성 ✅) |
| `/help` | 명령 목록 |

## 5. 보안 규칙 (내장됨)

- **내 chat ID 의 메시지에만 반응** — 다른 사람이 봇을 발견해 말을 걸어도 완전 무응답
- 봇 토큰·chat ID 는 환경변수로만 읽음 (코드/파일 하드코딩 없음)
- 같은 봇 토큰으로 서버를 **2개 이상 띄우면 안 됨** (텔레그램 getUpdates 409 충돌)
- 모든 매매는 모의계좌(sim) 전용 — 실주문 경로와 코드 수준에서 분리, DRY_RUN 기본 ON

## 6. (선택) Discord 알림

디스코드 채널 → 설정 → 연동 → **웹훅 만들기** → URL 복사 후:

```powershell
$env:DISCORD_WEBHOOK_URL = '<웹훅 URL>'
```

텔레그램과 동시에 설정하면 두 곳 모두 발송됩니다.

---

문제 해결: 봇이 응답하지 않으면 ① 봇에게 먼저 말을 걸었는지 ② TELEGRAM_CHAT_ID 가 숫자 그대로인지
③ 서버 콘솔(stderr)에 텔레그램 경고가 있는지 순으로 확인하세요.
