"""Forensic actions catalogue contract tests.

Pin the v8.1 actions / brochure red-green / Klerk→NPA / EAEU split / amendment
chain catalogues as data the system can consume per-batch. The catalogue is
domain-specific (Russian migration corpus); this test file fixes the structure
and asserts that any caller-supplied catalogue conforms to the same shape.
"""
from __future__ import annotations

import pytest

from docdiffops.forensic_actions import (
    ACTION_CATEGORIES,
    Action,
    AmendmentChainEntry,
    BrochureRedGreenEntry,
    DEFAULT_ACTIONS,
    DEFAULT_AMENDMENT_CHAIN,
    DEFAULT_BROCHURE_REDGREEN,
    DEFAULT_EAEU_SPLIT,
    DEFAULT_KLERK_NPA_LINKS,
    EAEUSplitEntry,
    KlerkNPALink,
    SEVERITY_LEVELS,
    actions_for_pair,
    apply_actions_to_bundle,
    raci_for_action,
)


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


def test_action_dataclass_has_required_fields():
    a = Action(
        id="FA-99",
        category="Test",
        severity="medium",
        where="nowhere",
        what_is_wrong="x",
        why="y",
        what_to_do="z",
        owner="qa",
        related_docs=["D01"],
        v8_status="manual_review",
    )
    assert a.id == "FA-99"
    assert a.severity == "medium"
    assert "D01" in a.related_docs


def test_default_actions_count_matches_v8_1_contract():
    assert len(DEFAULT_ACTIONS) == 10
    ids = [a.id for a in DEFAULT_ACTIONS]
    assert ids == [f"FA-{i:02d}" for i in range(1, 11)]


def test_all_actions_have_known_severity():
    for a in DEFAULT_ACTIONS:
        assert a.severity in SEVERITY_LEVELS, a.severity


def test_all_actions_have_known_category():
    for a in DEFAULT_ACTIONS:
        assert a.category in ACTION_CATEGORIES, f"{a.id}: unknown category {a.category!r}"


def test_brochure_redgreen_has_six_concrete_fixes():
    assert len(DEFAULT_BROCHURE_REDGREEN) == 6
    for entry in DEFAULT_BROCHURE_REDGREEN:
        assert entry.before, entry
        assert entry.after, entry
        assert entry.before != entry.after
        assert entry.basis  # ПП №2573 reference


def test_brochure_uses_more_than_in_red_and_not_less_in_green():
    """The defining BR fix: «более X» → «не менее X» on the porog rows."""
    porog_entries = [e for e in DEFAULT_BROCHURE_REDGREEN if "Критерий" in e.section]
    assert len(porog_entries) >= 4
    for e in porog_entries:
        assert "более" in e.before.lower(), e.before
        assert "не менее" in e.after.lower(), e.after


def test_klerk_links_cover_six_main_themes():
    assert len(DEFAULT_KLERK_NPA_LINKS) == 6
    for link in DEFAULT_KLERK_NPA_LINKS:
        assert link.thesis  # the claim
        assert link.npa_doc  # primary NPA
        assert link.specific_place  # article/paragraph
        assert link.footnote  # text to add


def test_eaeu_split_has_three_groups():
    assert len(DEFAULT_EAEU_SPLIT) == 3
    groups = [e.group for e in DEFAULT_EAEU_SPLIT]
    assert any("ЕАЭС" in g for g in groups)
    # The contradicting group must list non-EAEU countries explicitly
    non_eaeu = next(e for e in DEFAULT_EAEU_SPLIT if "Узбекистан" in e.countries)
    assert "патент" in non_eaeu.work_regime.lower()


def test_amendment_chain_links_known_documents():
    assert len(DEFAULT_AMENDMENT_CHAIN) == 5
    chains = {c.id: c for c in DEFAULT_AMENDMENT_CHAIN}
    # ruID chain must cite ПП 1510 → 468
    rui = chains["AC-01"]
    assert "1510" in rui.base_act
    assert "468" in rui.amendments_chronology or "468" in rui.cite_now


# ---------------------------------------------------------------------------
# actions_for_pair: which actions are relevant to a given pair?
# ---------------------------------------------------------------------------


def test_actions_for_pair_d18_d20_returns_brochure_action():
    matched = actions_for_pair("D18", "D20")
    ids = [a.id for a in matched]
    assert "FA-01" in ids


def test_actions_for_pair_d10_d26_returns_eaeu_action():
    matched = actions_for_pair("D10", "D26")
    ids = [a.id for a in matched]
    assert "FA-02" in ids


def test_actions_for_pair_d09_returns_klerk_action_for_any_npa():
    """D09 (Klerk) paired with any rank-1 NPA should match FA-03."""
    for rhs in ("D11", "D15", "D17", "D12", "D13"):
        matched = actions_for_pair("D09", rhs)
        assert any(a.id == "FA-03" for a in matched), f"no FA-03 for D09↔{rhs}"


def test_actions_for_pair_unrelated_pair_returns_empty():
    matched = actions_for_pair("D01", "D02")
    assert matched == []


# ---------------------------------------------------------------------------
# RACI matrix
# ---------------------------------------------------------------------------


def test_raci_for_action_returns_dict_with_four_roles():
    raci = raci_for_action("FA-01")
    assert set(raci.keys()) == {"R", "A", "C", "I"}
    # Brochure fix: юрист is accountable
    assert "юрист" in raci["A"].lower() or "юрист" in raci["R"].lower()


def test_raci_for_unknown_action_returns_empty():
    raci = raci_for_action("FA-99")
    assert raci == {"R": "", "A": "", "C": "", "I": ""}


# ---------------------------------------------------------------------------
# Bundle integration
# ---------------------------------------------------------------------------


def test_apply_actions_to_bundle_attaches_relevant_actions_per_pair():
    bundle = {
        "schema_version": "v8.0",
        "documents": [
            {"id": "D18", "code": "MINEK_BROCHURE", "rank": 2, "title": "брошюра", "type": "brochure"},
            {"id": "D20", "code": "PP_2573", "rank": 1, "title": "ПП 2573", "type": "law"},
            {"id": "D10", "code": "MINEK", "rank": 2, "title": "Минэк", "type": "screenshots"},
            {"id": "D26", "code": "EAEU", "rank": 1, "title": "ЕАЭС", "type": "treaty"},
            {"id": "D01", "code": "NEURON", "rank": 3, "title": "neuron", "type": "manual"},
            {"id": "D02", "code": "XLSX", "rank": 3, "title": "xlsx", "type": "table"},
        ],
        "pairs": [
            {"id": "P1", "left": "D18", "right": "D20", "v8_status": "manual_review",
             "events_count": 2, "topics": [], "rank_pair": "1—2"},
            {"id": "P2", "left": "D10", "right": "D26", "v8_status": "contradiction",
             "events_count": 1, "topics": [], "rank_pair": "1—2"},
            {"id": "P3", "left": "D01", "right": "D02", "v8_status": "not_comparable",
             "events_count": 0, "topics": [], "rank_pair": "3—3"},
        ],
    }
    out = apply_actions_to_bundle(bundle)

    by_id = {p["id"]: p for p in out["pairs"]}
    assert "FA-01" in by_id["P1"]["actions"]
    assert "FA-02" in by_id["P2"]["actions"]
    assert by_id["P3"]["actions"] == []
    # Bundle gains a top-level "actions_catalogue" with all 10 actions
    assert len(out["actions_catalogue"]) == 10


# ---------------------------------------------------------------------------
# Step 2 — corpus parameter / catalogue split
# ---------------------------------------------------------------------------


def _generic_bundle():
    return {
        "schema_version": "v8.0",
        "documents": [
            {"id": "X1", "code": "C", "rank": 1, "title": "t", "type": "law"},
            {"id": "X2", "code": "D", "rank": 1, "title": "t2", "type": "law"},
        ],
        "pairs": [
            {"id": "P1", "left": "X1", "right": "X2", "v8_status": "match",
             "events_count": 1, "topics": [], "rank_pair": "1—1"},
        ],
    }


def test_apply_actions_no_corpus_omits_supplementaries():
    out = apply_actions_to_bundle(_generic_bundle())
    assert "actions_catalogue" in out
    assert "raci_matrix" in out
    assert "brochure_redgreen" not in out
    assert "klerk_npa_links" not in out
    assert "eaeu_split" not in out
    assert "amendment_chain" not in out


def test_apply_actions_migration_v8_corpus_includes_supplementaries():
    out = apply_actions_to_bundle(_generic_bundle(), corpus="migration_v8")
    assert "actions_catalogue" in out
    assert "brochure_redgreen" in out
    assert "klerk_npa_links" in out
    assert "eaeu_split" in out
    assert "amendment_chain" in out
