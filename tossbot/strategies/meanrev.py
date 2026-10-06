"""평균회귀(meanrev) 전략군."""
from __future__ import annotations
from .base import buy, sell, strategy


@strategy("Z-Score 회귀", "meanrev")
def zscore(f):
    b, p = f["boll"], f["price"]
    if not b or not b["sd"]:
        return None
    z = (p - b["mid"]) / b["sd"]
    if z < -2:
        return buy("Z-Score 회귀", "meanrev", min(1.0, (-z - 2) / 1.5 + 0.5), f"z={z:.1f}(평균 대비 과도이탈↓)")
    if z > 2:
        return sell("Z-Score 회귀", "meanrev", min(1.0, (z - 2) / 1.5 + 0.5), f"z={z:.1f}(평균 대비 과도이탈↑)")
    return None


@strategy("이격도(20) 회귀", "meanrev")
def disparity(f):
    d = f["disparity20"]
    if d is None:
        return None
    if d < 96:
        return buy("이격도 회귀", "meanrev", 0.5, f"이격도 {d:.0f}<96(낙폭과대)")
    if d > 104:
        return sell("이격도 회귀", "meanrev", 0.5, f"이격도 {d:.0f}>104(과열)")
    return None
