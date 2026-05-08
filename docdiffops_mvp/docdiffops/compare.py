from __future__ import annotations

import itertools
import re
from typing import Any

from rapidfuzz import fuzz, process

from .utils import compact_text, stable_id


def pair_id(lhs_id: str, rhs_id: str) -> str:
    return "pair_" + stable_id(lhs_id, rhs_id, n=20)


def build_pairs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = []
    for lhs, rhs in itertools.combinations(docs, 2):
        pairs.append({
            "pair_id": pair_id(lhs["doc_id"], rhs["doc_id"]),
            "lhs_doc_id": lhs["doc_id"],
            "rhs_doc_id": rhs["doc_id"],
        })
    return pairs


def numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", s or ""))


def best_match(block: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    if not candidates:
        return None, 0.0
    norms = [c.get("norm", "") for c in candidates]
    result = process.extractOne(block.get("norm", ""), norms, scorer=fuzz.token_set_ratio)
    if not result:
        return None, 0.0
    _, score, idx = result
    return candidates[idx], float(score)


def classify_severity(status: str, lhs_doc: dict[str, Any], rhs_doc: dict[str, Any], score: float, text_len: int) -> str:
    rank_l = int(lhs_doc.get("source_rank", 3) or 3)
    rank_r = int(rhs_doc.get("source_rank", 3) or 3)
    legal = lhs_doc.get("doc_type", "").startswith("LEGAL") or rhs_doc.get("doc_type", "").startswith("LEGAL")
    if status in {"contradicts", "deleted", "added"} and legal and min(rank_l, rank_r) <= 1:
        return "high" if text_len > 80 else "medium"
    if status in {"partial", "modified"} and score < 85:
        return "medium"
    return "low"


def make_event(pair: dict[str, Any], lhs_doc: dict[str, Any], rhs_doc: dict[str, Any], status: str, lhs_block: dict[str, Any] | None, rhs_block: dict[str, Any] | None, score: float, explanation: str) -> dict[str, Any]:
    lhs_text = lhs_block.get("text") if lhs_block else ""
    rhs_text = rhs_block.get("text") if rhs_block else ""
    event_id = "evt_" + stable_id(pair["pair_id"], status, lhs_block.get("block_id") if lhs_block else "", rhs_block.get("block_id") if rhs_block else "", n=20)
    text_len = max(len(lhs_text or ""), len(rhs_text or ""))
    return {
        "event_id": event_id,
        "pair_id": pair["pair_id"],
        "lhs_doc_id": lhs_doc["doc_id"],
        "rhs_doc_id": rhs_doc["doc_id"],
        "comparison_type": infer_comparison_type(lhs_doc, rhs_doc),
        "status": status,
        "severity": classify_severity(status, lhs_doc, rhs_doc, score, text_len),
        "confidence": round(min(max(score / 100.0, 0), 1), 3),
        "score": round(score, 2),
        "lhs": evidence(lhs_block, lhs_doc),
        "rhs": evidence(rhs_block, rhs_doc),
        "explanation_short": explanation,
        "explanation_full": explanation,
        "review_required": status in {"partial", "contradicts", "manual_review", "not_found"} or classify_severity(status, lhs_doc, rhs_doc, score, text_len) == "high",
        "reviewer_decision": None,
        "reviewer_comment": None,
    }


def evidence(block: dict[str, Any] | None, doc: dict[str, Any]) -> dict[str, Any] | None:
    if not block:
        return None
    return {
        "doc_id": doc["doc_id"],
        "doc_title": doc.get("title") or doc.get("filename"),
        "doc_type": doc.get("doc_type"),
        "source_rank": doc.get("source_rank"),
        "page_no": block.get("page_no"),
        "block_id": block.get("block_id"),
        "bbox": block.get("bbox"),
        "quote": compact_text(block.get("text", ""), 700),
        "meta": block.get("meta", {}),
    }


def infer_comparison_type(lhs_doc: dict[str, Any], rhs_doc: dict[str, Any]) -> str:
    a = lhs_doc.get("doc_type", "OTHER")
    b = rhs_doc.get("doc_type", "OTHER")
    if "PRESENTATION" in {a, b} and ("LEGAL_NPA" in {a, b} or "LEGAL_CONCEPT" in {a, b}):
        return "claim_validation"
    if {a, b} <= {"LEGAL_CONCEPT", "LEGAL_NPA", "GOV_PLAN"}:
        return "legal_or_policy_diff"
    if a == "TABLE" and b == "TABLE":
        return "table_diff"
    return "block_semantic_diff"


def compare_pair(pair: dict[str, Any], lhs_doc: dict[str, Any], rhs_doc: dict[str, Any], lhs_blocks: list[dict[str, Any]], rhs_blocks: list[dict[str, Any]], same_threshold: int = 92, partial_threshold: int = 78) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    same_count = 0
    partial_count = 0

    for lb in lhs_blocks:
        rb, score = best_match(lb, rhs_blocks)
        if score >= same_threshold:
            # If matching text has different numbers, escalate to modified_numeric.
            if rb and numbers(lb.get("text", "")) and numbers(rb.get("text", "")) and numbers(lb.get("text", "")) != numbers(rb.get("text", "")):
                events.append(make_event(pair, lhs_doc, rhs_doc, "modified", lb, rb, score, "Похожий блок содержит отличающиеся числовые значения; нужна проверка контекста."))
            else:
                same_count += 1
        elif score >= partial_threshold and rb:
            partial_count += 1
            events.append(make_event(pair, lhs_doc, rhs_doc, "partial", lb, rb, score, "Частичное совпадение: формулировки близки, но не эквивалентны. Требуется экспертная проверка."))
        else:
            events.append(make_event(pair, lhs_doc, rhs_doc, "deleted", lb, rb, score, "Фрагмент есть в левом документе и не найден с достаточной близостью в правом."))

    for rb in rhs_blocks:
        lb, score = best_match(rb, lhs_blocks)
        if score < partial_threshold:
            events.append(make_event(pair, lhs_doc, rhs_doc, "added", lb, rb, score, "Фрагмент есть в правом документе и не найден с достаточной близостью в левом."))

    summary = {
        "pair_id": pair["pair_id"],
        "lhs_doc_id": lhs_doc["doc_id"],
        "rhs_doc_id": rhs_doc["doc_id"],
        "events_total": len(events),
        "same_count": same_count,
        "partial_count": partial_count,
        "added_count": sum(1 for e in events if e["status"] == "added"),
        "deleted_count": sum(1 for e in events if e["status"] == "deleted"),
        "high_count": sum(1 for e in events if e["severity"] == "high"),
        "review_required_count": sum(1 for e in events if e["review_required"]),
    }
    return events, summary
