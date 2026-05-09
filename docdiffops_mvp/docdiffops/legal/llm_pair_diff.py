"""LLM-driven pair-level diff (replaces fuzzy block noise).

Takes two extracted documents and a single LLM call returns a curated
list of diff events — added / deleted / modified / partial / contradicts
— at the SEMANTIC level, not the token-overlap level.

Goal: collapse 250+ false-positive fuzzy events per pair into 10-30
high-signal events that actually move a reviewer's needle. Russian
morphology, document re-organization, and HTML/PDF extraction
differences no longer wreck precision.

Activated by ``LLM_PAIR_DIFF_ENABLED=true`` + ``LLM_API_KEY``.
Cost per pair: 1 LLM call with ~6-8K input tokens, ~1-2K output. With
faster200 / gpt-5.4-mini: ~$0.003 per pair. For 3 docs (3 pairs): ~$0.01.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

from . import semantic as _sem

logger = logging.getLogger(__name__)


_VALID_STATUS = {"same", "added", "deleted", "modified", "partial", "contradicts"}
_VALID_SEVERITY = {"low", "medium", "high"}


_SYSTEM_PROMPT = (
    "Ты — асессор сравнения двух русскоязычных документов. Найди "
    "СЕМАНТИЧЕСКИЕ различия. Игнорируй косметику и синонимы.\n\n"
    "Ответ — ТОЛЬКО ОДИН валидный JSON-объект без markdown:\n"
    "{\"events\": [ ... ]}\n\n"
    "Каждый элемент массива events:\n"
    "{\n"
    "  \"status\": \"added\"|\"deleted\"|\"modified\"|\"partial\"|\"contradicts\"|\"same\",\n"
    "  \"severity\": \"low\"|\"medium\"|\"high\",\n"
    "  \"topic\": краткая русская тема (≤ 10 слов),\n"
    "  \"lhs_quote\": дословная цитата из LHS (пусто если added),\n"
    "  \"rhs_quote\": дословная цитата из RHS (пусто если deleted),\n"
    "  \"explanation\": одно русское предложение, что и почему отличается\n"
    "}\n\n"
    "Возвращай 5-10 САМЫХ значимых событий (high-severity первыми). "
    "Цитаты ≤ 100 символов. Цитируй только то, что реально есть. "
    "Ничего, кроме JSON-объекта."
)

_USER_TEMPLATE = (
    "LHS документ ({lhs_label}):\n"
    "---\n{lhs}\n---\n\n"
    "RHS документ ({rhs_label}):\n"
    "---\n{rhs}\n---\n\n"
    "Верни {{\"events\": [ ... ]}}."
)


def is_enabled() -> bool:
    """LLM pair diff is enabled iff its own flag and the LLM key are set."""
    if os.getenv("LLM_PAIR_DIFF_ENABLED", "false").lower() != "true":
        return False
    return bool(_sem._api_key())


def _doc_summary_text(blocks: list[dict[str, Any]], *, max_chars: int) -> str:
    """Concatenate block texts with simple structural markers; cap length."""
    out: list[str] = []
    used = 0
    for b in blocks or []:
        t = (b.get("text") or "").strip()
        if not t:
            continue
        page = b.get("page_no")
        prefix = f"[p.{page}] " if page else ""
        chunk = prefix + t
        if used + len(chunk) + 1 > max_chars:
            remaining = max_chars - used
            if remaining > 50:
                out.append(chunk[: remaining - 3] + "…")
            break
        out.append(chunk)
        used += len(chunk) + 1
    return "\n".join(out)


def _split_into_segments(blocks: list[dict[str, Any]], *, segment_chars: int) -> list[str]:
    """Group blocks into segments of approximately ``segment_chars`` each.

    Blocks are kept atomic (a single block doesn't get split mid-sentence)
    unless an individual block exceeds the budget, in which case it's
    truncated. Returns the list of segments — never empty if any blocks
    have non-empty text.
    """
    segments: list[str] = []
    current: list[str] = []
    used = 0
    for b in blocks or []:
        t = (b.get("text") or "").strip()
        if not t:
            continue
        page = b.get("page_no")
        prefix = f"[p.{page}] " if page else ""
        piece = prefix + t
        if len(piece) > segment_chars * 1.5:
            # An over-long single block — split it on its own.
            if current:
                segments.append("\n".join(current))
                current, used = [], 0
            for i in range(0, len(piece), segment_chars):
                segments.append(piece[i : i + segment_chars])
            continue
        if used + len(piece) + 1 > segment_chars and current:
            segments.append("\n".join(current))
            current, used = [], 0
        current.append(piece)
        used += len(piece) + 1
    if current:
        segments.append("\n".join(current))
    return segments


def _doc_label(doc: dict[str, Any]) -> str:
    rank = doc.get("source_rank") or "?"
    dt = doc.get("doc_type") or "OTHER"
    name = doc.get("filename") or doc.get("doc_id") or "?"
    return f"rank-{rank} {dt} {name}"


def _event_id(pair_id: str, idx: int, topic: str) -> str:
    h = hashlib.sha256(f"{pair_id}|{idx}|{topic}".encode("utf-8")).hexdigest()
    return "evt_llm_" + h[:16]


def _call_llm_for_segment(
    api_key: str,
    model: str,
    max_tokens: int,
    lhs_label: str,
    rhs_label: str,
    lhs_text: str,
    rhs_text: str,
    pair_id: str,
) -> list[dict[str, Any]]:
    """One LLM call → list of raw event dicts (validated upstream)."""
    user = _USER_TEMPLATE.format(
        lhs_label=lhs_label, rhs_label=rhs_label, lhs=lhs_text, rhs=rhs_text,
    )
    try:
        raw = _sem._post_chat(
            api_key, model, _SYSTEM_PROMPT, user,
            max_tokens=max_tokens, json_object=True,
        )
    except Exception as e:
        logger.warning("llm_pair_diff HTTP failed for %s: %s", pair_id, e)
        try:
            raw = _sem._post_chat(
                api_key, model, _SYSTEM_PROMPT, user,
                max_tokens=max_tokens, json_object=False,
            )
        except Exception as e2:
            logger.warning("llm_pair_diff retry failed: %s", e2)
            return []
    items = _parse_json_array(raw)
    if len(items) == 1 and isinstance(items[0], dict) and "events" in items[0] and isinstance(items[0]["events"], list):
        items = items[0]["events"]
    if not items:
        logger.warning("llm_pair_diff parse failed for %s; raw[0:200]=%r", pair_id, raw[:200])
    return items


def llm_pair_diff(
    pair: dict[str, Any],
    lhs_doc: dict[str, Any],
    rhs_doc: dict[str, Any],
    lhs_blocks: list[dict[str, Any]],
    rhs_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return semantic diff events for ``pair``.

    Strategy:
    - Split each side into ~3-4KB segments.
    - For each pair of segments at the same position, run one LLM call.
    - Aggregate events with deduplication on (status, topic).

    The chunked approach beats the single-call approach on big docs:
    it never blows the token budget and lets long docs surface ~20-30
    curated events instead of getting truncated to 0.

    Returns ``[]`` when disabled or on universal failure.
    """
    if not is_enabled():
        return []
    api_key = _sem._api_key()
    if not api_key:
        return []
    model = os.getenv("LLM_PAIR_DIFF_MODEL") or _sem._model()
    pair_id = pair.get("pair_id") or "?"

    # Per-segment budget — leave room for the system prompt and JSON
    # envelope. 3500 chars per side per call comfortably fits a 4K-token
    # response on most providers.
    segment_chars = int(os.getenv("LLM_PAIR_DIFF_SEGMENT_CHARS", "3500"))
    max_tokens = int(os.getenv("LLM_PAIR_DIFF_MAX_TOKENS", "4000"))
    max_segments = int(os.getenv("LLM_PAIR_DIFF_MAX_SEGMENTS", "4"))

    lhs_segments = _split_into_segments(lhs_blocks, segment_chars=segment_chars)
    rhs_segments = _split_into_segments(rhs_blocks, segment_chars=segment_chars)
    if not lhs_segments or not rhs_segments:
        return []

    # Position-paired segments (segment 1 of LHS ↔ segment 1 of RHS, etc.).
    # When the doc lengths differ we still run zip-style pairs and drop
    # the rest — better than O(N²) cost. Bounded by max_segments.
    n_pairs = min(len(lhs_segments), len(rhs_segments), max_segments)
    if n_pairs == 0:
        return []

    lhs_label = _doc_label(lhs_doc)
    rhs_label = _doc_label(rhs_doc)
    raw_items: list[dict[str, Any]] = []
    for i in range(n_pairs):
        seg_items = _call_llm_for_segment(
            api_key, model, max_tokens, lhs_label, rhs_label,
            lhs_segments[i], rhs_segments[i], pair_id,
        )
        for it in seg_items:
            if isinstance(it, dict):
                it["_segment_index"] = i
                raw_items.append(it)

    if not raw_items:
        return []

    # Dedup events whose (status, normalized topic) collide — large docs
    # often surface the same difference in two adjacent segments.
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for it in raw_items:
        topic = (it.get("topic") or "").strip().lower()
        topic_key = re.sub(r"[\s\-—–.,;:!?]+", " ", topic)[:80]
        key = ((it.get("status") or "").lower(), topic_key)
        if key not in seen:
            seen[key] = it
    items = list(seen.values())

    out: list[dict[str, Any]] = []
    for i, it in enumerate(items[:30]):  # safety cap
        if not isinstance(it, dict):
            continue
        status = (it.get("status") or "").lower()
        if status not in _VALID_STATUS:
            continue
        severity = (it.get("severity") or "low").lower()
        if severity not in _VALID_SEVERITY:
            severity = "low"
        topic = (it.get("topic") or "").strip()[:120]
        ev = {
            "event_id": _event_id(pair_id, i, topic),
            "pair_id": pair_id,
            "comparison_type": "llm_pair_diff",
            "status": status,
            "severity": severity,
            "score": None,
            "confidence": _confidence_for(status, severity),
            "review_required": severity in {"high", "medium"} and status != "same",
            "lhs_doc_id": lhs_doc.get("doc_id"),
            "rhs_doc_id": rhs_doc.get("doc_id"),
            "topic": topic,
            "lhs": {
                "doc_id": lhs_doc.get("doc_id"),
                "page_no": None,
                "block_id": None,
                "bbox": None,
                "quote": (it.get("lhs_quote") or "").strip()[:600] or None,
            },
            "rhs": {
                "doc_id": rhs_doc.get("doc_id"),
                "page_no": None,
                "block_id": None,
                "bbox": None,
                "quote": (it.get("rhs_quote") or "").strip()[:600] or None,
            },
            "explanation_short": (it.get("explanation") or "").strip()[:400],
            "model": model,
        }
        out.append(ev)
    return out


def _confidence_for(status: str, severity: str) -> float:
    base = {
        "same": 0.95,
        "added": 0.85,
        "deleted": 0.85,
        "modified": 0.75,
        "partial": 0.65,
        "contradicts": 0.85,
    }.get(status, 0.6)
    if severity == "high":
        base = min(1.0, base + 0.05)
    return round(base, 3)


def _parse_json_array(raw: str) -> list[Any]:
    """Best-effort extraction of a JSON array from LLM output.

    Handles: pure JSON, JSON wrapped in ```json fences, JSON with prose
    prefix/suffix, single object instead of array.
    """
    if not raw:
        return []
    txt = raw.strip()

    # Strip ```json ... ``` fences.
    fence = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", txt, re.DOTALL)
    if fence:
        txt = fence.group(1)

    # Find the first '[' or '{' and the last matching ']' or '}'.
    start = min(
        (txt.find("[") if "[" in txt else 10**9),
        (txt.find("{") if "{" in txt else 10**9),
    )
    if start == 10**9:
        return []
    end_arr = txt.rfind("]")
    end_obj = txt.rfind("}")
    end = max(end_arr, end_obj)
    if end <= start:
        return []
    blob = txt[start : end + 1]

    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        # Repair attempt 1: drop trailing commas.
        cleaned = re.sub(r",(\s*[}\]])", r"\1", blob)
        try:
            parsed = json.loads(cleaned)
        except Exception:
            # Repair attempt 2: response was truncated mid-object.
            # Find the last complete object inside the events array
            # and rebuild a valid {"events":[...]} envelope.
            try:
                parsed = _salvage_truncated_events(blob)
            except Exception:
                return []
            if parsed is None:
                return []

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _salvage_truncated_events(blob: str) -> dict | None:
    """Recover from a response cut off mid-event.

    Walks the blob to find the last balanced ``{...}`` that lives inside
    an ``events`` array, then closes the array+object explicitly. Returns
    ``None`` if no recoverable structure is present.
    """
    # Find the events array opener.
    arr_start = blob.find('"events"')
    if arr_start < 0:
        return None
    arr_start = blob.find("[", arr_start)
    if arr_start < 0:
        return None

    # Walk forward, tracking balanced braces of complete objects.
    depth = 0
    in_str = False
    esc = False
    last_complete = arr_start  # position right after last complete `{...}`
    i = arr_start + 1
    while i < len(blob):
        c = blob[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    last_complete = i + 1
        i += 1

    if last_complete == arr_start:
        return None

    # Reconstruct the envelope.
    repaired = "{\"events\":" + blob[arr_start:last_complete] + "]}"
    try:
        return json.loads(repaired)
    except Exception:
        return None


_SUMMARY_SYSTEM_PROMPT = (
    "Ты — асессор сравнения двух документов. Дай КРАТКОЕ описание главного "
    "различия одной строкой 30-60 слов на русском языке. Ничего, кроме самой "
    "сути. Не используй markdown. Не используй вводные фразы типа "
    "«В этом документе», «Здесь сравнение». Сразу к делу."
)

_SUMMARY_USER_TEMPLATE = (
    "LHS ({lhs_label}):\n{lhs}\n\n"
    "RHS ({rhs_label}):\n{rhs}\n\n"
    "Опиши главное различие 30-60 слов одной строкой."
)


def llm_pair_summary(
    pair: dict[str, Any],
    lhs_doc: dict[str, Any],
    rhs_doc: dict[str, Any],
    lhs_blocks: list[dict[str, Any]],
    rhs_blocks: list[dict[str, Any]],
) -> str | None:
    """One-line executive description of the pair's main difference.

    Returns ``None`` when the LLM is not available, on transport error,
    or on empty response. Cheap (1 short call), runs alongside
    llm_pair_diff. Result is attached to ``summary['narrative']`` for
    display in evidence_matrix.xlsx, executive_diff, and the SPA.
    """
    if not is_enabled():
        return None
    api_key = _sem._api_key()
    if not api_key:
        return None
    model = os.getenv("LLM_PAIR_DIFF_MODEL") or _sem._model()
    char_budget = int(os.getenv("LLM_PAIR_SUMMARY_CHAR_BUDGET", "8000"))
    per_side = char_budget // 2
    lhs_text = _doc_summary_text(lhs_blocks, max_chars=per_side)
    rhs_text = _doc_summary_text(rhs_blocks, max_chars=per_side)
    if not lhs_text or not rhs_text:
        return None
    user = _SUMMARY_USER_TEMPLATE.format(
        lhs_label=_doc_label(lhs_doc),
        rhs_label=_doc_label(rhs_doc),
        lhs=lhs_text,
        rhs=rhs_text,
    )
    try:
        raw = _sem._post_chat(
            api_key, model, _SUMMARY_SYSTEM_PROMPT, user,
            max_tokens=int(os.getenv("LLM_PAIR_SUMMARY_MAX_TOKENS", "200")),
        )
    except Exception as e:
        logger.warning("llm_pair_summary failed for %s: %s", pair.get("pair_id"), e)
        return None
    if not raw:
        return None
    # Strip leading bullets / quotes / markdown the model often adds.
    line = raw.strip().splitlines()[0] if raw.strip().splitlines() else raw.strip()
    return line.strip().lstrip("•-—–*>").strip().strip('"').strip("«»")[:500]


__all__ = ["llm_pair_diff", "llm_pair_summary", "is_enabled"]
