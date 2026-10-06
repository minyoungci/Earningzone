"""전략 패키지 — import 시 모든 전략이 REGISTRY에 자동 등록됩니다.

새 전략 추가: strategies/ 아래 모듈을 만들고 @strategy 데코레이터로 함수를 등록한 뒤,
아래 import 목록에 모듈명을 추가하면 됩니다.
"""
from .base import REGISTRY, Signal, buy, run_all, sell, strategy  # noqa: F401

# 전략 모듈 로드(등록 트리거)
from . import trend        # noqa: F401,E402
from . import momentum     # noqa: F401,E402
from . import volatility   # noqa: F401,E402
from . import meanrev      # noqa: F401,E402
from . import breakout     # noqa: F401,E402
from . import structure    # noqa: F401,E402
# 확장 전략군 (mega-build)
from . import harmonic         # noqa: F401,E402
from . import vwap_bands       # noqa: F401,E402
from . import ichimoku_detail  # noqa: F401,E402
from . import supertrend       # noqa: F401,E402
from . import stochrsi_flow    # noqa: F401,E402
from . import candles_ext      # noqa: F401,E402
from . import trend_ext        # noqa: F401,E402
from . import meanrev_ext      # noqa: F401,E402
from . import volume_ext       # noqa: F401,E402
from . import pivots_ext       # noqa: F401,E402
# 분봉 전략은 별도 레지스트리로 로드하여 일봉 전략 수와 점수에 영향을 주지 않는다.


def for_interval(interval):
    if interval == "1m":
        from .intraday import INTRADAY_REGISTRY
        return REGISTRY + INTRADAY_REGISTRY
    return REGISTRY


def categories():
    cats = {}
    for fn in REGISTRY:
        cats.setdefault(fn.s_category, []).append(fn.s_name)
    return cats
