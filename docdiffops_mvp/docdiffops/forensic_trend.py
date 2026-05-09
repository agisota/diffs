"""Multi-batch forensic trend analysis.

Roll N consecutive v8 bundles into a time-series view: status distribution
over time, control-number trajectory, and pair-status delta sequence. Useful
for longitudinal quality tracking ("does our corpus get healthier?").

Pure module — no DB, no IO. Operates on in-memory bundle dicts.

Usage::

    from docdiffops.forensic_trend import compute_trend
    trend = compute_trend([bundle_jan, bundle_feb, bundle_mar])
    # trend["timeline"] — list of per-bundle snapshots in input order
    # trend["status_series"] — {status: [count_per_bundle]}
    # trend["match_share_series"] — match-percentage trajectory
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .forensic import STATUS_MATCH, V8_STATUSES


def compute_trend(bundles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate a sequence of v8 bundles into a time-series view.

    Bundles are assumed to be in chronological order (oldest first).
    Each bundle must have ``schema_version`` starting with ``"v8."``.

    Returns a dict with:
      * ``schema_version``        — ``"v8-trend"``
      * ``bundle_count``          — number of bundles
      * ``timeline``              — list of per-bundle snapshots
        (id, generated_at, pairs_total, pairs_match,
         pairs_contradiction, pairs_review, match_share)
      * ``status_series``         — {status_code: [count_per_bundle]}
      * ``match_share_series``    — list of match-percentage values
      * ``contradiction_series``  — list of contradiction counts
      * ``review_series``         — list of manual-review counts
      * ``trend_direction``       — "improving" | "degrading" | "stable"
        (based on first-vs-last match share)

    Raises ``ValueError`` if any bundle has incompatible schema_version
    or the input list is empty.
    """
    if not bundles:
        raise ValueError("compute_trend: input is empty; need at least one bundle")
    for i, b in enumerate(bundles):
        sv = b.get("schema_version", "")
        if not str(sv).startswith("v8."):
            raise ValueError(
                f"compute_trend: bundle index {i} has incompatible "
                f"schema_version={sv!r}; expected v8.x"
            )

    timeline: list[dict[str, Any]] = []
    status_series: dict[str, list[int]] = {st: [] for st in V8_STATUSES}

    for i, b in enumerate(bundles):
        sd = b.get("status_distribution_pairs") or {}
        cn = b.get("control_numbers") or {}
        pairs_total = cn.get("pairs", sum(sd.values()))
        match_n = sd.get(STATUS_MATCH, 0)
        match_share = (match_n * 100 / pairs_total) if pairs_total else 0
        snapshot = {
            "index":              i,
            "generated_at":       b.get("generated_at", ""),
            "schema_version":     b.get("schema_version", ""),
            "pairs_total":        pairs_total,
            "pairs_match":        match_n,
            "pairs_contradiction":sd.get("contradiction", 0),
            "pairs_manual_review":sd.get("manual_review", 0),
            "pairs_partial":      sd.get("partial_overlap", 0),
            "pairs_outdated":     sd.get("outdated", 0),
            "pairs_source_gap":   sd.get("source_gap", 0),
            "pairs_not_comparable":sd.get("not_comparable", 0),
            "match_share":        round(match_share, 2),
        }
        timeline.append(snapshot)
        for st in V8_STATUSES:
            status_series[st].append(sd.get(st, 0))

    match_share_series = [t["match_share"] for t in timeline]
    contradiction_series = [t["pairs_contradiction"] for t in timeline]
    review_series = [t["pairs_manual_review"] for t in timeline]

    if len(timeline) >= 2:
        first_share = match_share_series[0]
        last_share = match_share_series[-1]
        delta = last_share - first_share
        if delta > 1.0:
            trend_direction = "improving"
        elif delta < -1.0:
            trend_direction = "degrading"
        else:
            trend_direction = "stable"
    else:
        trend_direction = "stable"

    return {
        "schema_version":      "v8-trend",
        "bundle_count":        len(bundles),
        "timeline":            timeline,
        "status_series":       status_series,
        "match_share_series":  match_share_series,
        "contradiction_series":contradiction_series,
        "review_series":       review_series,
        "trend_direction":     trend_direction,
    }


__all__ = ["compute_trend"]
