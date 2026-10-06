"""토스 API 키를 OS 키체인(Windows 자격 증명 관리자 / macOS Keychain / Secret Service)에
안전 저장·로드한다. 평문 .env 대신 사용 — 데스크톱 앱의 키 저장 백엔드.

keyring 이 설치되지 않았거나 백엔드가 없는 환경에서도 import·호출은 실패하지 않고
graceful 하게 degrade 한다(available()=False). 그런 환경에선 여전히 환경변수로 주입 가능.
"""
from __future__ import annotations
import os

SERVICE = "tossbot"
# 환경변수명 → 키체인 필드명
_FIELDS = {
    "TOSS_CLIENT_ID": "toss_client_id",
    "TOSS_CLIENT_SECRET": "toss_client_secret",
}


def _kr():
    """keyring 모듈을 지연 로드. 사용 불가면 None."""
    try:
        import keyring  # noqa: PLC0415
        # 백엔드가 실제로 있는지 확인(없으면 fail 백엔드가 예외를 던짐)
        if keyring.get_keyring().priority <= 0:
            return None
        return keyring
    except Exception:
        return None


def available() -> bool:
    return _kr() is not None


def load_into_env() -> bool:
    """키체인에 저장된 키를 os.environ 으로 로드(기존 환경변수가 있으면 그대로 존중).
    하나라도 새로 채웠으면 True."""
    kr = _kr()
    if kr is None:
        return False
    filled = False
    for env_key, field in _FIELDS.items():
        if os.environ.get(env_key):
            continue  # 이미 env 로 주입돼 있으면 우선
        try:
            val = kr.get_password(SERVICE, field)
        except Exception:
            val = None
        if val:
            os.environ[env_key] = val
            filled = True
    return filled


def save(client_id: str, client_secret: str) -> None:
    """키체인에 저장. 사용 불가하면 RuntimeError."""
    kr = _kr()
    if kr is None:
        raise RuntimeError("OS 키체인(keyring) 백엔드를 사용할 수 없습니다")
    kr.set_password(SERVICE, _FIELDS["TOSS_CLIENT_ID"], client_id)
    kr.set_password(SERVICE, _FIELDS["TOSS_CLIENT_SECRET"], client_secret)


def clear() -> None:
    """저장된 키 삭제(로그아웃)."""
    kr = _kr()
    if kr is None:
        return
    for field in _FIELDS.values():
        try:
            kr.delete_password(SERVICE, field)
        except Exception:
            pass  # 없으면 무시


def status() -> dict:
    """저장 여부만 반환(값은 절대 노출하지 않음)."""
    kr = _kr()
    if kr is None:
        return {"available": False, "has_id": False, "has_secret": False}

    def _has(field: str) -> bool:
        try:
            return bool(kr.get_password(SERVICE, field))
        except Exception:
            return False

    return {
        "available": True,
        "has_id": _has(_FIELDS["TOSS_CLIENT_ID"]),
        "has_secret": _has(_FIELDS["TOSS_CLIENT_SECRET"]),
    }
