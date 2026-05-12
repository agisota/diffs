"""LLM-event position enrichment via fuzzy-match to extract blocks.

LLM pair-diff returns events with text quotes but no page/bbox/block_id
(see llm_pair_diff.py:280-293). For inline viewer we need positions —
this module re-attaches them by fuzzy-matching the quote against the
extracted blocks of the same document.

Match threshold: rapidfuzz token_set_ratio >= 85 (chosen empirically;
80 produced false positives on numerically-similar regulatory text).
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from rapidfuzz import fuzz, process  # type: ignore
except ImportError:  # pragma: no cover — rapidfuzz is in compare.py deps already
    fuzz = None
    process = None

logger = logging.getLogger(__name__)

_MIN_QUOTE_LEN = 20
_MIN_SCORE = 85


def _enrich_side(side_data: dict, blocks: list[dict]) -> bool:
    """Return True if side_data was enriched in place."""
    if not side_data:
        return False
    if side_data.get("bbox") and side_data.get("page_no"):
        return False
    quote = side_data.get("quote")
    if not quote or len(quote.strip()) < _MIN_QUOTE_LEN:
        return False
    if not blocks or process is None:
        return False
    cands = [(b.get("text") or "") for b in blocks]
    m = process.extractOne(quote, cands, scorer=fuzz.token_set_ratio)
    if not m:
        return False
    _matched_text, score, idx = m
    if score < _MIN_SCORE:
        return False
    blk = blocks[idx]
    side_data["page_no"] = blk.get("page_no")
    side_data["block_id"] = blk.get("block_id")
    side_data["bbox"] = blk.get("bbox")
    side_data["enrichment_score"] = round(float(score), 2)
    return True


def enrich_llm_events(
    events: list[dict],
    lhs_blocks: list[dict],
    rhs_blocks: list[dict],
) -> int:
    """Mutate events in place: attach page/bbox/block_id where missing.

    Returns the number of side-slots enriched (each event has 2 slots:
    lhs and rhs, counted separately).
    """
    enriched = 0
    for ev in events or []:
        lhs = ev.get("lhs")
        rhs = ev.get("rhs")
        if isinstance(lhs, dict) and _enrich_side(lhs, lhs_blocks):
            ev["lhs"] = lhs
            # mirror flat columns used by db.add_diff_event
            ev["lhs_page"] = lhs.get("page_no")
            ev["lhs_bbox"] = lhs.get("bbox")
            ev["lhs_block_id"] = lhs.get("block_id")
            enriched += 1
        if isinstance(rhs, dict) and _enrich_side(rhs, rhs_blocks):
            ev["rhs"] = rhs
            ev["rhs_page"] = rhs.get("page_no")
            ev["rhs_bbox"] = rhs.get("bbox")
            ev["rhs_block_id"] = rhs.get("block_id")
            enriched += 1
    if enriched:
        logger.info("enrich_llm_events attached positions for %d side-slots", enriched)
    return enriched
