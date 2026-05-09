"""Reproducibility & performance contract for the forensic bundle.

Two guarantees pinned by these tests:

  1. **Determinism**: same inputs always produce the same bundle structure.
     Anything that floats (timestamps) is masked before comparison.

  2. **Performance ceiling**: bundle generation for a 26-doc corpus stays
     under 100 ms, and for a 50-doc corpus (1225 pairs) under 500 ms.
     These are loose ceilings — they catch O(n²) → O(n³) regressions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time

import pytest

from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_actions import apply_actions_to_bundle


def _fingerprint(bundle: dict) -> str:
    """SHA-256 of canonical JSON, with timestamps masked."""
    masked = copy.deepcopy(bundle)
    masked["generated_at"] = "FIXED"
    blob = json.dumps(masked, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def _synthetic_corpus(n: int):
    docs = [
        {"id": f"D{i:02d}", "code": f"CODE_{i}", "rank": (1 if i % 2 == 0 else 3),
         "title": f"Document {i}", "type": "law" if i % 2 == 0 else "analytic"}
        for i in range(1, n + 1)
    ]
    pairs = []
    pid = 0
    for i in range(n):
        for j in range(i + 1, n):
            pid += 1
            pairs.append({
                "id": f"P{pid:04d}",
                "left": f"D{i + 1:02d}", "right": f"D{j + 1:02d}",
                "events": [
                    {"status": ("partial" if (i + j) % 3 == 0 else "same"),
                     "topic": "Цифровой профиль" if i % 4 == 0 else ""}
                ],
            })
    return docs, pairs


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_input_produces_identical_bundle_structure():
    docs, pairs = _synthetic_corpus(10)
    a = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    assert _fingerprint(a) == _fingerprint(b)


def test_action_application_is_deterministic():
    docs, pairs = _synthetic_corpus(10)
    bundle = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    a = apply_actions_to_bundle(bundle)
    b = apply_actions_to_bundle(bundle)
    assert _fingerprint(a) == _fingerprint(b)


def test_input_order_does_not_change_pair_status():
    """Pair ordering in the input shouldn't affect aggregated v8 statuses."""
    docs, pairs = _synthetic_corpus(8)
    bundle_a = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})

    pairs_rev = list(reversed(pairs))
    bundle_b = build_forensic_bundle(documents=docs, pairs=pairs_rev, events=[], amendment_graph={})

    statuses_a = {p["id"]: p["v8_status"] for p in bundle_a["pairs"]}
    statuses_b = {p["id"]: p["v8_status"] for p in bundle_b["pairs"]}
    assert statuses_a == statuses_b


def test_status_distribution_invariant_under_doc_relabel():
    """Renaming D01 → DZZ_001 must not change status histogram."""
    docs, pairs = _synthetic_corpus(8)
    bundle_a = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})

    rename = {f"D{i:02d}": f"DZZ_{i:03d}" for i in range(1, 9)}
    docs_r = [{**d, "id": rename[d["id"]]} for d in docs]
    pairs_r = [{**p, "left": rename[p["left"]], "right": rename[p["right"]]} for p in pairs]
    bundle_b = build_forensic_bundle(documents=docs_r, pairs=pairs_r, events=[], amendment_graph={})

    assert bundle_a["status_distribution_pairs"] == bundle_b["status_distribution_pairs"]


# ---------------------------------------------------------------------------
# Performance ceilings
# ---------------------------------------------------------------------------


def _time_build(n: int) -> float:
    docs, pairs = _synthetic_corpus(n)
    t0 = time.perf_counter()
    build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    return time.perf_counter() - t0


def test_perf_26_docs_under_100ms():
    """Reference corpus size: 26 docs → 325 pairs → must complete < 100 ms."""
    elapsed = _time_build(26)
    assert elapsed < 0.10, f"build_forensic_bundle(26 docs) took {elapsed * 1000:.1f}ms"


def test_perf_50_docs_under_500ms():
    """O(n²) pairs (1225) — ceiling 500 ms catches O(n³) regressions."""
    elapsed = _time_build(50)
    assert elapsed < 0.50, f"build_forensic_bundle(50 docs) took {elapsed * 1000:.1f}ms"


def test_perf_action_apply_under_50ms_for_26_docs():
    """apply_actions_to_bundle on the reference corpus stays cheap."""
    docs, pairs = _synthetic_corpus(26)
    bundle = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    t0 = time.perf_counter()
    apply_actions_to_bundle(bundle)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.05, f"apply_actions_to_bundle took {elapsed * 1000:.1f}ms"


# ---------------------------------------------------------------------------
# Schema validation throughput
# ---------------------------------------------------------------------------


def test_schema_validation_under_300ms_for_50_docs():
    from docdiffops.forensic_schema import validate_bundle
    docs, pairs = _synthetic_corpus(50)
    bundle = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    t0 = time.perf_counter()
    errs = validate_bundle(bundle)
    elapsed = time.perf_counter() - t0
    assert errs == [], errs
    assert elapsed < 0.30, f"validate_bundle took {elapsed * 1000:.1f}ms for 50-doc bundle"
