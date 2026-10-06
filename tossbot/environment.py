"""Load a local .env without overwriting explicit process settings."""
from pathlib import Path
import os
import sys


def load_env(root):
    path = Path(root) / ".env"
    if not path.is_file():
        return
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key:
                os.environ.setdefault(key, value)
    except OSError:
        print("[warn] .env 파일을 읽지 못했습니다", file=sys.stderr)
