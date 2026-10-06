"""Local browser launcher with a free port and a readiness check."""
import argparse
from pathlib import Path
import socket
import sys
import threading
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def available_port(preferred=8000):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    from tossbot.environment import load_env
    load_env(ROOT)
    from tossbot import secrets_store
    secrets_store.load_into_env()
    import uvicorn

    port = available_port(args.port)
    url = f"http://127.0.0.1:{port}"
    print(f"[실행] {url}  (종료: Ctrl+C)", flush=True)
    finished = threading.Event()
    def open_when_ready():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(100):
            if finished.is_set():
                return
            try:
                with opener.open(url + "/api/auth", timeout=1):
                    webbrowser.open(url)
                    return
            except OSError:
                finished.wait(0.2)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        uvicorn.run("server.app:app", host="127.0.0.1", port=port)
    finally:
        finished.set()


if __name__ == "__main__":
    main()
