"""주문 실행 브로커 추상화 — 분석(토스 데이터)은 공유, '주문 집행'만 갈아끼운다.

- TossBroker : 기존 TossClient.place_order 래핑 (DRY_RUN 게이트는 client 내부).
- KISBroker  : 한국투자증권 KIS Developers (kis.KISClient, DRY_RUN + 모의투자 VTS 이중 안전).

활성 브로커는 .broker_state.json({"broker": "toss"|"kis"}) 에 저장되어 재시작에도 유지된다.
비밀(키)은 절대 저장하지 않는다 — 키는 환경변수로만.
"""
from __future__ import annotations

import json
import os
import threading

from . import config
from .kis import KISClient

_lock = threading.Lock()
_kis_client = None  # 토큰 캐시 공유를 위한 싱글턴


def _kis():
    global _kis_client
    with _lock:
        if _kis_client is None:
            _kis_client = KISClient()
        return _kis_client


class TossBroker:
    name = "toss"
    label = "토스증권"

    def __init__(self, client):
        self.client = client

    @property
    def dry_run(self):
        return self.client.dry_run

    def configured(self):
        return bool(config.CLIENT_ID and config.CLIENT_SECRET)

    def place_order(self, symbol, side, qty, price=None):
        order_type = "LIMIT" if price else "MARKET"
        return self.client.place_order(symbol, side.upper(), order_type,
                                       quantity=int(qty), price=price)

    def summary(self):
        return {
            "name": self.name, "label": self.label,
            "configured": self.configured(),
            "dryRun": self.dry_run,
            "mode": "DRY_RUN" if self.dry_run else "LIVE",
            "note": "분석 데이터 공급 + 주문 실행",
        }


class KISBroker:
    name = "kis"
    label = "한국투자증권"

    def __init__(self):
        self.client = _kis()

    @property
    def dry_run(self):
        return config.DRY_RUN

    def configured(self):
        return self.client.configured()

    def place_order(self, symbol, side, qty, price=None):
        return self.client.place_order(symbol, side, qty, price)

    def summary(self):
        c = self.client
        return {
            "name": self.name, "label": self.label,
            "configured": c.configured(),
            "dryRun": config.DRY_RUN,
            "paper": c.paper,
            "mode": ("DRY_RUN" if config.DRY_RUN
                     else ("모의투자(VTS)" if c.paper else "실전")),
            "note": "주문 실행 전용 (KIS Developers)" if c.configured()
                    else "미연결 — KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT 환경변수 필요",
        }


BROKERS = ("toss", "kis")


def _load_state():
    try:
        with open(config.BROKER_STATE_FILE, encoding="utf-8") as f:
            b = json.load(f).get("broker", "")
            if b in BROKERS:
                return b
    except Exception:
        pass
    return config.BROKER_DEFAULT if config.BROKER_DEFAULT in BROKERS else "toss"


def active_name():
    with _lock:
        return _load_state()


def select(name):
    """활성 브로커 변경. 잘못된 이름이면 ValueError."""
    name = (name or "").lower()
    if name not in BROKERS:
        raise ValueError(f"지원하지 않는 브로커: {name} (toss|kis)")
    with _lock:
        tmp = config.BROKER_STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"broker": name}, f)
        os.replace(tmp, config.BROKER_STATE_FILE)
    return name


def get(toss_client, name=None):
    """활성(또는 지정) 브로커 인스턴스 반환. toss_client 는 기존 TossClient."""
    name = (name or active_name()).lower()
    return KISBroker() if name == "kis" else TossBroker(toss_client)


def status(toss_client):
    """UI 용 전체 상태: 활성 브로커 + 각 브로커 요약."""
    return {
        "active": active_name(),
        "dryRun": config.DRY_RUN,
        "brokers": [TossBroker(toss_client).summary(), KISBroker().summary()],
        "note": "분석/차트/시그널은 토스 데이터 기반으로 공유되며, 브로커는 자동매매 '주문 실행'에만 적용됩니다.",
    }
