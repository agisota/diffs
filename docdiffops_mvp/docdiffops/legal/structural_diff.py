"""Structural diff for chunked legal/policy documents (PR-3.3).

Aligns LHS and RHS chunk lists by their hierarchical key (e.g.
``article=5/part=2``) instead of by sequential block order, so a doc
that's been re-organized doesn't produce a wall of false-positive
'added/deleted' events. Falls back to the existing fuzzy block diff
when chunks lack a stable structural key.

Status assignment:
- both sides have the same key:
    similarity ≥ 92  → same
    78 ≤ similarity < 92 → partial
    similarity < 78  → modified  (or contradicts when rank-1 vs rank-1)
- LHS only → deleted
- RHS only → added

Each event carries ``comparison_type='legal_structural_diff'`` and the
structural key inside ``lhs.chunk_key`` / ``rhs.chunk_key`` so the
evidence matrix and the reviewer UI can collapse rows by anchor.
"""
from __future__ import annotations

import hashlib
from typing import Any

try:
    from rapidfuzz import fuzz as _fuzz

    def _similarity(a: str, b: str) -> float:
        return float(_fuzz.token_set_ratio(a or "", b or ""))
except Exception:  # pragma: no cover — rapidfuzz is in requirements
    import difflib

    def _similarity(a: str, b: str) -> float:
        return 100.0 * difflib.SequenceMatcher(None, a or "", b or "").ratio()


from .chunker import Chunk
from .rank_gate import apply_rank_gate


def _chunk_key(c: Chunk) -> str | None:
    """Build a doc-agnostic structural key from a Chunk's hierarchy."""
    parts: list[str] = []
    if c.kind == "article" and c.number:
        parts.append(f"article={c.number}")
    elif c.kind == "section" and c.number:
        parts.append(f"section={c.number}")
    elif c.kind == "chapter" and c.number:
        parts.append(f"chapter={c.number}")
    elif c.kind == "part" and c.number:
        parts.append(f"part={c.number}")
    elif c.kind == "point" and c.number:
        parts.append(f"point={c.number}")
    elif c.kind == "subpoint" and c.number:
        parts.append(f"subpoint={c.number}")
    elif c.kind == "measure" and c.number:
        parts.append(f"measure={c.number}")
    return "/".join(parts) or None


def _index_by_key(chunks: list[Chunk]) -> dict[str, list[Chunk]]:
    out: dict[str, list[Chunk]] = {}
    for c in chunks:
        k = _chunk_key(c)
        if k is None:
            continue
        out.setdefault(k, []).append(c)
    return out


def _event_id(pair_id: str, scope: str) -> str:
    return "evt_" + hashlib.sha256(f"{pair_id}|{scope}".encode("utf-8")).hexdigest()[:18]


def _event_for(
    pair: dict[str, Any],
    lhs_doc: dict[str, Any],
    rhs_doc: dict[str, Any],
    lhs_chunk: Chunk | None,
    rhs_chunk: Chunk | None,
    status: str,
    score: float,
    severity: str,
) -> dict[str, Any]:
    pair_id = pair.get("pair_id") or "?"
    key_for_id = (lhs_chunk and _chunk_key(lhs_chunk)) or (rhs_chunk and _chunk_key(rhs_chunk)) or "?"
    return {
        "event_id": _event_id(pair_id, key_for_id),
        "pair_id": pair_id,
        "comparison_type": "legal_structural_diff",
        "status": status,
        "severity": severity,
        "score": round(score, 1),
        "confidence": round(min(1.0, score / 100.0), 3),
        "review_required": severity in {"high", "medium"} and status != "same",
        "lhs_doc_id": lhs_doc.get("doc_id"),
        "rhs_doc_id": rhs_doc.get("doc_id"),
        "lhs": _evidence(lhs_chunk, lhs_doc) if lhs_chunk else None,
        "rhs": _evidence(rhs_chunk, rhs_doc) if rhs_chunk else None,
        "explanation_short": _explain(status, lhs_chunk, rhs_chunk, score),
    }


def _evidence(c: Chunk, doc: dict[str, Any]) -> dict[str, Any]:
    quote = (c.title + " — " + c.text).strip(" —") if c.title else c.text
    if len(quote) > 600:
        quote = quote[:597] + "…"
    return {
        "doc_id": doc.get("doc_id"),
        "page_no": None,
        "block_id": c.chunk_id,
        "chunk_kind": c.kind,
        "chunk_key": _chunk_key(c),
        "chunk_number": c.number,
        "bbox": None,
        "quote": quote,
    }


def _explain(status: str, lhs: Chunk | None, rhs: Chunk | None, score: float) -> str:
    if status == "same":
        return f"Структурный совпадает ({score:.0f}/100)."
    if status == "partial":
        return f"Структурно та же норма, текст частично изменён ({score:.0f}/100)."
    if status == "modified":
        return f"Структурный анкор тот же, текст существенно изменён ({score:.0f}/100)."
    if status == "contradicts":
        return f"Структурно совпадает, формулировки противоречат ({score:.0f}/100)."
    if status == "added":
        kind = (rhs.kind if rhs else "?")
        num = (rhs.number if rhs else "?")
        return f"Добавлен новый структурный блок {kind} {num} в RHS."
    if status == "deleted":
        kind = (lhs.kind if lhs else "?")
        num = (lhs.number if lhs else "?")
        return f"Удалён структурный блок {kind} {num} из RHS."
    return ""


def _classify(score: float, both_npa: bool) -> tuple[str, str]:
    """Map similarity score → (status, severity)."""
    if score >= 92:
        return "same", "low"
    if score >= 78:
        return "partial", "medium"
    if both_npa:
        # Two official NPAs at the same anchor with very different text
        # is genuinely a contradiction worth flagging.
        return "contradicts", "high"
    return "modified", "medium"


def legal_structural_diff(
    pair: dict[str, Any],
    lhs_doc: dict[str, Any],
    rhs_doc: dict[str, Any],
    lhs_chunks: list[Chunk],
    rhs_chunks: list[Chunk],
) -> list[dict[str, Any]]:
    """Return diff events for a pair using structural alignment.

    Events go through the source-rank gate before being returned, so
    rank-3 ↔ rank-1 'contradicts' get downgraded to manual_review per
    PR-3.6 rules.
    """
    lhs_idx = _index_by_key(lhs_chunks)
    rhs_idx = _index_by_key(rhs_chunks)

    keys = sorted(set(lhs_idx) | set(rhs_idx))
    both_npa = (
        int(lhs_doc.get("source_rank") or 3) == 1
        and int(rhs_doc.get("source_rank") or 3) == 1
    )

    events: list[dict[str, Any]] = []
    for k in keys:
        lhs_list = lhs_idx.get(k, [])
        rhs_list = rhs_idx.get(k, [])
        if lhs_list and rhs_list:
            # Use the first chunk on each side (typical case: 1 article == 1 chunk).
            l = lhs_list[0]
            r = rhs_list[0]
            score = _similarity(_normalize(l), _normalize(r))
            status, severity = _classify(score, both_npa)
            ev = _event_for(pair, lhs_doc, rhs_doc, l, r, status, score, severity)
        elif lhs_list:
            l = lhs_list[0]
            ev = _event_for(pair, lhs_doc, rhs_doc, l, None, "deleted", 0.0, "medium")
        else:
            r = rhs_list[0]
            ev = _event_for(pair, lhs_doc, rhs_doc, None, r, "added", 0.0, "medium")

        ev = apply_rank_gate(ev, lhs_doc, rhs_doc)
        events.append(ev)

    return events


def _normalize(c: Chunk) -> str:
    """Lower-case, collapse whitespace; combine title + text for sim score."""
    s = ((c.title or "") + " " + (c.text or "")).lower()
    return " ".join(s.split())
