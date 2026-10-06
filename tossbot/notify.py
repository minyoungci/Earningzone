"""알림 전송 — Discord Webhook / Telegram Bot (표준 라이브러리만 사용).

키는 환경변수로만 주입한다(코드/파일 평문 저장 금지):
- DISCORD_WEBHOOK_URL                    : Discord 채널 웹훅 URL
- TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID  : 텔레그램 봇 토큰 + 대상 채팅 ID

계약:
- send(text) -> bool : 설정된 채널 전부에 전송 시도. 하나라도 성공하면 True.
                       둘 다 미설정이면 no-op(False). 모든 실패는 무해(False) —
                       알림 실패가 매매/서버 흐름을 절대 깨뜨리지 않는다.
- configured() -> {"discord": bool, "telegram": bool}
"""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request

TIMEOUT_SEC = 10
# 일부 엣지가 기본 'Python-urllib' UA 를 차단하므로 명시적 UA 사용.
USER_AGENT = "Mozilla/5.0"
# 플랫폼별 본문 길이 한도(초과 시 잘라서 전송 — 실패보다 축약이 낫다).
DISCORD_MAX_LEN = 2000
TELEGRAM_MAX_LEN = 4096


def configured():
    """채널별 설정 여부. env 는 호출 시점에 읽는다(서버 재기동 없이도 반영)."""
    return {
        "discord": bool(os.environ.get("DISCORD_WEBHOOK_URL", "").strip()),
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
                         and os.environ.get("TELEGRAM_CHAT_ID", "").strip()),
    }


def _post_json(url, body):
    """JSON POST — 2xx 면 True. 예외는 호출부에서 삼킨다."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": USER_AGENT, "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
        return 200 <= r.status < 300


def _send_discord(text):
    """Discord 웹훅 POST {"content": text}. 성공 시 보통 204 No Content."""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return False
    try:
        return _post_json(url, {"content": text[:DISCORD_MAX_LEN]})
    except Exception:
        # 네트워크/웹훅 오류는 무해하게 실패 처리
        return False


def _send_telegram(text):
    """Telegram Bot API sendMessage."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    url = "https://api.telegram.org/bot" + urllib.parse.quote(token) + "/sendMessage"
    try:
        return _post_json(url, {
            "chat_id": chat_id,
            "text": text[:TELEGRAM_MAX_LEN],
            "disable_web_page_preview": True,  # 링크 미리보기로 채팅이 길어지는 것 방지
        })
    except Exception:
        return False


def send(text):
    """설정된 모든 채널로 전송. 하나라도 성공하면 True, 아니면(미설정 포함) False."""
    text = str(text or "").strip()
    if not text:
        return False
    ok = False
    if _send_discord(text):
        ok = True
    if _send_telegram(text):
        ok = True
    return ok
