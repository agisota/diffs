"""Pair-level similarity score (PR-5.9).

Reduces an event list to a single 0-100 score: how similar are LHS
and RHS overall. 100 means perfect match, 0 means no semantic overlap.

Used by:
- evidence_matrix ``02_pair_matrix`` sheet (new ``score`` column)
- SPA pair card (badge with the number)
- pair sorting in the executive summary

Heuristic (deterministic, no LLM):
    score = 100 - sum(weight_per_event) / max_possible
where weight per event depends on status × severity:
    same        →   0
    partial     →  high:8 medium:4 low:2
    modified    →  high:10 medium:6 low:3
    contradicts →  high:14 medium:8 low:4
    added/del   →  high:6 medium:3 low:1
    manual_review/not_found → high:5 medium:3 low:1
Capped at 100 events worth of weight; floor at 0.
"""
from __future__ import annotations

from typing import Any


_WEIGHT = {
    "same":          {"low": 0,  "medium": 0,  "high": 0},
    "partial":       {"low": 2,  "medium": 4,  "high": 8},
    "modified":      {"low": 3,  "medium": 6,  "high": 10},
    "contradicts":   {"low": 4,  "medium": 8,  "high": 14},
    "added":         {"low": 1,  "medium": 3,  "high": 6},
    "deleted":       {"low": 1,  "medium": 3,  "high": 6},
    "manual_review": {"low": 1,  "medium": 3,  "high": 5},
    "not_found":     {"low": 1,  "medium": 3,  "high": 5},
}

_MAX_WEIGHT_PER_PAIR = 100  # caps deduction at 100 points


def pair_similarity_score(events: list[dict[str, Any]]) -> int:
    """Return integer score 0..100 for a pair from its events.

    Empty events list → 100 (no diff = perfect match). Unknown
    statuses/severities default to a small medium weight so they
    contribute something rather than vanishing.
    """
    if not events:
        return 100
    total = 0
    for e in events:
        status = (e.get("status") or "").lower()
        sev = (e.get("severity") or "low").lower()
        bucket = _WEIGHT.get(status)
        if bucket is None:
            total += 2  # mild penalty for unrecognized status
            continue
        total += bucket.get(sev, bucket.get("medium", 2))
    deduction = min(_MAX_WEIGHT_PER_PAIR, total)
    return max(0, 100 - deduction)


def score_band(score: int) -> str:
    """Coarse label for UI badges."""
    if score >= 90:
        return "near-identical"
    if score >= 70:
        return "minor"
    if score >= 50:
        return "moderate"
    if score >= 30:
        return "major"
    return "divergent"


__all__ = ["pair_similarity_score", "score_band"]
