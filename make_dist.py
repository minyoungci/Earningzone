"""배포용 zip 생성 — 다른 환경에서 바로 실행 가능한 tossbot-app.zip 을 만든다.

node_modules / 캐시 / 비밀(.env, paper_state) 등은 제외하고, 빌드된 프론트(web/dist)는 포함.
사용: python make_dist.py
"""
import os
import hashlib
import json
from datetime import datetime, timezone
import zipfile

from tossbot.financial_library import DOCUMENT_FILES

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "tossbot-app.zip")
TOP = "tossbot-app"  # zip 내부 최상위 폴더

PUBLIC_FILES = {"docs/public/" + name for name in DOCUMENT_FILES}
INCLUDE_DIRS = ["tossbot", "server", "web", "tests"]
EXTRA_FILES = [
    "run.py", "run.bat", "run.sh", "build_master.py", ".env.example", ".gitignore", ".gitattributes",
    "README.md", "README.ko.md", "NOTICE", "DIST_README.md", "TOSSBOT_README.md", "TOSS_GUIDE.md",
    "TELEGRAM_GUIDE.md", "selftest.py", "desktop.py", "build_desktop.py", "DESKTOP.md",
    "make_dist.py",
] + sorted(PUBLIC_FILES)
SKIP_DIRS = {"node_modules", "__pycache__", ".venv", ".git", ".vite",
             ".guide_sections", ".ts_sections", "dist-ssr", ".pytest_cache",
             ".tmp", ".ds-sync", ".codex", "discord_collected"}
SKIP_EXTS = {".pyc", ".pyo", ".log"}
# 비밀·로컬 상태 파일은 절대 배포 zip 에 넣지 않는다
SKIP_FILES = {".env", ".paper_state.json", "tossbot-app.zip",
              ".sim_state.json", ".sim_state.backup.json", ".broker_state.json",
              ".access_token.txt", ".tunnel_url.txt", "INSIGHTS.md",
              "source_inventory.json", "stock_master.json", "MAINTENANCE_REPORT.md", "UI_DESIGN_REPORT.md",
              "FINANCIAL_TOOLS_REPORT.md", "CHART_EXECUTION_REPORT.md"}


def distributable(relative):
    """Enforce privacy even if a future caller includes a parent docs directory."""
    rel = relative.replace("\\", "/")
    parts = rel.split("/")
    name = parts[-1]
    if any(p.casefold() in {d.casefold() for d in SKIP_DIRS} for p in parts[:-1]):
        return False
    if name.casefold() in {f.casefold() for f in SKIP_FILES} or os.path.splitext(name)[1].lower() in SKIP_EXTS:
        return False
    if name.casefold().startswith("discord_") and name.lower().endswith(".md"):
        return False
    return not rel.casefold().startswith("docs/") or rel in PUBLIC_FILES


def add_tree(z, base):
    src = os.path.join(ROOT, base)
    count = 0
    for dp, dns, fns in os.walk(src):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, ROOT)
            if not distributable(rel):
                continue
            z.write(full, TOP + "/" + rel.replace(os.sep, "/"))
            count += 1
    return count


def main():
    total = 0
    temporary = OUT + ".tmp"
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for d in INCLUDE_DIRS:
            if os.path.isdir(os.path.join(ROOT, d)):
                total += add_tree(z, d)
        for f in EXTRA_FILES:
            p = os.path.join(ROOT, f)
            if os.path.isfile(p) and distributable(f):
                z.write(p, TOP + "/" + f.replace(os.sep, "/"))
                total += 1
    # Reopen after writing: on Windows, in-memory ZipInfo.orig_filename may
    # contain backslashes while the stored ZIP header uses forward slashes.
    with zipfile.ZipFile(temporary, "a", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        manifest = {"builtAt": datetime.now(timezone.utc).isoformat(), "files": {}}
        for entry in z.namelist():
            rel = entry.removeprefix(TOP + "/")
            manifest["files"][rel] = hashlib.sha256(z.read(entry)).hexdigest()
        payload = json.dumps(manifest, ensure_ascii=False, indent=2)
        z.writestr(TOP + "/BUILD_MANIFEST.json", payload)
        total += 1
    with zipfile.ZipFile(temporary) as check:
        if check.testzip() is not None:
            raise RuntimeError("배포 ZIP 무결성 검증 실패 — 이전 ZIP을 보존합니다")
    os.replace(temporary, OUT)
    with open(os.path.join(ROOT, "BUILD_MANIFEST.json"), "w", encoding="utf-8") as f:
        f.write(payload)
    size = os.path.getsize(OUT)
    print(f"created {OUT}")
    print(f"  files: {total}   size: {size/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
