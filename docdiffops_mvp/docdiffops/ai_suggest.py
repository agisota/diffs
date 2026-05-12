"""Single-event AI suggestion for the review workflow.

Different from llm_pair_diff (which compares whole pairs). This module
takes ONE event (LHS quote vs RHS quote + status + doc types) and asks
the LLM 'should the reviewer accept or reject this revision?'. Returns
a structured recommendation that the SPA pre-fills in the popover.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_TIMEOUT = float(os.getenv("AI_SUGGEST_TIMEOUT", "30"))
_MODEL = os.getenv("AI_SUGGEST_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"


_SYSTEM = (
    "Ты — эксперт по правовой экспертизе документов. Тебе показывают одну "
    "правку между двумя версиями документа (LHS = старая, RHS = новая). "
    "Тебе нужно решить, стоит ли её принять (confirmed) или отклонить "
    "(rejected), и кратко обосновать на русском. "
    "Отвечай ТОЛЬКО валидным JSON: "
    '{"decision": "confirmed"|"rejected", "confidence": 0.0..1.0, "reasoning": "одно-два предложения"}'
)


def _build_user_prompt(
    event: dict[str, Any],
    lhs_doc: dict[str, Any] | None,
    rhs_doc: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    parts.append(f"Статус правки: {event.get('status') or '?'}")
    parts.append(f"Severity: {event.get('severity') or 'low'}")
    if lhs_doc:
        parts.append(
            f"LHS документ: {lhs_doc.get('filename') or lhs_doc.get('doc_id')} "
            f"(type={lhs_doc.get('doc_type')}, rank={lhs_doc.get('source_rank')})"
        )
    if rhs_doc:
        parts.append(
            f"RHS документ: {rhs_doc.get('filename') or rhs_doc.get('doc_id')} "
            f"(type={rhs_doc.get('doc_type')}, rank={rhs_doc.get('source_rank')})"
        )
    lhs_q = ((event.get("lhs") or {}).get("quote") or "").strip()
    rhs_q = ((event.get("rhs") or {}).get("quote") or "").strip()
    parts.append("")
    if lhs_q:
        parts.append(f"LHS: «{lhs_q}»")
    else:
        parts.append("LHS: (текста не было — это добавление в RHS)")
    if rhs_q:
        parts.append(f"RHS: «{rhs_q}»")
    else:
        parts.append("RHS: (текст удалён в RHS)")
    if event.get("explanation_short"):
        parts.append("")
        parts.append(f"Pipeline-комментарий: {event['explanation_short']}")
    parts.append("")
    parts.append(
        "Принять (confirmed) — если правка корректная, очевидная, или повышает соответствие закону. "
        "Отклонить (rejected) — если правка вводит ошибку, противоречие или ухудшает документ. "
        "Если сомневаешься — оценивай в пользу принятия (confirmed) только если "
        "правка действительно нейтральная или улучшающая."
    )
    return "\n".join(parts)


def suggest_for_event(
    event: dict[str, Any],
    lhs_doc: dict[str, Any] | None = None,
    rhs_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call the LLM and return {decision, confidence, reasoning, model} dict.

    Raises RuntimeError on missing config, transport failure, or parse error.
    """
    api_base = os.getenv("LLM_API_BASE", "").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_base or not api_key:
        raise RuntimeError("LLM not configured (LLM_API_BASE/LLM_API_KEY missing)")

    user_prompt = _build_user_prompt(event, lhs_doc, rhs_doc)
    body: dict[str, Any] = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "max_tokens": 400,
        # Provider (api.zed.md) defaults to streaming when this is omitted —
        # force non-streaming so the body is one JSON blob, not SSE chunks.
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            # Some providers (api.zed.md observed) ignore stream:false and
            # still emit SSE chunks. Parse the chunks ourselves and rebuild
            # a synthetic openai-shape response.
            if "data:" in raw:
                content_parts: list[str] = []
                final_usage = None
                for line in raw.splitlines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    for ch in chunk.get("choices") or []:
                        delta = ch.get("delta") or {}
                        if isinstance(delta.get("content"), str):
                            content_parts.append(delta["content"])
                    if chunk.get("usage"):
                        final_usage = chunk["usage"]
                if content_parts:
                    data = {
                        "choices": [{"message": {"content": "".join(content_parts)}}],
                        "usage": final_usage,
                    }
                else:
                    logger.warning("ai_suggest: SSE parsed but no content from %s: %r", api_base, raw[:500])
                    raise RuntimeError(f"LLM SSE returned no content: {raw[:200]!r}")
            else:
                logger.warning("ai_suggest: non-JSON response from %s: %r", api_base, raw[:500])
                raise RuntimeError(f"LLM returned non-JSON ({len(raw)}B): {raw[:200]!r}")
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="ignore")[:500]
        except Exception:
            pass
        raise RuntimeError(f"LLM HTTP {e.code}: {body_text}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM transport error: {e}") from e

    try:
        content = data["choices"][0]["message"]["content"]
        parsed: dict[str, Any] = json.loads(content)
    except (KeyError, json.JSONDecodeError) as e:
        raise RuntimeError(f"LLM returned unparseable response: {e}") from e

    decision = (parsed.get("decision") or "").strip().lower()
    if decision not in {"confirmed", "rejected"}:
        decision = "confirmed"  # safer default

    try:
        confidence = float(parsed.get("confidence") or 0.5)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(parsed.get("reasoning") or "").strip()[:500]

    return {
        "decision": decision,
        "confidence": round(confidence, 2),
        "reasoning": reasoning,
        "model": _MODEL,
    }
