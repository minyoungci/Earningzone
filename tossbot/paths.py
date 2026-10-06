"""상태 파일 저장 위치 결정.

- 소스로 실행: 프로젝트 루트(기존 동작 — 개발 중 .sim_state.json 등이 그대로 유지).
- 패키징(PyInstaller frozen): __file__ 이 임시 추출 폴더(_MEIPASS)를 가리켜 재시작마다
  사라지므로, %APPDATA%\\tossbot (Windows) 등 영구·쓰기가능 폴더를 쓴다.
- TOSSBOT_DATA_DIR 환경변수로 명시 지정 시 최우선.
"""
from __future__ import annotations
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    env = os.environ.get("TOSSBOT_DATA_DIR")
    if env:
        d = env
    elif getattr(sys, "frozen", False):  # PyInstaller 등으로 패키징된 실행
        base = (os.environ.get("APPDATA")
                or os.path.join(os.path.expanduser("~"), ".local", "share"))
        d = os.path.join(base, "tossbot")
    else:
        d = _PROJECT_ROOT
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def state_path(filename: str) -> str:
    """영구 상태 파일의 절대 경로."""
    return os.path.join(data_dir(), filename)
