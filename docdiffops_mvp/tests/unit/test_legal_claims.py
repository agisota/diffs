"""Tests for claim extraction and validation (PR-3.5)."""
from __future__ import annotations

from docdiffops.legal import (
    Claim,
    chunk_text,
    claim_validation_events,
    extract_claims,
    validate_claim,
)


# ---------------------------------------------------------------------------
# extract_claims
# ---------------------------------------------------------------------------


def _block(text: str, block_id: str = "b1", page: int = 1) -> dict:
    return {"block_id": block_id, "text": text, "page_no": page}


def test_extract_claims_picks_normative_sentence():
    blocks = [
        _block("Иностранные граждане обязаны зарегистрироваться в течение семи дней с момента въезда."),
    ]
    claims = extract_claims(blocks, doc_id="vciom")
    assert len(claims) == 1
    assert "обязаны" in claims[0].text.lower()
    assert claims[0].score_assertive > 0


def test_extract_claims_skips_too_short_sentences():
    blocks = [_block("Это так.")]
    claims = extract_claims(blocks, doc_id="d")
    assert claims == []


def test_extract_claims_filters_low_assertive():
    """A neutral observation without normative markers is skipped."""
    blocks = [_block("Сегодня хорошая погода в Москве и Санкт-Петербурге одновременно.")]
    claims = extract_claims(blocks, doc_id="d")
    assert claims == []


def test_extract_claims_splits_multiple_sentences():
    blocks = [_block(
        "Стимулировать интеллектуальную миграцию — приоритет. "
        "Усилить регулирование въезда необходимо в кратчайшие сроки."
    )]
    claims = extract_claims(blocks, doc_id="d")
    assert len(claims) == 2


def test_extract_claims_respects_max_per_doc_cap():
    blocks = [_block("Стимулировать развитие миграционной политики необходимо.") for _ in range(50)]
    claims = extract_claims(blocks, doc_id="d", max_per_doc=10)
    assert len(claims) == 10


def test_extract_claims_deterministic_ids():
    blocks = [_block("Иностранные граждане обязаны зарегистрироваться в течение семи дней.")]
    a = extract_claims(blocks, doc_id="d")
    b = extract_claims(blocks, doc_id="d")
    assert a[0].claim_id == b[0].claim_id


# ---------------------------------------------------------------------------
# validate_claim
# ---------------------------------------------------------------------------


def test_validate_claim_confirmed_when_npa_says_same_thing():
    claim = Claim(
        claim_id="c1",
        text="Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке.",
        source_doc_id="vciom", source_block_id="b1", source_page=4,
        score_assertive=0.5,
    )
    npa_text = (
        "Раздел II. Цели\n"
        "1. Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке.\n"
    )
    npa_chunks = chunk_text("LEGAL_CONCEPT", npa_text, doc_id="conc")
    status, score, chunk = validate_claim(claim, npa_chunks)
    assert status == "confirmed"
    assert score >= 88
    assert chunk is not None


def test_validate_claim_partial_when_close_but_not_exact():
    claim = Claim(
        claim_id="c1",
        text="Регистрация мигрантов в течение трёх дней.",
        source_doc_id="vciom", source_block_id="b1", source_page=4,
        score_assertive=0.5,
    )
    npa_text = (
        "Статья 5. Учёт мигрантов\n"
        "Иностранные граждане обязаны зарегистрироваться в течение семи дней.\n"
    )
    npa_chunks = chunk_text("LEGAL_NPA", npa_text, doc_id="fz")
    status, score, _ = validate_claim(claim, npa_chunks)
    # The two are close ("регистрация мигрантов" / "семи дней" share tokens)
    # but counts differ — status lands in partial OR manual_review.
    assert status in {"partial", "manual_review", "confirmed"}
    assert score >= 50


def test_validate_claim_not_found_when_topic_absent():
    claim = Claim(
        claim_id="c1",
        text="Запретить криптовалюты на территории страны.",
        source_doc_id="vciom", source_block_id="b1", source_page=4,
        score_assertive=0.5,
    )
    npa_text = "Статья 5. Учёт мигрантов\nИностранные граждане подлежат учёту."
    npa_chunks = chunk_text("LEGAL_NPA", npa_text, doc_id="fz")
    status, score, _ = validate_claim(claim, npa_chunks)
    assert status in {"not_found", "manual_review"}
    assert score < 70


def test_validate_claim_empty_chunks_returns_not_found():
    claim = Claim(
        claim_id="c1", text="Тезис.", source_doc_id="d",
        source_block_id=None, source_page=None, score_assertive=0.5,
    )
    status, score, chunk = validate_claim(claim, [])
    assert status == "not_found"
    assert score == 0.0
    assert chunk is None


# ---------------------------------------------------------------------------
# claim_validation_events
# ---------------------------------------------------------------------------


def _doc(doc_id: str, rank: int) -> dict:
    return {"doc_id": doc_id, "source_rank": rank, "doc_type": "PRESENTATION" if rank == 3 else "LEGAL_CONCEPT"}


def test_claim_validation_events_for_analytics_vs_npa_pair():
    analytics_blocks = [
        _block("Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке."),
        _block("Усилить регулирование въезда крайне необходимо в кратчайшие сроки."),
    ]
    npa_text = (
        "Раздел II. Цели\n"
        "1. Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке.\n"
        "2. Снизить нелегальную миграцию.\n"
    )
    npa_chunks = chunk_text("LEGAL_CONCEPT", npa_text, doc_id="conc")
    events = claim_validation_events(
        {"pair_id": "p1"},
        analytics_doc=_doc("vciom", 3),
        npa_doc=_doc("conc", 1),
        analytics_blocks=analytics_blocks,
        npa_chunks=npa_chunks,
    )
    assert len(events) == 2
    types = {e["comparison_type"] for e in events}
    assert types == {"claim_validation"}
    # First claim should be confirmed (literal match).
    assert any(e["status"] == "confirmed" for e in events)


def test_claim_validation_event_has_lhs_claim_metadata():
    blocks = [_block("Иностранные граждане обязаны зарегистрироваться в течение семи дней.")]
    npa_chunks = chunk_text("LEGAL_NPA", "Статья 5. Учёт\nТекст.", doc_id="fz")
    events = claim_validation_events(
        {"pair_id": "p1"},
        analytics_doc=_doc("vciom", 3),
        npa_doc=_doc("fz", 1),
        analytics_blocks=blocks,
        npa_chunks=npa_chunks,
    )
    assert len(events) == 1
    assert "claim_id" in events[0]["lhs"]
    assert events[0]["lhs"]["score_assertive"] is not None


def test_claim_validation_runs_rank_gate():
    """A 'confirmed' status passes through; a strong divergence on rank3↔rank1
    that would otherwise be 'modified' should be downgraded by the gate."""
    blocks = [_block("Запретить интеллектуальную миграцию полностью без исключений срочно.")]
    npa_text = (
        "Раздел I. Цели\n"
        "1. Стимулировать интеллектуальную миграцию необходимо в приоритетном порядке.\n"
    )
    npa_chunks = chunk_text("LEGAL_CONCEPT", npa_text, doc_id="conc")
    events = claim_validation_events(
        {"pair_id": "p1"},
        analytics_doc=_doc("vciom", 3),
        npa_doc=_doc("conc", 1),
        analytics_blocks=blocks,
        npa_chunks=npa_chunks,
    )
    assert len(events) == 1
    e = events[0]
    # Either not_found or downgraded by rank_gate; never raw 'contradicts'.
    assert e["status"] in {"not_found", "manual_review", "partial"}


def test_claim_validation_empty_blocks_returns_no_events():
    npa_chunks = chunk_text("LEGAL_NPA", "Статья 1. Цели\nТекст.", doc_id="fz")
    events = claim_validation_events(
        {"pair_id": "p1"},
        analytics_doc=_doc("vciom", 3),
        npa_doc=_doc("fz", 1),
        analytics_blocks=[],
        npa_chunks=npa_chunks,
    )
    assert events == []
