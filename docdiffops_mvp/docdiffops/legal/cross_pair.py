"""Cross-pair event clustering (post-processing).

After the pipeline emits per-pair events for all C(N,2) pairs, the same
factual difference often appears in multiple pairs. Example: an Указ
that exists only in one rank-1 doc shows as ``added`` in every pair
that includes that doc.

This module groups events by (status, normalized topic) across ALL
pairs of the batch, producing a flatter view: one cluster per fact,
with the list of pair_ids that surfaced it.

Used by:
- evidence_matrix.xlsx — new ``11_topic_clusters`` sheet
- web UI — Topics tab on batch detail
- executive_diff — cluster-rolled summary instead of raw event list
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalize_topic(topic: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, strip accents.

    Aggressive enough that "Указ о миграционной политике" and
    "указ Президента о миграционной политике" cluster together; not so
    aggressive that distinct claims merge. ~80 chars max.
    """
    s = unicodedata.normalize("NFKC", topic or "").lower()
    s = re.sub(r"[«»\"'`()\[\]{}]+", " ", s)
    s = re.sub(r"[.,;:!?…\-—–]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80]


def _topic_similarity(a: str, b: str) -> float:
    """Token-based similarity 0..100. Falls back to simple Jaccard
    when rapidfuzz isn't available (it always is in this project,
    but we keep the fallback for portability)."""
    try:
        from rapidfuzz import fuzz
        return float(fuzz.token_set_ratio(a, b))
    except Exception:
        sa = set(a.split())
        sb = set(b.split())
        if not sa or not sb:
            return 0.0
        return 100.0 * len(sa & sb) / len(sa | sb)


def _maybe_merge(buckets: dict, status: str, normalized: str, threshold: int) -> str | None:
    """Find an existing bucket whose normalized topic is similar enough
    to ``normalized`` and return its key. Otherwise None."""
    for (st, norm) in list(buckets.keys()):
        if st != status:
            continue
        if norm == normalized:
            return norm
        if _topic_similarity(norm, normalized) >= threshold:
            return norm
    return None


def cluster_events(events: list[dict[str, Any]], *, similarity_threshold: int = 78) -> list[dict[str, Any]]:
    """Group events by (status, ~similar topic).

    Each cluster is a dict:
      {
        "cluster_id": stable str,
        "topic": canonical topic (longest seen),
        "status": status,
        "severity": worst severity in cluster,
        "comparison_types": list of distinct comparison_types,
        "pair_ids": list of pair_ids,
        "event_ids": list of event_ids,
        "count": number of events,
        "explanations": short list of distinct explanations,
        "first_event": full first event (for drill-down),
      }
    Sorted by severity (high first) then count desc.
    """
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    severity_order = {"high": 3, "medium": 2, "low": 1}
    buckets: dict[tuple[str, str], dict[str, Any]] = {}

    for e in events or []:
        topic = (e.get("topic") or "").strip()
        if not topic:
            # Fall back to short prefix of explanation for clusters
            # produced by the deterministic comparators that don't
            # set a topic field.
            topic = ((e.get("explanation_short") or "")[:60]).strip()
            if not topic:
                continue
        status_l = (e.get("status") or "").lower()
        normalized = _normalize_topic(topic)
        if not normalized:
            continue
        # Fuzzy merge: find an existing bucket whose topic is similar enough.
        merge_to = _maybe_merge(buckets, status_l, normalized, similarity_threshold)
        if merge_to is not None:
            normalized = merge_to
        key = (status_l, normalized)
        b = buckets.setdefault(key, {
            "topic": topic,
            "status": key[0],
            "severity_rank_max": 0,
            "comparison_types": set(),
            "pair_ids": [],
            "event_ids": [],
            "explanations": [],
            "first_event": e,
        })
        # Worst-severity wins.
        sev = (e.get("severity") or "low").lower()
        rank = severity_order.get(sev, 0)
        if rank > b["severity_rank_max"]:
            b["severity_rank_max"] = rank
        b["comparison_types"].add(e.get("comparison_type") or "?")
        if e.get("pair_id") and e["pair_id"] not in b["pair_ids"]:
            b["pair_ids"].append(e["pair_id"])
        if e.get("event_id"):
            b["event_ids"].append(e["event_id"])
        # Keep the longest topic seen — usually most informative.
        if len(topic) > len(b["topic"]):
            b["topic"] = topic
        expl = (e.get("explanation_short") or "").strip()
        if expl and expl not in b["explanations"] and len(b["explanations"]) < 3:
            b["explanations"].append(expl)

    sev_label = {3: "high", 2: "medium", 1: "low", 0: "low"}
    clusters = []
    for (status, _norm), b in buckets.items():
        sev = sev_label[b["severity_rank_max"]]
        cid_seed = f"{status}|{_normalize_topic(b['topic'])}"
        cluster_id = "cl_" + re.sub(r"\s+", "-", _normalize_topic(cid_seed))[:48]
        clusters.append({
            "cluster_id": cluster_id,
            "topic": b["topic"],
            "status": status,
            "severity": sev,
            "comparison_types": sorted(b["comparison_types"]),
            "pair_ids": list(b["pair_ids"]),
            "event_ids": list(b["event_ids"]),
            "count": len(b["event_ids"]),
            "explanations": b["explanations"],
            "first_event_id": (b["first_event"] or {}).get("event_id"),
        })

    clusters.sort(key=lambda c: (sev_rank.get(c["severity"], 3), -c["count"], c["topic"]))
    return clusters


__all__ = ["cluster_events"]
