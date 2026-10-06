#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "[오류] Python 3.10+가 필요합니다."; exit 1; }
"$PY" -c 'import sys; assert sys.version_info >= (3, 10)' || { echo "[오류] Python 3.10+가 필요합니다."; exit 1; }
[ -f .venv/bin/python ] || "$PY" -m venv .venv
source .venv/bin/activate
if ! python server/check_requirements.py; then
  python -m pip install --disable-pip-version-check -r server/requirements.txt
fi
exec python server/launch.py
