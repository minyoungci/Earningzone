#!/usr/bin/env python3
"""tossbot 데스크톱 앱 빌드 — PyInstaller onefile → dist/tossbot.exe

준비(최초 1회):
  pip install pywebview keyring pyinstaller "uvicorn[standard]" fastapi
  (Windows 키체인 백엔드용) pip install pywin32
  cd web && npm run build      # 프론트엔드가 web/dist 에 빌드돼 있어야 함

빌드:
  python build_desktop.py            # 창 모드(콘솔 없음)
  python build_desktop.py --console  # 콘솔 유지(첫 디버그에 유용)
"""
import os
import sys

from tossbot.financial_library import DOCUMENT_FILES

HERE = os.path.dirname(os.path.abspath(__file__))
SEP = os.pathsep  # Windows ';' / POSIX ':'


def main():
    try:
        import PyInstaller.__main__
    except Exception:
        print("[오류] PyInstaller 가 없습니다.  pip install pyinstaller", file=sys.stderr)
        sys.exit(1)

    dist_web = os.path.join(HERE, "web", "dist")
    if not os.path.isdir(dist_web):
        print("[오류] web/dist 가 없습니다. 먼저 `cd web && npm run build` 실행.", file=sys.stderr)
        sys.exit(1)

    console = "--console" in sys.argv
    # onedir: 매 실행 재압축 없이 폴더에서 바로 실행 → 콜드스타트 ~1-2초(onefile 은 12-15초).
    # 배포는 dist/tossbot 폴더를 통째로 zip. 자주 여는 데스크톱 앱엔 onedir 권장.
    onedir = "--onedir" in sys.argv

    args = [
        os.path.join(HERE, "desktop.py"),
        "--name=tossbot",
        ("--onedir" if onedir else "--onefile"),
        "--noconfirm",
        "--clean",
        f"--distpath={os.path.join(HERE, 'dist')}",
        f"--workpath={os.path.join(HERE, 'build')}",
        f"--specpath={HERE}",
        # 번들된 SPA — 런타임에 server.app 이 web/dist 를 서빙
        f"--add-data={dist_web}{SEP}web/dist",
    ]
    # Use the same explicit public article list as the API and ZIP builder.
    # Never collect the personal archive or arbitrary files from a docs folder.
    for name in DOCUMENT_FILES:
        args.append(f"--add-data={os.path.join(HERE, 'docs', 'public', name)}{SEP}docs/public")
    # 종목 검색 마스터(있으면 전체 종목 검색; 없으면 큐레이션 폴백)
    master = os.path.join(HERE, "tossbot", "stock_master.json")
    if os.path.exists(master):
        args.append(f"--add-data={master}{SEP}tossbot")
    args += [
        # 동적 임포트가 많은 패키지는 전량 수집
        "--collect-all=uvicorn",
        "--collect-all=webview",
        "--collect-all=keyring",
        "--copy-metadata=keyring",
        "--collect-submodules=fastapi",
        "--collect-submodules=starlette",
        "--collect-submodules=tossbot",
        "--collect-submodules=server",
        # 키체인 백엔드(플랫폼별 — 미존재 플랫폼은 무해하게 스킵)
        "--hidden-import=keyring.backends.Windows",
        "--hidden-import=keyring.backends.SecretService",
        "--hidden-import=keyring.backends.macOS",
    ]
    icon = os.path.join(HERE, "assets", "tossbot.ico")
    if os.path.exists(icon):
        args.append(f"--icon={icon}")
    if not console:
        args.append("--windowed")

    print("[빌드] PyInstaller 실행 …", "(콘솔 모드)" if console else "(창 모드)")
    PyInstaller.__main__.run(args)
    filename = "tossbot.exe" if os.name == "nt" else "tossbot"
    out = os.path.join(HERE, "dist", "tossbot", filename) if onedir else os.path.join(HERE, "dist", filename)
    print(f"\n[완료] {out}")


if __name__ == "__main__":
    main()
