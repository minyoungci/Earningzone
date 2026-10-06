# tossbot 데스크톱 앱

토스증권 퀀트 워크스테이션을 **네이티브 창 하나짜리 실행 앱**(`tossbot.exe`)으로 패키징합니다.
브라우저·터미널 없이 더블클릭으로 실행되며, 토스 API 키는 **OS 자격 증명 관리자**에 안전 저장됩니다.

## 구조

- **pywebview** — OS 네이티브 웹뷰 창(Windows = Edge WebView2, 대부분 기본 설치됨)에 UI를 띄움.
- **내장 FastAPI 서버** — 앱이 빈 포트를 잡아 `server.app` 을 백그라운드 스레드로 기동(127.0.0.1).
- **keyring** — 토스 키를 Windows 자격 증명 관리자(WinVault)에 암호화 저장. 평문 파일 없음.
- **PyInstaller onefile** — Python 런타임 + 의존성 + 빌드된 SPA를 단일 `tossbot.exe`(약 65MB)로 묶음.

주요 파일: [desktop.py](desktop.py)(진입점) · [build_desktop.py](build_desktop.py)(빌드) ·
[tossbot/secrets_store.py](tossbot/secrets_store.py)(키체인) · [tossbot/paths.py](tossbot/paths.py)(상태 저장 위치).

## 빌드

```powershell
# 1) 최초 1회 — 의존성 설치
python -m pip install -r server/requirements-desktop.txt

# 2) 프론트엔드 빌드(코드 변경 시마다)
cd web ; npm run build ; cd ..

# 3) 데스크톱 앱 빌드
python build_desktop.py            # onefile — 단일 tossbot.exe(배포 간편, 콜드스타트 ~12-15초)
python build_desktop.py --onedir   # onedir — dist/tossbot 폴더(콜드스타트 ~1-2초, 자주 여는 앱 권장)
python build_desktop.py --console  # 콘솔 유지 — 첫 실행 디버그용(에러가 콘솔에 보임)
```

→ onefile: `dist/tossbot.exe` · onedir: `dist/tossbot/tossbot.exe`(폴더 통째로 배포).

**onefile vs onedir**: onefile 은 파일 하나라 배포가 간편하지만 매 실행마다 64MB 를 temp 에
압축해제(+백신 스캔)하여 **첫 기동에 ~12-15초** 걸린다. onedir 은 재압축이 없어 **~1-2초**에
뜬다 — 매일 여는 도구라면 onedir 폴더를 zip 으로 배포하는 편이 쾌적하다.
(onefile 을 쓰면서 대기를 감추려면 `build_desktop.py` 에 PyInstaller `--splash` 스플래시 추가 가능.)

## 실행 & 첫 키 입력 (키는 **딱 한 번만** 입력)

1. **onedir**: `dist/tossbot/tossbot.exe` 더블클릭(약 2초에 창) ·
   **onefile**: `dist/tossbot.exe`(첫 기동 12~15초)
2. 처음엔 상단에 **키 입력 배너** — `TOSS_CLIENT_ID` / `TOSS_CLIENT_SECRET` 을 붙여넣고
   **“키 저장하고 연결”**. 백엔드가 Windows 자격 증명 관리자에 저장하고 **즉시 반영**(재시작 불필요).
3. **다음 실행부터는 자동 로드** — 다시 입력할 필요 없음. 프론트엔드는 키를 저장하지 않는다.

> 실측 검증: 키 저장(`saved_to_keychain=true`) → 앱 종료 → 재실행 시
> `/api/settings/keys` 가 `loaded=true` 로 응답(자동 로드 확인).

키를 바꾸려면: 자격 증명 관리자에서 `tossbot` 항목 삭제 후 앱 재실행 → 배너에서 새 키 입력.
(또는 `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET` 환경변수를 설정하면 키체인보다 우선 적용.)

> **IP 허용목록**: 토스 Open API는 IP-gated입니다. 다른 네트워크에서 처음 실행하면 배너가
> **현재 공인 IP**를 안내 — 토스 개발자센터 > 키 설정 > 허용 IP 에 추가하세요.

키를 환경변수로 주입하고 싶다면(앱보다 우선): 실행 전 `TOSS_CLIENT_ID` / `TOSS_CLIENT_SECRET`
환경변수를 설정하면 키체인보다 우선 적용됩니다.

## 상태 저장 위치

- **패키징(exe) 실행**: `%APPDATA%\tossbot\` — 모의투자 계좌(`.sim_state.json`),
  브로커 선택(`.broker_state.json`) 등이 **재시작에도 유지**됨.
- **소스 실행**(`python desktop.py`): 프로젝트 루트(기존 개발 동작).
- `TOSSBOT_DATA_DIR` 환경변수로 위치를 명시 지정 가능.

## 안전

- `TOSS_DRY_RUN` 기본 ON — 매수/매도는 **모의 체결**만, 실주문 없음.
- 토스 키는 코드·평문파일에 저장되지 않고 OS 키체인에만 존재. 로그아웃은
  자격 증명 관리자에서 `tossbot` 항목 삭제(또는 `secrets_store.clear()`).

## 알려진 참고

- Edge WebView2 런타임이 없는 구형 Windows에서는 최초 실행 시 런타임 설치를 유도할 수 있음
  (Win10/11 대부분 기본 포함).
- 첫 배포 시 SmartScreen 경고가 뜰 수 있음(서명 안 된 exe) — “추가 정보 > 실행”.
  정식 배포 시 코드 서명 인증서로 서명 권장.
- macOS/Linux 빌드도 동일 스크립트로 가능(각 OS에서 실행). 키체인은 각 OS 네이티브 백엔드 사용.

## 오프라인 패키지 진단

`dist/tossbot/tossbot.exe --selftest-report <보고서.json>`으로 내장 서버·프론트 자산을
검증할 수 있습니다. GUI와 키체인 로드를 생략하고 임시 데이터 폴더를 사용합니다.
실제 인증과 WebView 화면 표시는 별도 검증 대상입니다.

## 공개 설명 문서

EXE에는 [분석 시스템과 알고리즘](docs/public/README.md)의 지정된 공개 글 6개만 포함합니다.
개인 금융 원문·사본·그림·출처 목록은 번들에 넣지 않으며 문서·이미지 API도 제공하지 않습니다.
오프라인 패키지 진단은 공개 글을 읽을 수 있는지와 개인 자료 경로의 차단 여부도 검사합니다.
