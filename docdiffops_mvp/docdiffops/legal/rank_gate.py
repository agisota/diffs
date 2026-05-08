"""Source-rank gate (PR-3.6).

Enforces the brief §13 rule: rank-3 sources (analytics, presentations,
blog posts) cannot REFUTE rank-1 sources (official NPAs). They can be:
not-confirmed, partially-confirmed, contradicting-as-thesis (which we
downgrade to manual_review), or simply not-comparable.

The gate runs AFTER the comparator emits raw events and BEFORE they're
written to the evidence matrix, so it shapes severity/status without
changing what the comparator sees.
"""
from __future__ import annotations

from typing import Any


# Status that a rank-3 vs rank-1 (or 1 vs 3) pair is NOT allowed to claim.
# When a comparator emits one of these, we downgrade per the rules below.
DISALLOWED_FOR_LOW_VS_HIGH = {"contradicts", "modified", "deleted", "added"}

# Mapping of (lhs_rank, rhs_rank, original_status) → (new_status, reason).
# Asymmetric: a rank-1 NPA can still flag a rank-3 analytic as
# "contradicts" (the analytic contradicts the NPA, that's fine to assert);
# but the reverse — analytic ↔ NPA flagged as "contradicts" — is downgraded.
# We collapse both directions to "manual_review" because the comparator
# doesn't know which side is the "claim".
_DOWNGRADE_REASON = (
    "rank-3 source cannot refute rank-1 NPA; downgraded for human review"
)


def apply_rank_gate(
    event: dict[str, Any],
    lhs_doc: dict[str, Any] | None,
    rhs_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the event with status/severity adjusted per rank rules.

    Mutation: the input ``event`` is modified in place AND returned for
    convenience. Adds ``rank_gate`` field with ``{applied: bool, reason}``
    so reviewers can see why a status changed. Severity is recomputed
    from the new status.

    Rules:
    - If neither side is rank-1 OR neither is rank-3 → no-op.
    - If a rank-3 doc is involved with a rank-1 NPA AND the original
      status is in DISALLOWED_FOR_LOW_VS_HIGH → downgrade to
      ``manual_review`` and require review.
    - If statuses are ``same`` or ``partial`` → no-op (those are valid
      regardless of rank).
    """
    if not event:
        return event
    lhs_rank = _rank_of(lhs_doc)
    rhs_rank = _rank_of(rhs_doc)

    # Only relevant when one side is rank-1 and the other rank-3.
    has_npa = 1 in (lhs_rank, rhs_rank)
    has_analytics = 3 in (lhs_rank, rhs_rank)
    if not (has_npa and has_analytics):
        return event

    status = (event.get("status") or "").lower()
    if status not in DISALLOWED_FOR_LOW_VS_HIGH:
        return event

    # Downgrade.
    event["original_status"] = status
    event["status"] = "manual_review"
    event["review_required"] = True
    event["severity"] = _severity_for_review(event)
    event["rank_gate"] = {
        "applied": True,
        "reason": _DOWNGRADE_REASON,
        "lhs_rank": lhs_rank,
        "rhs_rank": rhs_rank,
        "original_status": status,
    }
    return event


def _rank_of(doc: dict[str, Any] | None) -> int:
    if not doc:
        return 3
    try:
        return int(doc.get("source_rank") or 3)
    except (TypeError, ValueError):
        return 3


def _severity_for_review(event: dict[str, Any]) -> str:
    """Manual-review events need attention but aren't auto-failures.

    A high-confidence ex-contradicts event stays ``high`` so reviewers
    see it on top of the queue. Low-confidence ones drop to ``medium``.
    """
    conf = event.get("confidence")
    if isinstance(conf, (int, float)) and conf >= 0.8:
        return "high"
    return "medium"
