"""텔레그램 컨트롤 봇 — getUpdates 롱폴링 (표준 라이브러리만 사용).

서버(server/app.py)가 기동 시 start_bot(handlers) 를 호출해 데몬 스레드로 돌린다.
notify.py 와 동일한 원칙: 키/토큰은 환경변수로만 주입(코드/파일 평문 저장 금지).
- TELEGRAM_BOT_TOKEN : 봇 토큰
- TELEGRAM_CHAT_ID   : 허용된 채팅 ID (이 채팅의 메시지만 처리)

보안:
- message.chat.id 가 TELEGRAM_CHAT_ID 와 일치하는 메시지만 처리한다.
  그 외 발신자는 조용히 무시(응답도 하지 않음 — 봇 존재를 노출하지 않는다).

계약:
- start_bot(handlers) -> bool : 폴링 스레드 시작. 이미 실행 중이면 무시(False).
    handlers = {"status", "regime", "picks", "portfolio",
                "autopilot_start", "autopilot_stop", "accounts"}
    각 값은 한국어 요약 '문자열'을 반환하는 함수(예외는 fn 내부에서 처리 권장,
    여기서도 방어적으로 잡아 '⚠️ 오류: ...' 로 응답).
- stop_bot()          : 이벤트 기반 정지 요청(다음 폴링 주기에 종료).
- running() -> bool   : 폴링 스레드 생존 여부.

폴링/오류 정책:
- getUpdates?timeout=50&offset=N (urllib, 소켓 timeout=60 — 롱폴링보다 길게).
- 네트워크 오류 시 5초 대기 후 재폴링 — 루프는 절대 죽지 않는다.
- 응답은 sendMessage, 본문은 4096자 절단(실패보다 축약이 낫다).
"""
from __future__ import annotations
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

# notify.py 와 동일 — 일부 엣지가 기본 'Python-urllib' UA 를 차단한다.
USER_AGENT = "Mozilla/5.0"
TELEGRAM_MAX_LEN = 4096   # sendMessage 본문 한도
POLL_TIMEOUT_SEC = 50     # 텔레그램 서버 측 롱폴링 대기(초)
HTTP_TIMEOUT_SEC = 60     # urllib 소켓 타임아웃(롱폴링 대기보다 길게)
RETRY_WAIT_SEC = 5        # 네트워크 오류 시 재시도 대기
CLOCK_SKEW_SEC = 5        # 백로그 판정 시 허용할 로컬↔텔레그램 시계 오차(초)

# /picks 허용 시장(명령 인자 화이트리스트 — 기본 kr)
PICKS_MARKETS = ("kr", "kosdaq", "us", "usgrowth", "all")

HELP_TEXT = (
    "🤖 tossbot 컨트롤 명령\n"
    "/status — 오토파일럿·레짐 상태 요약\n"
    "/regime — 시장 레짐 스냅샷\n"
    "/picks [kr|kosdaq|us|usgrowth|all] — 퀀트 상위 종목(기본 kr)\n"
    "/portfolio — 모의 포트폴리오 요약\n"
    "/autopilot_start [market] — 오토파일럿 시작(기본 kr)\n"
    "/autopilot_stop — 오토파일럿 정지\n"
    "/accounts — 계좌 목록 요약\n"
    "/help — 이 도움말"
)

# ---------------------------------------------------------------- 스레드 상태
_lock = threading.Lock()          # start_bot 중복 호출 방지 락
_stop_event = threading.Event()   # 이벤트 기반 정지 신호
_thread = None                    # 폴링 스레드 핸들


def running():
    """폴링 스레드가 살아있으면 True."""
    t = _thread
    return bool(t is not None and t.is_alive())


def start_bot(handlers):
    """폴링 데몬 스레드 시작. 이미 실행 중이면 무시(False)."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False  # 이미 실행 중 — 중복 기동 금지
        _stop_event.clear()
        _thread = threading.Thread(
            target=_poll_loop, args=(handlers,),
            name="telegram-bot", daemon=True,
        )
        _thread.start()
        return True


def stop_bot():
    """정지 요청 — 진행 중인 롱폴링이 끝나는 대로 루프가 종료된다."""
    _stop_event.set()


# ---------------------------------------------------------------- 텔레그램 API
def _api_url(method, params=None):
    """봇 API URL 조립 — 토큰은 호출 시점에 env 에서 읽는다(notify.py 방식)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    url = "https://api.telegram.org/bot" + urllib.parse.quote(token) + "/" + method
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


def _get_updates(offset):
    """getUpdates 롱폴링 — 업데이트 리스트 반환. 예외는 호출부에서 처리."""
    params = {"timeout": POLL_TIMEOUT_SEC}
    if offset is not None:
        params["offset"] = offset
    req = urllib.request.Request(
        _api_url("getUpdates", params),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not isinstance(data, dict) or not data.get("ok"):
        return []
    result = data.get("result")
    return result if isinstance(result, list) else []


def _send_message(chat_id, text):
    """sendMessage — 4096자 절단, 실패는 무해(False). notify.py 패턴 재사용."""
    text = str(text or "").strip()
    if not text or not chat_id:
        return False
    body = {
        "chat_id": chat_id,
        "text": text[:TELEGRAM_MAX_LEN],
        "disable_web_page_preview": True,  # 링크 미리보기로 채팅이 길어지는 것 방지
    }
    req = urllib.request.Request(
        _api_url("sendMessage"),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": USER_AGENT, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


# ---------------------------------------------------------------- 명령 라우팅
def _call(handlers, key, *args):
    """핸들러 호출 — 없거나 예외면 '⚠️ 오류: ...' 문자열로 방어."""
    fn = handlers.get(key) if isinstance(handlers, dict) else None
    if not callable(fn):
        return "⚠️ 오류: '%s' 핸들러가 없습니다" % key
    try:
        return str(fn(*args))
    except Exception as e:  # 계약상 fn 내부에서 잡지만, 여기서도 이중 방어
        return "⚠️ 오류: %s" % e


def _dispatch(text, handlers):
    """명령 텍스트 → 응답 문자열. 알 수 없는 명령은 안내 문구."""
    parts = str(text or "").strip().split()
    if not parts:
        return None  # 빈 텍스트는 무응답
    cmd = parts[0].lower()
    if "@" in cmd:  # 그룹에서 '/status@MyBot' 형태로 올 수 있음
        cmd = cmd.split("@", 1)[0]
    args = parts[1:]

    if cmd in ("/start", "/help"):
        return HELP_TEXT
    if cmd == "/status":
        return _call(handlers, "status")
    if cmd == "/regime":
        return _call(handlers, "regime")
    if cmd == "/picks":
        market = args[0].lower() if args else "kr"
        if market not in PICKS_MARKETS:
            return "지원하지 않는 시장이에요. /picks [%s]" % "|".join(PICKS_MARKETS)
        return _call(handlers, "picks", market)
    if cmd == "/portfolio":
        return _call(handlers, "portfolio")
    if cmd == "/autopilot_start":
        market = args[0].lower() if args else "kr"
        return _call(handlers, "autopilot_start", market)
    if cmd == "/autopilot_stop":
        return _call(handlers, "autopilot_stop")
    if cmd == "/accounts":
        return _call(handlers, "accounts")
    return "알 수 없는 명령이에요. /help"


def _handle_update(update, handlers, allowed_chat_id, start_ts):
    """update 1건 처리 — 허용 chat.id 의 텍스트 메시지만 응답 문자열 반환.

    허용되지 않은 발신자는 None(조용히 무시 — 응답도 하지 않음).
    edited_message 는 처리하지 않는다 — 과거 명령 메시지를 수정하는 것만으로
    /autopilot_start 같은 상태 변경 명령이 재실행되는 것을 막는다.
    폴링 시작(start_ts) 이전에 보낸 메시지도 실행하지 않는다 — 서버가 꺼져
    있는 동안 쌓인 백로그 명령이 재기동 시 소리 없이 재생되는 것을 막는다.
    """
    if not isinstance(update, dict):
        return None
    msg = update.get("message")  # edited_message 는 의도적으로 무시(위 docstring)
    if not isinstance(msg, dict):
        return None
    # ⏱️ 백로그 게이트: 기동 전 메시지는 dispatch 하지 않는다(오프셋만 전진).
    # date 는 텔레그램 서버 기준 유닉스 초 — 시계 오차만큼 여유를 둔다.
    # date 가 없거나 형식이 이상한 메시지는 신선도를 판정할 수 없으므로 버린다.
    date = msg.get("date")
    if not isinstance(date, (int, float)) or date < start_ts - CLOCK_SKEW_SEC:
        return None
    chat = msg.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    # ⚠️ 보안 게이트: env TELEGRAM_CHAT_ID 와 정확히 일치해야만 처리
    if chat_id is None or not allowed_chat_id or str(chat_id) != str(allowed_chat_id):
        return None
    text = msg.get("text")
    if not isinstance(text, str) or not text.strip():
        return None  # 사진/스티커 등 비텍스트는 무시
    return _dispatch(text, handlers)


# ---------------------------------------------------------------- 폴링 루프
def _poll_loop(handlers):
    """getUpdates 롱폴링 루프 — stop_bot() 전까지 절대 죽지 않는다."""
    offset = None  # 마지막 처리 update_id + 1 (중복 수신 방지)
    # 폴링 시작 시각 — 이전(서버 다운 중) 백로그 메시지는 실행하지 않고 버린다.
    start_ts = time.time()
    while not _stop_event.is_set():
        try:
            updates = _get_updates(offset)
        except Exception as e:
            # 네트워크 오류 — 5초 대기 후 재폴링(정지 신호는 즉시 반영)
            sys.stderr.write("[telegram_bot] 폴링 오류: %s — %d초 후 재시도\n"
                             % (e, RETRY_WAIT_SEC))
            _stop_event.wait(RETRY_WAIT_SEC)
            continue
        # chat.id 허용값은 매 주기 env 에서 읽는다(재기동 없이 반영)
        allowed = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        for update in updates:
            uid = update.get("update_id") if isinstance(update, dict) else None
            if isinstance(uid, int):
                offset = uid + 1  # 처리 여부와 무관하게 오프셋 전진
            if _stop_event.is_set():
                break
            try:
                reply = _handle_update(update, handlers, allowed, start_ts)
            except Exception as e:  # 어떤 예외도 루프를 죽이지 못한다
                sys.stderr.write("[telegram_bot] 처리 오류: %s\n" % e)
                reply = None
            if reply:
                _send_message(allowed, reply)
