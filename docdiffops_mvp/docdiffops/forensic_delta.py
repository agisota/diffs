"""Forensic bundle delta comparison.

Compares two v8 forensic bundles and reports what changed: pair status
shifts, new/removed pairs, and distribution deltas.

Usage::

    from docdiffops.forensic_delta import compare_bundles
    delta = compare_bundles(old_bundle, new_bundle)
    # delta["status_changes"] — list of pairs whose v8_status shifted
    # delta["distribution_diff"] — e.g. {"match": +2, "contradiction": -1}
"""
from __future__ import annotations

import datetime
from collections import Counter
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUS_RANK: dict[str, int] = {
    "match": 6,
    "partial_overlap": 5,
    "outdated": 4,
    "manual_review": 3,
    "source_gap": 2,
    "contradiction": 1,
    "not_comparable": 0,
}

DIRECTION_IMPROVED  = "improved"
DIRECTION_DEGRADED  = "degraded"
DIRECTION_UNCHANGED = "unchanged"
DIRECTION_NEW       = "new"
DIRECTION_DROPPED   = "dropped"

ACTIONS_COVERAGE_SYMMETRIC = "symmetric"
ACTIONS_COVERAGE_OLD_ONLY  = "old_only"
ACTIONS_COVERAGE_NEW_ONLY  = "new_only"
ACTIONS_COVERAGE_NEITHER   = "neither"


def _direction(old_status: str, new_status: str) -> str:
    old_rank = STATUS_RANK.get(old_status, -1)
    new_rank = STATUS_RANK.get(new_status, -1)
    if new_rank > old_rank:
        return DIRECTION_IMPROVED
    if new_rank < old_rank:
        return DIRECTION_DEGRADED
    return DIRECTION_UNCHANGED


def _actions_coverage(old_bundle: Mapping[str, Any], new_bundle: Mapping[str, Any]) -> str:
    old_has = "actions_catalogue" in old_bundle
    new_has = "actions_catalogue" in new_bundle
    if old_has and new_has:
        return ACTIONS_COVERAGE_SYMMETRIC
    if old_has:
        return ACTIONS_COVERAGE_OLD_ONLY
    if new_has:
        return ACTIONS_COVERAGE_NEW_ONLY
    return ACTIONS_COVERAGE_NEITHER


def compare_bundles(
    old_bundle: Mapping[str, Any],
    new_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare two v8 forensic bundles and return a delta report.

    Both bundles must have ``schema_version`` starting with ``"v8."``.
    Raises ``ValueError`` if either bundle has an incompatible schema version.

    The returned dict has ``schema_version == "v8-delta"`` and is not itself
    a v8 bundle — it should not be passed to ``validate_bundle``.
    """
    for label, b in (("old", old_bundle), ("new", new_bundle)):
        sv = b.get("schema_version", "")
        if not str(sv).startswith("v8."):
            raise ValueError(
                f"compare_bundles: {label} bundle has incompatible schema_version={sv!r}; "
                "expected v8.x"
            )

    old_pairs: dict[str, dict[str, Any]] = {
        p["id"]: p for p in old_bundle.get("pairs", [])
    }
    new_pairs: dict[str, dict[str, Any]] = {
        p["id"]: p for p in new_bundle.get("pairs", [])
    }

    all_ids = set(old_pairs) | set(new_pairs)
    status_changes = []
    added_pairs = []
    removed_pairs = []

    for pid in sorted(all_ids):
        in_old = pid in old_pairs
        in_new = pid in new_pairs

        if in_old and in_new:
            old_st = old_pairs[pid].get("v8_status", "")
            new_st = new_pairs[pid].get("v8_status", "")
            if old_st != new_st:
                status_changes.append({
                    "pair_id": pid,
                    "left_id":    new_pairs[pid].get("left", ""),
                    "right_id":   new_pairs[pid].get("right", ""),
                    "old_status": old_st,
                    "new_status": new_st,
                    "direction":  _direction(old_st, new_st),
                })
        elif in_new:
            added_pairs.append(dict(new_pairs[pid]))
        else:
            removed_pairs.append(dict(old_pairs[pid]))

    old_dist = Counter(p.get("v8_status", "") for p in old_pairs.values())
    new_dist = Counter(p.get("v8_status", "") for p in new_pairs.values())
    all_statuses = set(old_dist) | set(new_dist)
    distribution_diff = {
        st: new_dist.get(st, 0) - old_dist.get(st, 0)
        for st in sorted(all_statuses)
        if new_dist.get(st, 0) != old_dist.get(st, 0)
    }

    pairs_resolved = sum(
        1 for c in status_changes if c["new_status"] == "match"
    )

    coverage = _actions_coverage(old_bundle, new_bundle)
    asymmetric_warning: str | None = None
    if coverage in (ACTIONS_COVERAGE_OLD_ONLY, ACTIONS_COVERAGE_NEW_ONLY):
        asymmetric_warning = (
            f"actions_catalogue present in {coverage.split('_')[0]} bundle only; "
            "delta action comparisons are not available"
        )

    return {
        "schema_version": "v8-delta",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_generated_at": old_bundle.get("generated_at", ""),
        "current_generated_at":  new_bundle.get("generated_at", ""),
        "control_numbers": {
            "pairs_total":   len(all_ids),
            "pairs_changed": len(status_changes),
            "pairs_resolved": pairs_resolved,
            "pairs_new":     len(added_pairs),
            "pairs_removed": len(removed_pairs),
        },
        "status_changes":    status_changes,
        "distribution_diff": distribution_diff,
        "new_pairs":         added_pairs,
        "removed_pairs":     removed_pairs,
        "actions_coverage":  coverage,
        "asymmetric_actions_warning": asymmetric_warning,
    }


__all__ = [
    "STATUS_RANK",
    "DIRECTION_IMPROVED", "DIRECTION_DEGRADED", "DIRECTION_UNCHANGED",
    "DIRECTION_NEW", "DIRECTION_DROPPED",
    "ACTIONS_COVERAGE_SYMMETRIC", "ACTIONS_COVERAGE_OLD_ONLY",
    "ACTIONS_COVERAGE_NEW_ONLY", "ACTIONS_COVERAGE_NEITHER",
    "compare_bundles",
]
