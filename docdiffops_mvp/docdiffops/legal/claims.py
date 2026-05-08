"""Claim extraction + validation (PR-3.5).

Extracts assertive/normative claims from analytics docs (presentations,
expert summaries, blog posts) and validates each against the structural
chunks of rank-1 NPAs. Each validated claim becomes a diff event with
``comparison_type='claim_validation'``.

This is the ВЦИОМ → Концепция flow from the brief: take a tezis like
"стимулирование интеллектуальной миграции" and check whether the rank-1
Concept actually says that, says something close, contradicts it, or
doesn't mention it at all.

Heuristics-only — no LLM. Sprint 5 PR-5.5 adds the semantic comparator
on top; this layer is the deterministic baseline.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

try:
    from rapidfuzz import fuzz as _fuzz

    def _similarity(a: str, b: str) -> float:
        return float(_fuzz.token_set_ratio(a or "", b or ""))
except Exception:  # pragma: no cover
    import difflib

    def _similarity(a: str, b: str) -> float:
        return 100.0 * difflib.SequenceMatcher(None, a or "", b or "").ratio()


from .chunker import Chunk
from .rank_gate import apply_rank_gate

# ---------------------------------------------------------------------------
# Extraction heuristics
# ---------------------------------------------------------------------------

# Russian normative / assertive markers. A sentence/phrase that contains
# any of these is more likely to be a "claim" than a passing observation.
_CLAIM_MARKERS = (
    "должен", "должна", "должно", "должны",
    "обязан", "обязана", "обязано", "обязаны",
    "необходим", "требует", "требуется",
    "стимулирован", "усилен", "развит", "ввести",
    "повыс", "снизит", "сократит", "увеличит",
    "запрет", "разрешен", "разрешён",
    "регулирует", "устанавливает", "предусматрив",
    "цель", "приоритет", "направлен",
)

# "More-than-trivial" sentence: at least N words and not a date/number-only.
_MIN_WORDS = 4
_MAX_WORDS = 60


@dataclass
class Claim:
    """A normative/assertive statement extracted from an analytics doc."""

    claim_id: str
    text: str
    source_doc_id: str
    source_block_id: str | None
    source_page: int | None
    score_assertive: float  # 0..1, higher = stronger normative tone

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "source_doc_id": self.source_doc_id,
            "source_block_id": self.source_block_id,
            "source_page": self.source_page,
            "score_assertive": self.score_assertive,
        }


def _split_sentences(text: str) -> list[str]:
    """Cheap RU-aware sentence splitter — preserves Cyrillic ё/Ё."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?…])\s+(?=[А-ЯЁA-Z])", text.strip())
    out = []
    for p in parts:
        p = p.strip(" \t\n\r—–-•·")
        if p:
            out.append(p)
    return out


def _assertive_score(text: str) -> float:
    """Return 0..1 score: density of normative markers + structural cues.

    Cues:
    - Markers from ``_CLAIM_MARKERS`` (each adds 0.15)
    - Verb-first or imperative shape (sentence starts with marker)
    - Bullet-like prefixes ('— ', '• ') already stripped by caller
    """
    if not text:
        return 0.0
    low = text.lower()
    n_markers = sum(1 for m in _CLAIM_MARKERS if m in low)
    score = min(1.0, 0.15 * n_markers)
    if any(low.startswith(m) for m in _CLAIM_MARKERS):
        score = min(1.0, score + 0.2)
    return round(score, 3)


def _claim_id(doc_id: str, block_id: str | None, text: str) -> str:
    h = hashlib.sha256(f"{doc_id}|{block_id or ''}|{text}".encode("utf-8")).hexdigest()
    return "clm_" + h[:14]


def extract_claims(
    blocks: list[dict[str, Any]],
    doc_id: str,
    *,
    min_score: float = 0.15,
    max_per_doc: int = 200,
) -> list[Claim]:
    """Walk extracted blocks, split each into sentences, return claim list.

    Filters out short/numeric-only sentences and below-threshold assertions.
    Caps total claims per doc to keep claim_validation O(N) bounded.
    """
    claims: list[Claim] = []
    for b in blocks or []:
        text = (b.get("text") or "").strip()
        if not text:
            continue
        for sent in _split_sentences(text):
            words = sent.split()
            if len(words) < _MIN_WORDS or len(words) > _MAX_WORDS:
                continue
            if sent[:6].strip().isdigit():
                continue  # skip "1. " bullets where number leaked
            sc = _assertive_score(sent)
            if sc < min_score:
                continue
            claims.append(Claim(
                claim_id=_claim_id(doc_id, b.get("block_id"), sent),
                text=sent,
                source_doc_id=doc_id,
                source_block_id=b.get("block_id"),
                source_page=b.get("page_no"),
                score_assertive=sc,
            ))
            if len(claims) >= max_per_doc:
                return claims
    return claims


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _classify_match(score: float) -> tuple[str, str]:
    """Map similarity → (status, severity) for claim_validation events."""
    if score >= 88:
        return "confirmed", "low"
    if score >= 70:
        return "partial", "medium"
    if score >= 50:
        return "manual_review", "medium"
    return "not_found", "medium"


def validate_claim(
    claim: Claim,
    npa_chunks: list[Chunk],
    *,
    top_k: int = 1,
) -> tuple[str, float, Chunk | None]:
    """Find best-matching NPA chunk for ``claim`` and classify."""
    if not npa_chunks:
        return "not_found", 0.0, None
    best_chunk: Chunk | None = None
    best_score = 0.0
    target = _norm(claim.text)
    for ch in npa_chunks:
        body = _norm((ch.title or "") + " " + (ch.text or ""))
        if not body:
            continue
        s = _similarity(target, body)
        if s > best_score:
            best_score = s
            best_chunk = ch
    status, _ = _classify_match(best_score)
    return status, best_score, best_chunk


def claim_validation_events(
    pair: dict[str, Any],
    analytics_doc: dict[str, Any],
    npa_doc: dict[str, Any],
    analytics_blocks: list[dict[str, Any]],
    npa_chunks: list[Chunk],
) -> list[dict[str, Any]]:
    """Run extract → validate → emit events for one analytics ↔ NPA pair.

    The analytics doc is rank-3, the NPA is rank-1. Status is shaped by
    apply_rank_gate so 'contradicts' / 'modified' / 'added' downgrade to
    manual_review automatically.
    """
    claims = extract_claims(analytics_blocks, analytics_doc.get("doc_id") or "?")
    pair_id = pair.get("pair_id") or "?"
    out: list[dict[str, Any]] = []
    for claim in claims:
        status, score, chunk = validate_claim(claim, npa_chunks)
        _, severity = _classify_match(score)
        ev = {
            "event_id": "evt_" + hashlib.sha256(f"{pair_id}|{claim.claim_id}".encode()).hexdigest()[:18],
            "pair_id": pair_id,
            "comparison_type": "claim_validation",
            "status": status,
            "severity": severity,
            "score": round(score, 1),
            "confidence": round(min(1.0, score / 100.0), 3),
            "review_required": status in {"manual_review", "not_found"},
            "lhs_doc_id": analytics_doc.get("doc_id"),
            "rhs_doc_id": npa_doc.get("doc_id"),
            "lhs": {
                "doc_id": analytics_doc.get("doc_id"),
                "page_no": claim.source_page,
                "block_id": claim.source_block_id,
                "claim_id": claim.claim_id,
                "score_assertive": claim.score_assertive,
                "bbox": None,
                "quote": claim.text,
            },
            "rhs": _chunk_evidence(chunk, npa_doc) if chunk else None,
            "explanation_short": _explain(status, claim, chunk, score),
        }
        out.append(apply_rank_gate(ev, analytics_doc, npa_doc))
    return out


def _chunk_evidence(chunk: Chunk, doc: dict[str, Any]) -> dict[str, Any]:
    quote = ((chunk.title or "") + " — " + (chunk.text or "")).strip(" —")
    if len(quote) > 600:
        quote = quote[:597] + "…"
    return {
        "doc_id": doc.get("doc_id"),
        "page_no": None,
        "block_id": chunk.chunk_id,
        "chunk_kind": chunk.kind,
        "chunk_number": chunk.number,
        "bbox": None,
        "quote": quote,
    }


def _explain(status: str, claim: Claim, chunk: Chunk | None, score: float) -> str:
    if status == "confirmed":
        loc = f"{chunk.kind} {chunk.number}" if chunk else "норме"
        return f"Тезис подтверждается ({loc}, sim={score:.0f}/100)."
    if status == "partial":
        loc = f"{chunk.kind} {chunk.number}" if chunk else "норма"
        return f"Тезис частично подтверждается ({loc}, sim={score:.0f}/100)."
    if status == "manual_review":
        return f"Тезис требует ручной проверки — слабое совпадение ({score:.0f}/100)."
    if status == "not_found":
        return "Тезис не найден в нормативных документах ранга 1."
    return ""
