"""Tests for cross-pair event clustering."""
from __future__ import annotations

from docdiffops.legal.cross_pair import _normalize_topic, cluster_events


def _ev(*, status, topic, severity="medium", pair_id="p1", event_id=None,
        comparison_type="llm_pair_diff", explanation="") -> dict:
    return {
        "status": status,
        "severity": severity,
        "topic": topic,
        "pair_id": pair_id,
        "event_id": event_id or f"evt_{abs(hash((status, topic, pair_id))) % 10**8:08x}",
        "comparison_type": comparison_type,
        "explanation_short": explanation,
    }


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def test_normalize_collapses_punctuation_and_case():
    assert _normalize_topic("Указ о миграционной политике") == "указ о миграционной политике"
    assert _normalize_topic('"Указ о миграционной политике."') == "указ о миграционной политике"
    assert _normalize_topic("УКАЗ — о  миграционной политике") == "указ о миграционной политике"


def test_normalize_caps_at_80_chars():
    out = _normalize_topic("a" * 200)
    assert len(out) <= 80


def test_normalize_handles_none():
    assert _normalize_topic("") == ""
    assert _normalize_topic(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# cluster_events
# ---------------------------------------------------------------------------


def test_cluster_groups_same_status_topic_across_pairs():
    events = [
        _ev(status="added", topic="Указ о миграционной политике", pair_id="p1"),
        _ev(status="added", topic="указ о миграционной политике", pair_id="p2"),
        _ev(status="added", topic="Указ о миграционной политике.", pair_id="p3"),
    ]
    out = cluster_events(events)
    assert len(out) == 1
    assert out[0]["count"] == 3
    assert sorted(out[0]["pair_ids"]) == ["p1", "p2", "p3"]


def test_cluster_keeps_distinct_status_separate():
    events = [
        _ev(status="added", topic="X", pair_id="p1"),
        _ev(status="deleted", topic="X", pair_id="p2"),
    ]
    out = cluster_events(events)
    assert len(out) == 2
    statuses = sorted(c["status"] for c in out)
    assert statuses == ["added", "deleted"]


def test_cluster_keeps_distinct_topics_separate():
    events = [
        _ev(status="added", topic="Указ", pair_id="p1"),
        _ev(status="added", topic="Концепция", pair_id="p2"),
    ]
    out = cluster_events(events)
    assert len(out) == 2


def test_cluster_severity_is_worst_in_cluster():
    events = [
        _ev(status="added", topic="X", severity="low", pair_id="p1"),
        _ev(status="added", topic="X", severity="high", pair_id="p2"),
        _ev(status="added", topic="X", severity="medium", pair_id="p3"),
    ]
    out = cluster_events(events)
    assert out[0]["severity"] == "high"


def test_cluster_collects_comparison_types():
    events = [
        _ev(status="modified", topic="X", comparison_type="llm_pair_diff"),
        _ev(status="modified", topic="X", comparison_type="legal_structural_diff"),
    ]
    out = cluster_events(events)
    assert "llm_pair_diff" in out[0]["comparison_types"]
    assert "legal_structural_diff" in out[0]["comparison_types"]


def test_cluster_collects_up_to_3_distinct_explanations():
    events = [
        _ev(status="added", topic="X", explanation="Объяснение раз."),
        _ev(status="added", topic="X", explanation="Объяснение два."),
        _ev(status="added", topic="X", explanation="Объяснение три."),
        _ev(status="added", topic="X", explanation="Объяснение четыре."),
        _ev(status="added", topic="X", explanation="Объяснение раз."),  # dup
    ]
    out = cluster_events(events)
    assert len(out[0]["explanations"]) == 3


def test_cluster_falls_back_to_explanation_when_no_topic():
    events = [
        _ev(status="added", topic="", explanation="Конкретный значимый тезис"),
        _ev(status="added", topic="", explanation="Конкретный значимый тезис"),
    ]
    out = cluster_events(events)
    assert len(out) == 1
    assert out[0]["count"] == 2


def test_cluster_skips_truly_empty_events():
    events = [
        _ev(status="added", topic="", explanation=""),
    ]
    out = cluster_events(events)
    assert out == []


def test_cluster_sorts_high_severity_first():
    events = [
        _ev(status="added", topic="A", severity="low"),
        _ev(status="added", topic="B", severity="high"),
        _ev(status="added", topic="C", severity="medium"),
    ]
    out = cluster_events(events)
    assert [c["topic"] for c in out] == ["B", "C", "A"]


def test_cluster_sorts_high_count_before_low_at_same_severity():
    events = [
        _ev(status="added", topic="rare", severity="medium", pair_id="p1"),
        _ev(status="added", topic="frequent", severity="medium", pair_id="p1"),
        _ev(status="added", topic="frequent", severity="medium", pair_id="p2"),
        _ev(status="added", topic="frequent", severity="medium", pair_id="p3"),
    ]
    out = cluster_events(events)
    assert out[0]["topic"] == "frequent"
    assert out[0]["count"] == 3


def test_cluster_id_is_deterministic_and_url_safe():
    events = [_ev(status="added", topic="Указ о миграционной политике")]
    a = cluster_events(events)[0]["cluster_id"]
    b = cluster_events(events)[0]["cluster_id"]
    assert a == b
    assert a.startswith("cl_")
    assert " " not in a
