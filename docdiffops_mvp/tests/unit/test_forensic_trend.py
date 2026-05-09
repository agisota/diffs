"""Tests for forensic_trend.compute_trend — multi-bundle time-series."""
from __future__ import annotations

import pytest

from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_trend import compute_trend


def _bundle(statuses: dict[str, str]) -> dict:
    docs = [{"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
            {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"}]
    pairs = [{"id": pid, "left": "D1", "right": "D2",
              "events": [{"status": st}]}
             for pid, st in statuses.items()]
    return build_forensic_bundle(documents=docs, pairs=pairs, events=[],
                                 amendment_graph={})


def test_single_bundle_yields_one_timeline_entry():
    b = _bundle({"P1": "same"})
    t = compute_trend([b])
    assert t["bundle_count"] == 1
    assert len(t["timeline"]) == 1
    assert t["trend_direction"] == "stable"


def test_improving_trend_when_match_share_grows():
    # 0% match → 100% match
    bad = _bundle({"P1": "contradicts", "P2": "contradicts"})
    good = _bundle({"P1": "same", "P2": "same"})
    t = compute_trend([bad, good])
    assert t["trend_direction"] == "improving"
    assert t["match_share_series"][0] == 0
    assert t["match_share_series"][-1] == 100


def test_degrading_trend_when_match_share_drops():
    good = _bundle({"P1": "same", "P2": "same"})
    bad = _bundle({"P1": "contradicts", "P2": "contradicts"})
    t = compute_trend([good, bad])
    assert t["trend_direction"] == "degrading"


def test_stable_trend_when_match_share_unchanged():
    b1 = _bundle({"P1": "same", "P2": "contradicts"})
    b2 = _bundle({"P1": "same", "P2": "contradicts"})
    t = compute_trend([b1, b2])
    assert t["trend_direction"] == "stable"


def test_status_series_aligns_with_timeline_length():
    b1 = _bundle({"P1": "same"})
    b2 = _bundle({"P1": "partial"})
    b3 = _bundle({"P1": "contradicts"})
    t = compute_trend([b1, b2, b3])
    assert len(t["status_series"]["match"]) == 3
    assert t["status_series"]["match"] == [1, 0, 0]
    assert t["status_series"]["partial_overlap"] == [0, 1, 0]
    assert t["status_series"]["contradiction"] == [0, 0, 1]


def test_contradiction_series_tracks_contradiction_count():
    b1 = _bundle({"P1": "same"})
    b2 = _bundle({"P1": "contradicts", "P2": "contradicts"})
    t = compute_trend([b1, b2])
    assert t["contradiction_series"] == [0, 2]


def test_schema_version_is_v8_trend():
    b = _bundle({"P1": "same"})
    t = compute_trend([b])
    assert t["schema_version"] == "v8-trend"


def test_empty_input_raises_value_error():
    with pytest.raises(ValueError, match="empty"):
        compute_trend([])


def test_incompatible_schema_version_raises_value_error():
    b = _bundle({"P1": "same"})
    bad = dict(b, schema_version="v7.0")
    with pytest.raises(ValueError, match="incompatible schema_version"):
        compute_trend([b, bad])


def test_match_share_is_rounded_to_two_decimals():
    # 1 match out of 3 pairs → 33.33%
    b = _bundle({"P1": "same", "P2": "contradicts", "P3": "partial"})
    t = compute_trend([b])
    assert t["timeline"][0]["match_share"] == 33.33
