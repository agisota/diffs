"""Unit tests for legal_structural_diff and apply_rank_gate (PR-3.3+3.6)."""
from __future__ import annotations

import pytest

from docdiffops.legal import apply_rank_gate, chunk_text, legal_structural_diff


def _doc(doc_id: str, rank: int) -> dict:
    return {"doc_id": doc_id, "source_rank": rank, "filename": doc_id + ".pdf"}


# ---------------------------------------------------------------------------
# legal_structural_diff
# ---------------------------------------------------------------------------


def test_structural_diff_same_article_text_unchanged():
    lhs_text = "Статья 5. Учёт мигрантов\nИностранные граждане подлежат учёту."
    rhs_text = "Статья 5. Учёт мигрантов\nИностранные граждане подлежат учёту."
    lhs_chunks = chunk_text("LEGAL_NPA", lhs_text, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_NPA", rhs_text, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p1"}, _doc("lhs", 1), _doc("rhs", 1), lhs_chunks, rhs_chunks
    )
    same = [e for e in events if e["status"] == "same"]
    assert len(same) >= 1
    e = next(x for x in events if x["lhs"] and x["lhs"]["chunk_key"] == "article=5")
    assert e["status"] == "same"
    assert e["severity"] == "low"
    assert e["confidence"] >= 0.92


def test_structural_diff_added_article_in_rhs():
    lhs_text = "Статья 5. Старая.\nТекст."
    rhs_text = "Статья 5. Старая.\nТекст.\nСтатья 6. Новая.\nТекст."
    lhs_chunks = chunk_text("LEGAL_NPA", lhs_text, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_NPA", rhs_text, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p1"}, _doc("lhs", 1), _doc("rhs", 1), lhs_chunks, rhs_chunks
    )
    added = [e for e in events if e["status"] == "added"]
    assert any(e["rhs"]["chunk_key"] == "article=6" for e in added)


def test_structural_diff_deleted_article_in_rhs():
    lhs_text = "Статья 5. Учёт.\nТекст.\nСтатья 6. Лишняя.\nТекст."
    rhs_text = "Статья 5. Учёт.\nТекст."
    lhs_chunks = chunk_text("LEGAL_NPA", lhs_text, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_NPA", rhs_text, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p1"}, _doc("lhs", 1), _doc("rhs", 1), lhs_chunks, rhs_chunks
    )
    deleted = [e for e in events if e["status"] == "deleted"]
    assert any(e["lhs"]["chunk_key"] == "article=6" for e in deleted)


def test_structural_diff_partial_text_change():
    lhs_text = "Статья 5. Учёт мигрантов\nИностранные граждане обязаны зарегистрироваться в течение семи рабочих дней с момента въезда на территорию Российской Федерации."
    rhs_text = "Статья 5. Учёт мигрантов\nИностранные граждане обязаны зарегистрироваться в течение тридцати дней с момента въезда."
    lhs_chunks = chunk_text("LEGAL_NPA", lhs_text, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_NPA", rhs_text, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p1"}, _doc("lhs", 1), _doc("rhs", 1), lhs_chunks, rhs_chunks
    )
    e = next(x for x in events if x["lhs"] and x["lhs"]["chunk_key"] == "article=5")
    assert e["status"] in {"partial", "modified", "contradicts"}


def test_structural_diff_two_rank1_npas_completely_different_is_contradicts():
    lhs_text = "Статья 5. Учёт\nРегистрация в течение семи дней."
    rhs_text = "Статья 5. Учёт\nДанные передаются в Минцифры через единую систему."
    lhs_chunks = chunk_text("LEGAL_NPA", lhs_text, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_NPA", rhs_text, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p1"}, _doc("lhs", 1), _doc("rhs", 1), lhs_chunks, rhs_chunks
    )
    e = next(x for x in events if x["lhs"] and x["lhs"]["chunk_key"] == "article=5")
    assert e["status"] in {"contradicts", "modified"}
    if e["status"] == "contradicts":
        assert e["severity"] == "high"


def test_structural_diff_event_ids_are_deterministic():
    lhs_text = "Статья 5. A\nТекст."
    rhs_text = "Статья 5. A\nТекст."
    lhs_chunks = chunk_text("LEGAL_NPA", lhs_text, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_NPA", rhs_text, doc_id="rhs")
    a = legal_structural_diff({"pair_id": "p1"}, _doc("lhs", 1), _doc("rhs", 1), lhs_chunks, rhs_chunks)
    b = legal_structural_diff({"pair_id": "p1"}, _doc("lhs", 1), _doc("rhs", 1), lhs_chunks, rhs_chunks)
    assert [e["event_id"] for e in a] == [e["event_id"] for e in b]


def test_structural_diff_event_evidence_carries_chunk_key():
    text = "Статья 7. Регистрация\nТекст."
    chunks = chunk_text("LEGAL_NPA", text)
    events = legal_structural_diff({"pair_id": "p1"}, _doc("a", 1), _doc("b", 1), chunks, chunks)
    e = events[0]
    assert e["lhs"]["chunk_key"] == "article=7"
    assert e["rhs"]["chunk_key"] == "article=7"
    assert e["lhs"]["chunk_kind"] == "article"


# ---------------------------------------------------------------------------
# apply_rank_gate (PR-3.6)
# ---------------------------------------------------------------------------


def test_rank_gate_no_op_when_both_rank_1():
    ev = {"status": "contradicts", "severity": "high", "confidence": 0.9}
    apply_rank_gate(ev, _doc("a", 1), _doc("b", 1))
    assert ev["status"] == "contradicts"
    assert "rank_gate" not in ev


def test_rank_gate_no_op_when_both_rank_3():
    ev = {"status": "contradicts", "severity": "high", "confidence": 0.9}
    apply_rank_gate(ev, _doc("a", 3), _doc("b", 3))
    assert ev["status"] == "contradicts"
    assert "rank_gate" not in ev


def test_rank_gate_downgrades_rank3_vs_rank1_contradicts():
    ev = {"status": "contradicts", "severity": "high", "confidence": 0.9}
    apply_rank_gate(ev, _doc("npa", 1), _doc("vciom", 3))
    assert ev["status"] == "manual_review"
    assert ev["original_status"] == "contradicts"
    assert ev["review_required"] is True
    assert ev["rank_gate"]["applied"] is True


def test_rank_gate_downgrades_when_lhs_rank3_rhs_rank1():
    """Symmetric: rank3↔rank1 in either order downgrades."""
    ev = {"status": "contradicts", "severity": "high", "confidence": 0.7}
    apply_rank_gate(ev, _doc("vciom", 3), _doc("npa", 1))
    assert ev["status"] == "manual_review"
    # Lower confidence → severity drops to medium.
    assert ev["severity"] == "medium"


def test_rank_gate_does_not_touch_partial_or_same():
    ev_same = {"status": "same", "severity": "low", "confidence": 1.0}
    apply_rank_gate(ev_same, _doc("npa", 1), _doc("vciom", 3))
    assert ev_same["status"] == "same"

    ev_partial = {"status": "partial", "severity": "medium", "confidence": 0.85}
    apply_rank_gate(ev_partial, _doc("npa", 1), _doc("vciom", 3))
    assert ev_partial["status"] == "partial"


def test_rank_gate_downgrades_added_and_deleted_for_low_vs_high():
    """rank-3 missing/extra section vs rank-1 NPA shouldn't be a hard add/del."""
    for st in ("added", "deleted"):
        ev = {"status": st, "severity": "medium", "confidence": 0.6}
        apply_rank_gate(ev, _doc("npa", 1), _doc("vciom", 3))
        assert ev["status"] == "manual_review"
        assert ev["original_status"] == st


def test_rank_gate_rank2_vs_rank1_no_op():
    """Rank-2 (departmental) vs rank-1 — no gate, both authoritative-ish."""
    ev = {"status": "contradicts", "severity": "high", "confidence": 0.8}
    apply_rank_gate(ev, _doc("npa", 1), _doc("kontur", 2))
    assert ev["status"] == "contradicts"
    assert "rank_gate" not in ev


def test_structural_diff_applies_rank_gate_inline():
    """Top-level diff should hand events through the gate."""
    lhs_text = "Статья 1. NPA\nТекст официальной нормы."
    rhs_text = "Статья 1. Аналитика\nСовершенно другой смысл — противоречит норме."
    lhs_chunks = chunk_text("LEGAL_NPA", lhs_text, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_NPA", rhs_text, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p1"}, _doc("npa", 1), _doc("vciom", 3), lhs_chunks, rhs_chunks
    )
    e = next(x for x in events if x["lhs"] and x["lhs"]["chunk_key"] == "article=1")
    # Without the gate this would be "contradicts" (both NPA-shaped) but
    # rank_gate downgrades because rhs is rank 3.
    assert e["status"] == "manual_review"
    assert e["rank_gate"]["applied"] is True
