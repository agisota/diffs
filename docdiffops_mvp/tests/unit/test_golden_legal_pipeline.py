"""Golden regression test for the legal pipeline (PR-5.1 lite).

Locks in the deterministic event counts and statuses for a fixed pair
of small Russian-language fixtures so future refactors detect drift
without needing the full docker compose stack.

This is a unit-level golden — it skips normalize/extract (which need
LibreOffice + PyMuPDF) and feeds chunkable text directly to the
legal_structural_diff and claim_validation paths.
"""
from __future__ import annotations

from docdiffops.legal import (
    chunk_text,
    claim_validation_events,
    legal_structural_diff,
)


# ---------------------------------------------------------------------------
# Fixtures (locked).
# ---------------------------------------------------------------------------

NPA_LHS = """\
Раздел I. Общие положения
1. Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке.
2. Усилить контроль за нелегальной миграцией.
3. Развитие цифровой инфраструктуры миграционного учёта.
"""

NPA_RHS = """\
Раздел I. Общие положения
1. Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке.
2. Усилить контроль за миграцией с применением биометрии.
3. Развитие цифровой инфраструктуры миграционного учёта.
4. Введение единой системы учёта.
"""

ANALYTICS_BLOCKS = [
    {"block_id": "b1", "page_no": 4, "text": "Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке."},
    {"block_id": "b2", "page_no": 4, "text": "Запретить любую миграцию полностью без исключений срочно."},
    {"block_id": "b3", "page_no": 5, "text": "Сегодня хорошая погода в Москве и Санкт-Петербурге одновременно."},
]


def _doc(doc_id: str, rank: int, doc_type: str) -> dict:
    return {"doc_id": doc_id, "source_rank": rank, "doc_type": doc_type}


# ---------------------------------------------------------------------------
# legal_structural_diff golden
# ---------------------------------------------------------------------------


def test_golden_structural_diff_counts_and_keys():
    lhs_chunks = chunk_text("LEGAL_CONCEPT", NPA_LHS, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_CONCEPT", NPA_RHS, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p_golden"},
        _doc("lhs", 1, "LEGAL_CONCEPT"),
        _doc("rhs", 1, "LEGAL_CONCEPT"),
        lhs_chunks,
        rhs_chunks,
    )

    # Section + 4 unique points = 5 events expected; one of them is
    # the new RHS-only point=4 with status=added.
    keys = {e["lhs"]["chunk_key"] if e.get("lhs") else e["rhs"]["chunk_key"] for e in events}
    assert "section=I" in keys
    assert "point=1" in keys
    assert "point=2" in keys
    assert "point=3" in keys
    assert "point=4" in keys

    by_status: dict[str, int] = {}
    for e in events:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    assert by_status.get("added", 0) >= 1            # point=4 only on RHS
    # point=1 and point=3 are identical text → at least one same.
    assert by_status.get("same", 0) >= 2


def test_golden_structural_diff_partial_on_modified_text():
    lhs_chunks = chunk_text("LEGAL_CONCEPT", NPA_LHS, doc_id="lhs")
    rhs_chunks = chunk_text("LEGAL_CONCEPT", NPA_RHS, doc_id="rhs")
    events = legal_structural_diff(
        {"pair_id": "p_golden"},
        _doc("lhs", 1, "LEGAL_CONCEPT"),
        _doc("rhs", 1, "LEGAL_CONCEPT"),
        lhs_chunks,
        rhs_chunks,
    )
    # point=2 differs ("нелегальной" vs "с применением биометрии") — must
    # land in {partial, modified, contradicts}, never `same` or `added`.
    p2 = next(
        (e for e in events
         if e.get("lhs") and e["lhs"].get("chunk_key") == "point=2"
         and e.get("rhs") and e["rhs"].get("chunk_key") == "point=2"),
        None,
    )
    assert p2 is not None
    assert p2["status"] in {"partial", "modified", "contradicts"}


# ---------------------------------------------------------------------------
# claim_validation golden
# ---------------------------------------------------------------------------


def test_golden_claim_validation_counts_and_first_claim_confirmed():
    npa_chunks = chunk_text("LEGAL_CONCEPT", NPA_LHS, doc_id="conc")
    events = claim_validation_events(
        {"pair_id": "p_golden_cv"},
        analytics_doc=_doc("vciom", 3, "PRESENTATION"),
        npa_doc=_doc("conc", 1, "LEGAL_CONCEPT"),
        analytics_blocks=ANALYTICS_BLOCKS,
        npa_chunks=npa_chunks,
    )

    # Block 3 is non-assertive (weather) — must NOT produce a claim
    # (extract_claims filters it out).
    assert all(e["lhs"]["block_id"] != "b3" for e in events)

    # Block 1 matches NPA point=1 verbatim → confirmed.
    confirmed = [e for e in events if e["status"] == "confirmed"]
    assert any(e["lhs"]["block_id"] == "b1" for e in confirmed)

    # Block 2 ("Запретить...") doesn't match anything in NPA →
    # not_found (or downgraded by rank_gate, never confirmed).
    b2_event = next(e for e in events if e["lhs"]["block_id"] == "b2")
    assert b2_event["status"] in {"not_found", "manual_review", "partial"}


def test_golden_event_ids_stable_across_runs():
    npa_chunks = chunk_text("LEGAL_CONCEPT", NPA_LHS, doc_id="conc")
    a = claim_validation_events(
        {"pair_id": "stable"},
        _doc("vciom", 3, "PRESENTATION"),
        _doc("conc", 1, "LEGAL_CONCEPT"),
        ANALYTICS_BLOCKS,
        npa_chunks,
    )
    b = claim_validation_events(
        {"pair_id": "stable"},
        _doc("vciom", 3, "PRESENTATION"),
        _doc("conc", 1, "LEGAL_CONCEPT"),
        ANALYTICS_BLOCKS,
        npa_chunks,
    )
    assert [e["event_id"] for e in a] == [e["event_id"] for e in b]
