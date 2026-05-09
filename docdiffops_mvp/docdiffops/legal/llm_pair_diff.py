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


def _doc_label(doc: dict[str, Any]) -> str:
    rank = doc.get("source_rank") or "?"
    dt = doc.get("doc_type") or "OTHER"
    name = doc.get("filename") or doc.get("doc_id") or "?"
    return f"rank-{rank} {dt} {name}"


def _event_id(pair_id: str, idx: int, topic: str) -> str:
    h = hashlib.sha256(f"{pair_id}|{idx}|{topic}".encode("utf-8")).hexdigest()
    return "evt_llm_" + h[:16]


def llm_pair_diff(
    pair: dict[str, Any],
    lhs_doc: dict[str, Any],
    rhs_doc: dict[str, Any],
    lhs_blocks: list[dict[str, Any]],
    rhs_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return semantic diff events for ``pair`` via a single LLM call.

    Returns ``[]`` when disabled, on transport errors, or on parse
    failure. Never raises into the caller.
    """
    if not is_enabled():
        return []
    api_key = _sem._api_key()
    if not api_key:
        return []
    model = os.getenv("LLM_PAIR_DIFF_MODEL") or _sem._model()
    char_budget = int(os.getenv("LLM_PAIR_DIFF_CHAR_BUDGET", "12000"))
    per_side = char_budget // 2

    lhs_text = _doc_summary_text(lhs_blocks, max_chars=per_side)
    rhs_text = _doc_summary_text(rhs_blocks, max_chars=per_side)
    if not lhs_text or not rhs_text:
        return []

    user = _USER_TEMPLATE.format(
        lhs_label=_doc_label(lhs_doc),
        rhs_label=_doc_label(rhs_doc),
        lhs=lhs_text,
        rhs=rhs_text,
    )

    max_tokens = int(os.getenv("LLM_PAIR_DIFF_MAX_TOKENS", "4000"))
    try:
        raw = _sem._post_chat(
            api_key, model, _SYSTEM_PROMPT, user,
            max_tokens=max_tokens, json_object=True,
        )
    except Exception as e:
        logger.warning("llm_pair_diff HTTP failed for %s: %s", pair.get("pair_id"), e)
        # Some providers reject response_format; retry without it.
        try:
            raw = _sem._post_chat(
                api_key, model, _SYSTEM_PROMPT, user,
                max_tokens=max_tokens, json_object=False,
            )
        except Exception as e2:
            logger.warning("llm_pair_diff retry failed: %s", e2)
            return []

    items = _parse_json_array(raw)
    # When response is a JSON object with "events" key, unwrap it.
    if len(items) == 1 and isinstance(items[0], dict) and "events" in items[0] and isinstance(items[0]["events"], list):
        items = items[0]["events"]
    if not items:
        logger.warning("llm_pair_diff parse failed for %s; raw[0:200]=%r", pair.get("pair_id"), raw[:200])
        return []

    pair_id = pair.get("pair_id") or "?"
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


__all__ = ["llm_pair_diff", "is_enabled"]
