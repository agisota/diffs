"""Tests for pair_similarity_score (PR-5.9)."""
from __future__ import annotations

from docdiffops.legal.pair_score import pair_similarity_score, score_band


def _ev(status, severity="medium"):
    return {"status": status, "severity": severity}


def test_empty_events_means_perfect_match():
    assert pair_similarity_score([]) == 100


def test_only_same_events_means_perfect_match():
    assert pair_similarity_score([_ev("same") for _ in range(5)]) == 100


def test_one_low_partial_drops_score_slightly():
    s = pair_similarity_score([_ev("partial", "low")])
    assert 95 <= s < 100


def test_high_contradicts_is_costly():
    s = pair_similarity_score([_ev("contradicts", "high")])
    assert s <= 86


def test_score_floors_at_zero_with_many_high_events():
    events = [_ev("contradicts", "high") for _ in range(20)]
    assert pair_similarity_score(events) == 0


def test_score_does_not_go_below_zero():
    events = [_ev("modified", "high") for _ in range(50)]
    assert pair_similarity_score(events) == 0


def test_added_deleted_costs_less_than_contradicts():
    a = pair_similarity_score([_ev("added", "high"), _ev("deleted", "high")])
    c = pair_similarity_score([_ev("contradicts", "high"), _ev("contradicts", "high")])
    assert a > c


def test_manual_review_costs_something():
    s = pair_similarity_score([_ev("manual_review", "medium")])
    assert s == 97


def test_unknown_status_default_weight():
    s = pair_similarity_score([_ev("ridiculous_status_xyz")])
    assert s == 98


def test_score_band_thresholds():
    assert score_band(100) == "near-identical"
    assert score_band(90) == "near-identical"
    assert score_band(80) == "minor"
    assert score_band(60) == "moderate"
    assert score_band(40) == "major"
    assert score_band(10) == "divergent"


def test_score_returns_int():
    assert isinstance(pair_similarity_score([_ev("partial")]), int)
