from datetime import datetime, timedelta, timezone
import json
import math
import re

import pytest

from tossbot.chart_study import completed_bars, pivots, retest, study
from tossbot.financial_library import DOCUMENT_FILES, document, image_path, library, resources

NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


def bars(closes):
    start = NOW - timedelta(days=100)
    return [{"time": (start+timedelta(days=i)).date().isoformat(), "open": c, "high": c+1, "low": c-1, "close": c, "volume": 100} for i, c in enumerate(closes)]


def test_confirmation_does_not_appear_before_right_hand_bars():
    rows = bars([10, 11, 15, 12, 10, 9, 12, 13])
    assert pivots(rows[:4], span=2) == []
    p = pivots(rows[:5], span=2)[0]
    assert p["time"] == rows[2]["time"]
    assert p["confirmedAt"] == rows[4]["time"]
    # Appending future bars never changes already available pivots.
    later = pivots(rows, span=2)
    assert [p for p in later if p["confirmedIndex"] < 5] == pivots(rows[:5], span=2)
    # Wick and body are separate observations.
    rows[2]["high"] = 20
    rows[2]["open"] = rows[2]["close"] = 11
    assert any(p["index"] == 2 for p in pivots(rows,2,"wick"))
    assert not any(p["index"] == 2 for p in pivots(rows,2,"body"))


def test_invalid_incomplete_duplicate_and_timezone_rows():
    good = bars([10])[0]
    rows = [good, dict(good, volume=200), dict(good, time="broken"), dict(good, time="2026-10-03"), dict(good, high=5), dict(good, volume=math.nan)]
    closed, q = completed_bars(rows, now=NOW)
    assert len(closed) == 1 and closed[0]["volume"] == 200
    assert (q["rejected"], q["duplicates"], q["unclosed"]) == (3,1,1)
    minute = [dict(good, time="2026-10-03T11:58:00Z"), dict(good, time="2026-10-03T12:00:00Z"), dict(good, time="2026-10-03T11:59:00")]
    closed, q = completed_bars(minute, "1m", NOW)
    assert len(closed) == 1 and q["unclosed"] == 1 and q["rejected"] == 1
    assert not q["stale"]


def test_retest_requires_later_follow_through_and_tracks_invalidation():
    rows = bars([99, 99, 102, 101.2, 103, 98])
    rows[3].update(low=99.7, high=102)
    p = {"side": "high", "price": 100, "confirmedIndex": 1, "confirmedAt": rows[1]["time"], "time": rows[0]["time"]}
    assert retest(rows[:3], p, .5)["state"] == "breakout"
    assert retest(rows[:4], p, .5)["state"] == "retest"
    assert retest(rows[:5], p, .5)["state"] == "confirmed"
    assert retest(rows, p, .5)["state"] == "invalidated"
    assert [e["state"] for e in retest(rows,p,.5)["events"]] == ["breakout","retest","confirmed","invalidated"]


def test_volume_denominator_and_volatility_units():
    rows = bars([100 + i * .1 + (i % 2) for i in range(40)])
    rows[-1]["volume"] = 1000
    day = study(rows, now=NOW)
    assert day["metrics"]["rvol20"] == 10  # not 1000/145 incl current bar
    assert day["metrics"]["directionVolume20"] == pytest.approx(900/2900)  # 10 down / 9 normal up / 1 large up
    minute_rows = [dict(r, time=r["time"]+"T00:00:00Z") for r in rows]
    minute = study(minute_rows, "1m", now=NOW)
    assert day["metrics"]["realizedVol20"] == pytest.approx(minute["metrics"]["realizedVol20"] * math.sqrt(252))
    assert minute["metrics"]["volUnit"] == "perMinuteBar"
    assert len(day["overlays"][0]["data"]) == 33  # EMA8 seed needs 8 bars
    assert day["gap"]["earningsVerified"] is False
    json.dumps(day, allow_nan=False)


def test_empty_and_short_data_never_invents_confirmed_structure():
    empty = study([], now=NOW)
    assert empty["structure"] == "insufficient" and empty["quality"]["stale"]
    short = study(bars([100,101,102]), now=NOW)
    assert short["metrics"]["rvol20"] is None
    assert short["metrics"]["realizedVol20"] is None
    assert short["zones"] == [] and short["pivots"] == []
    json.dumps(short, allow_nan=False)


def test_divergence_invalidation_is_not_erased_by_a_rebound(monkeypatch):
    import tossbot.chart_study as module
    rows = bars([100,102,101,98,94,90,95,98,100,103,104,101,96,92,89,85,89,92,83,86])
    def controlled_rsi(values):
        points = [50] * len(values)
        points[5], points[15] = 10,20
        return points
    monkeypatch.setattr(module, "rsi_series", controlled_rsi)
    candidate = study(rows[:18], span=2, now=NOW)["divergences"][0]
    assert candidate["state"] == "candidate"
    assert candidate["availableAt"] == rows[17]["time"]
    invalid = study(rows, span=2, now=NOW)["divergences"][0]
    assert invalid["state"] == "invalidated"
    assert invalid["invalidatedAt"] == rows[18]["time"]


def test_public_library_search_and_links_exclude_private_resources():
    lib = library()
    assert lib["counts"] == {"guides":6,"sources":0,"images":0}
    assert lib["visibility"] == "public" and lib["images"] == []
    assert {d["path"] for d in lib["documents"]} == set(DOCUMENT_FILES)
    assert all(d["kind"] == "guide" and not d["sourceUrl"] for d in lib["documents"])
    assert library("리테스트")["documents"]
    assert library("no-such-term-12345")["documents"] == []
    docs, bodies, images, *_ = resources()
    assert images == {}
    assert all(d["id"] in bodies for d in docs)
    for body in bodies.values():
        assert "docs/financial" not in body and "drive.google.com" not in body
        assert "![" not in body
        for ref in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
            assert ref in DOCUMENT_FILES
    assert all(set(m["docs"]) <= set(bodies) for m in lib["methods"])
    for key in ("../../.env", "01_CHART_STUDY", "source_inventory"):
        with pytest.raises(KeyError):
            document(key)
    with pytest.raises(KeyError):
        image_path("private.png")


def test_public_library_never_discovers_extra_files_or_falls_back(tmp_path, monkeypatch):
    import tossbot.financial_library as module
    original = module.ROOT
    public = tmp_path / "docs" / "public"
    public.mkdir(parents=True)
    private = tmp_path / "docs" / "financial"
    private.mkdir()
    for name in DOCUMENT_FILES:
        (public / name).write_bytes((original / name).read_bytes())
        (private / name).write_text("PRIVATE_SENTINEL", encoding="utf-8")
    (public / "personal.md").write_text("PRIVATE_SENTINEL", encoding="utf-8")
    (private / "source_inventory.json").write_text("PRIVATE_SENTINEL", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", public)
    resources.cache_clear()
    try:
        assert len(library()["documents"]) == 6
        assert library("PRIVATE_SENTINEL")["documents"] == []
        (public / "README.md").unlink()
        resources.cache_clear()
        with pytest.raises(FileNotFoundError):
            library()
    finally:
        resources.cache_clear()


def test_study_and_library_api_are_read_only_and_validate_inputs(api):
    http, _ = api
    response = http.get("/api/chart-study/005930")
    assert response.status_code == 200
    assert response.json()["quality"]["closed"] == 200
    json.dumps(response.json(), allow_nan=False)
    for suffix in ("?span=1", "?span=11", "?basis=invalid", "?interval=5m"):
        assert http.get("/api/chart-study/005930"+suffix).status_code == 422
    lib = http.get("/api/financial/library").json()
    assert lib["counts"] == {"guides":6,"sources":0,"images":0}
    for d in lib["documents"]:
        assert http.get("/api/financial/documents/"+d["id"]).json()["content"]
    for path in ("documents/unknown", "documents/01_CHART_STUDY", "documents/source_inventory",
                 "images/private.png", "images/%2e%2e/%2e%2e/.env", "images/source_inventory.json"):
        assert http.get("/api/financial/"+path).status_code == 404
