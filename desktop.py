#!/usr/bin/env python3
"""tossbot 데스크톱 앱 — 네이티브 창(pywebview) + 내장 FastAPI 서버.

동작:
  1) OS 키체인(keyring)에 저장된 토스 키를 환경변수로 로드(없으면 앱 설정 화면에서 입력).
  2) 빈 포트를 잡아 uvicorn(server.app) 을 백그라운드 스레드로 기동.
  3) 서버가 뜨면 그 주소를 가리키는 네이티브 웹뷰 창을 연다(Windows=Edge WebView2).

DRY_RUN 기본 ON — 실주문은 나가지 않는다.
빌드: `python build_desktop.py` → dist/tossbot.exe
진단 로그: APPDATA/tossbot/desktop.log (창 모드에서도 기동 문제를 여기서 확인)
"""
from __future__ import annotations
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

# PyInstaller 번들/소스 실행 양쪽에서 프로젝트 루트를 sys.path 에 둔다.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── 진단 로그(항상 파일) ─ 콘솔 없는 창 모드에서도 기동 문제를 남긴다 ──
_LOG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "tossbot")
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
    _LOG_PATH = os.path.join(_LOG_DIR, "desktop.log")
except Exception:
    _LOG_PATH = os.path.join(os.path.expanduser("~"), "tossbot_desktop.log")


def _log(msg: str) -> None:
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


# 창 모드(PyInstaller)에서 sys.stdout/stderr 가 None 이면 안전한 싱크로 교체
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(url: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.time() < deadline:
        try:
            with opener.open(url, timeout=1):
                pass
            return True
        except Exception:
            time.sleep(0.15)
    return False


def _start_server(port: int):
    """uvicorn 을 백그라운드 스레드에서 기동. GUI 루프가 메인 스레드를 써야 하므로
    시그널 핸들러 설치를 끈다(스레드에서 signal 설치는 예외)."""
    import uvicorn
    from server.app import app as fastapi_app  # 키 로드 뒤에 import(=config 가 최신 env 반영)

    cfg = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port,
                         log_level="warning", log_config=None)
    server = uvicorn.Server(cfg)
    server.install_signal_handlers = lambda: None

    def _serve():
        try:
            server.run()
        except Exception:
            _log("[server thread ERROR]\n" + traceback.format_exc())

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return server, thread


def main():
    _log("=== start (frozen=%s, py=%s) ===" % (getattr(sys, "frozen", False), sys.version.split()[0]))

    # 1) 키체인 → 환경변수 (있으면). 없으면 앱 설정 화면(SetupBanner)에서 입력받는다.
    try:
        from tossbot.environment import load_env
        load_env(_HERE)
        from tossbot import secrets_store
        secrets_store.load_into_env()
        _log("keychain keys loaded: %s" % bool(os.environ.get("TOSS_CLIENT_ID")))
    except Exception:
        _log("[secrets_store ERROR]\n" + traceback.format_exc())

    # 2) 서버 기동
    port = _free_port()
    _log("starting embedded server on 127.0.0.1:%d" % port)
    server, thread = _start_server(port)
    base = f"http://127.0.0.1:{port}"
    ready = _wait_ready(f"{base}/api/auth")
    _log("server ready=%s" % ready)
    if not ready:
        server.should_exit = True
        raise RuntimeError("내장 서버를 시작하지 못했습니다. desktop.log를 확인하세요.")

    # 3) 네이티브 창
    try:
        import webview  # pywebview
        _log("opening webview window -> %s" % base)
        webview.create_window(
            "tossbot — 토스증권 퀀트 워크스테이션",
            f"{base}/",
            width=1440, height=900, min_size=(1024, 680),
        )
        webview.start()  # 창이 닫히면 반환 → 데몬 서버 스레드와 함께 프로세스 종료
        _log("webview closed — exiting")
    except Exception:
        _log("[webview ERROR]\n" + traceback.format_exc())
        raise
    finally:
        server.should_exit = True
        thread.join(timeout=15)


def _selftest(report_path):
    """Verify the frozen server and SPA without a GUI, keys, or external calls."""
    import json
    import tempfile
    for key in ("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL", "ACCESS_TOKEN"):
        os.environ[key] = ""
    os.environ["TOSS_DRY_RUN"] = "1"
    with tempfile.TemporaryDirectory(prefix="tossbot-selftest-") as data:
        os.environ["TOSSBOT_DATA_DIR"] = data
        port = _free_port()
        server, thread = _start_server(port)
        base = f"http://127.0.0.1:{port}"
        result = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
        try:
            if not _wait_ready(base + "/api/auth"):
                raise RuntimeError("server readiness failed")
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(base + "/api/health", timeout=3) as response:
                result["health"] = json.load(response)
            with opener.open(base, timeout=3) as response:
                html = response.read().decode("utf-8")
                result["spa"] = response.status == 200 and "/assets/" in html
            import re
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
            for asset in assets:
                with opener.open(base + asset, timeout=3) as response:
                    assert response.status == 200
            result["assets"] = len(assets)
            assert result["health"]["strategies"] == 94 and result["health"]["dryRun"] is True
            assert result["spa"] and assets
            with opener.open(base + "/api/financial/library", timeout=3) as response:
                financial = json.load(response)
            assert financial["counts"] == {"guides": 6, "sources": 0, "images": 0}
            assert financial["visibility"] == "public" and financial["images"] == []
            for item in financial["documents"]:
                with opener.open(base + "/api/financial/documents/" + item["id"], timeout=3) as response:
                    assert json.load(response)["content"]
            from urllib.error import HTTPError
            for path in ("documents/01_CHART_STUDY", "documents/source_inventory", "images/private.png"):
                try:
                    opener.open(base + "/api/financial/" + path, timeout=3)
                except HTTPError as error:
                    assert error.code == 404
                else:
                    raise AssertionError("Private resource unexpectedly accessible")
            if getattr(sys, "frozen", False):
                assert not (Path(sys._MEIPASS) / "docs" / "financial").exists()
            result["privateResourcesBlocked"] = True
            result["financial"] = financial["counts"]
            with opener.open(base + "/openapi.json", timeout=3) as response:
                schema = json.load(response)
            assert "/api/chart-timing/{symbol}" in schema["paths"]
            assert schema["components"]["schemas"]["AutopilotIn"]["properties"]["strategy"]["default"] == "legacy"
            from datetime import datetime, timedelta, timezone
            from tossbot import autopilot, chart_execution, sim, quant
            assert "check_stop" in autopilot._try_chart_entries.__code__.co_varnames
            assert "include_symbols" in quant.screen.__code__.co_varnames
            plan = {"signalId": "frozen-policy-check", "policy": chart_execution.VERSION,
                    "stop": 95, "target": 120, "entryLow": 99, "entryHigh": 104,
                    "expiresAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
            size = chart_execution.entry_size(plan, 100, 10000, 10000, 10000)
            assert size["qty"] > 0 and size["riskKrw"] <= 50
            sim.order("005930", "BUY", 1, 100, execution_plan=plan)
            sim._cache_key = sim._cache_state = None
            assert sim.execution_plans()["005930"]["stop"] == 95
            autopilot._try_chart_entries([
                {"symbol": "000660", "currency": "KRW", "timing": {"eligible": True,
                 "plan": {**plan, "signalId": "frozen-quote-guard"}}}], {"000660": 100}, 3, 10000)
            assert sim.held_symbols() == ["005930"]
            sim.order("005930", "SELL", 1, 94)
            try:
                sim.order("005930", "BUY", 1, 100, execution_plan=plan)
            except sim.SimError:
                pass
            else:
                raise AssertionError("A used chart signal must not reenter")
            result["chartPolicy"] = {"version": chart_execution.VERSION, "riskSizing": True,
                                     "persistedPlan": True, "reentryGuard": True, "stopGuard": True,
                                     "heldSymbolScan": True, "quoteValuationGuard": True}
            from tossbot import quant
            from urllib.error import URLError
            class OfflineMarket:
                def candles(self, *args, **kwargs):
                    raise URLError("offline selftest")
            try:
                quant.screen(OfflineMarket(), universe=[("005930", "offline")])
            except URLError:
                result["networkFailureGuard"] = True
            else:
                raise AssertionError("Network errors must not become an empty scan")
            result["ok"] = True
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            server.should_exit = True
            thread.join(timeout=15)
        with open(report_path, "w", encoding="utf-8") as report:
            json.dump(result, report, indent=2)
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    if "--selftest-report" in sys.argv:
        index = sys.argv.index("--selftest-report")
        raise SystemExit(_selftest(sys.argv[index + 1]))
    try:
        main()
    except Exception:
        _log("[main ERROR]\n" + traceback.format_exc())
        raise
