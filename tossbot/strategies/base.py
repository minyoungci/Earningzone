"""전략 플러그인 골격 — Signal, 레지스트리, 실행기.

전략 함수는 Features dict를 받아 Signal 또는 None을 반환하고, @strategy 로 자동 등록됩니다.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List

_log = logging.getLogger("tossbot.strategies")


@dataclass
class Signal:
    name: str
    category: str          # trend | momentum | volatility | meanrev | breakout | structure
    action: str            # "BUY" | "SELL" | "NEUTRAL"
    strength: float = 0.5  # 0..1 (신뢰도)
    reason: str = ""

    @property
    def score(self) -> float:
        s = {"BUY": 1.0, "SELL": -1.0}.get(self.action, 0.0)
        return s * max(0.0, min(1.0, self.strength))


REGISTRY: List[Callable] = []


def strategy(name: str, category: str, *, registry=None):
    def deco(fn):
        fn.s_name = name
        fn.s_category = category
        (REGISTRY if registry is None else registry).append(fn)
        return fn
    return deco


def buy(name, category, strength, reason):
    return Signal(name, category, "BUY", strength, reason)


def sell(name, category, strength, reason):
    return Signal(name, category, "SELL", strength, reason)


class SignalList(List[Signal]):
    """run_all 결과 — Signal 리스트이면서 .errors 로 죽은 전략 목록을 노출.

    기존 호출처(analysis.py)는 이 객체를 그냥 리스트처럼 순회/저장하므로
    반환 계약을 깨지 않는다. 추가로 .errors == [{strategy, msg}] 가 붙는다.
    """
    errors: List[Dict[str, str]]


def run_all(feats, registry=None) -> SignalList:
    out: SignalList = SignalList()
    out.errors = []
    if not feats or feats.get("error"):
        return out
    for fn in (REGISTRY if registry is None else registry):
        try:
            sig = fn(feats)
        except Exception as e:
            # 예외를 조용히 삼키지 말고 전략명과 함께 로깅 + errors 에 노출.
            sname = getattr(fn, "s_name", getattr(fn, "__name__", "?"))
            _log.exception("strategy %r raised", sname)
            out.errors.append({"strategy": sname, "msg": str(e)})
            sig = None
        if sig and sig.action in ("BUY", "SELL"):
            out.append(sig)
    return out
