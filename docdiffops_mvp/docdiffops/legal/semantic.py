"""Semantic LLM comparator (PR-5.5).

When ``SEMANTIC_COMPARATOR_ENABLED=true`` AND an ``LLM_API_KEY`` is set,
this module asks an LLM to judge each (claim, NPA-chunk) pair and emits
a verdict ``confirmed | partial | contradicts | not_found`` with a one-
sentence rationale.

The verdict ALWAYS rides alongside the deterministic claim_validation
result (the deterministic event is preserved); the LLM verdict is
attached as ``event.semantic`` for A/B comparison before flipping any
default.

Provider:
- OpenAI-compatible chat-completions endpoint (works with api.zed.md/v1,
  Anthropic via OpenAI-compat layers, OpenAI proper, Together, etc.)
- ``LLM_API_BASE`` + ``LLM_API_KEY`` + ``LLM_MODEL`` env vars
- ``stream:false`` request — no SSE parsing
- 30s connect / 60s total timeout
- Cost guard: ``SEMANTIC_MAX_CLAIMS_PER_PAIR`` (default 10) caps per-pair
  LLM calls; over budget falls back to deterministic-only

Failure mode: any exception in the LLM call returns ``None`` and a
warning is logged. The comparator never raises into the pipeline.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticVerdict:
    """LLM-issued verdict on a (claim, npa_chunk) pair."""

    status: str  # confirmed | partial | contradicts | not_found
    confidence: float  # 0..1 the LLM expressed (or default)
    rationale: str  # 1-2 sentence explanation in the source language
    model: str
    raw_response: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "model": self.model,
        }


def is_enabled() -> bool:
    """True iff the env flag AND ``LLM_API_KEY`` are set."""
    if os.getenv("SEMANTIC_COMPARATOR_ENABLED", "false").lower() != "true":
        return False
    return bool(_api_key())


def _api_key() -> str | None:
    return (
        os.getenv("LLM_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _api_base() -> str:
    return os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/")


def _model() -> str:
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


def budget_per_pair() -> int:
    try:
        return max(0, int(os.getenv("SEMANTIC_MAX_CLAIMS_PER_PAIR", "10")))
    except ValueError:
        return 10


_SYSTEM_PROMPT = (
    "Ты — асессор соответствия. Отвечаешь СТРОГО ОДНОЙ СТРОКОЙ "
    "ровно в формате: STATUS | RATIONALE\n"
    "STATUS — одно из латинских слов: confirmed | partial | contradicts | not_found.\n"
    "RATIONALE — короткое русское объяснение ≤ 20 слов.\n"
    "Никакого markdown, никаких списков, никаких заголовков. Не пиши «Да/Нет».\n"
    "Пример: confirmed | Норма прямо повторяет тезис.\n"
    "Пример: partial | Норма уточняет тезис до интеллектуальной миграции.\n"
    "Пример: not_found | Норма не упоминает данный тезис."
)

_USER_TEMPLATE = (
    "Тезис из аналитики: {claim}\n"
    "Норма ({chunk_kind} {chunk_number}): {chunk_text}\n"
    "Подтверждает ли норма этот тезис? Ответ строго одной строкой "
    "STATUS | RATIONALE."
)

_VALID_STATUS = {"confirmed", "partial", "contradicts", "not_found"}


def judge(
    claim_text: str,
    chunk_text: str,
    *,
    chunk_kind: str = "норма",
    chunk_number: str = "",
    model: str | None = None,
) -> SemanticVerdict | None:
    """Ask the LLM to judge (claim, chunk). Returns None on any error or
    when the comparator is disabled. Never raises."""
    if not is_enabled():
        return None
    api_key = _api_key()
    if not api_key:
        return None
    model = model or _model()
    user_prompt = _USER_TEMPLATE.format(
        claim=(claim_text or "").strip()[:1500],
        chunk_kind=chunk_kind,
        chunk_number=chunk_number or "",
        chunk_text=(chunk_text or "").strip()[:3000],
    )
    try:
        content = _post_chat(api_key, model, _SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.warning("semantic comparator HTTP failed: %s", e)
        return None
    return _parse_verdict(content, model)


def _post_chat(
    api_key: str,
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int = 80,
    json_object: bool = False,
) -> str:
    """Synchronous chat-completions POST. Returns the assistant content
    string. Raises on transport errors so the caller can downgrade.

    ``json_object=True`` adds ``response_format={"type":"json_object"}``
    which forces compliant providers to return valid JSON. Used by the
    llm_pair_diff comparator to avoid prose responses.
    """
    import json
    import urllib.error
    import urllib.request

    payload = {
        "model": model,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_api_base()}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    timeout = float(os.getenv("LLM_TIMEOUT_SEC", "60"))
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — trusted base from env
        raw = r.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    if "error" in parsed:
        raise RuntimeError(f"LLM error: {parsed['error']}")
    msg = (parsed.get("choices") or [{}])[0].get("message") or {}
    return (msg.get("content") or "").strip()


def _parse_verdict(content: str, model: str) -> SemanticVerdict | None:
    """Parse the ``STATUS | RATIONALE`` line. Tolerant in this order:

    1. ``STATUS | RATIONALE`` exact format (preferred).
    2. First-token English status without ``|``.
    3. Russian alias as first token.
    4. Substring scan: any English status anywhere in the text.
    5. Russian alias substring scan (``частично``, ``противоречит`` etc.)
       — handles models that return prose instead of the format.

    Returns ``None`` only when no recognizable status appears.
    """
    if not content:
        return None
    raw = content.strip()
    low = raw.lower()
    line = raw.splitlines()[0].strip()
    rationale = raw

    # 1. Pipe format.
    if "|" in line:
        head, _, tail = line.partition("|")
        status_token = head.strip().lower()
        rationale = tail.strip() or raw
        if status_token in _VALID_STATUS:
            return _verdict(status_token, rationale, model, raw)

    # 2-3. First token (English or RU alias).
    aliases = {
        "подтверждается": "confirmed",
        "подтверждено": "confirmed",
        "подтвержден": "confirmed",
        "соответствует": "confirmed",
        "частично": "partial",
        "точечно": "partial",
        "не_полностью": "partial",
        "противоречит": "contradicts",
        "противоречие": "contradicts",
        "опровергает": "contradicts",
        "не_найдено": "not_found",
        "ненайдено": "not_found",
        "отсутствует": "not_found",
        "нет": "not_found",
    }
    first = (line.split() or [""])[0].strip().lower().rstrip(".,:;!?")
    if first in _VALID_STATUS:
        return _verdict(first, rationale, model, raw)
    if first in aliases:
        return _verdict(aliases[first], rationale, model, raw)

    # 4. English substring scan (whole tokens only — no false positives).
    import re
    for st in _VALID_STATUS:
        if re.search(rf"\b{st}\b", low):
            return _verdict(st, rationale, model, raw)

    # 5. RU alias substring scan — handles "частично/точечно", "противоречит" etc.
    for alias, mapped in aliases.items():
        if alias in low:
            return _verdict(mapped, rationale, model, raw)

    return None


def _verdict(status: str, rationale: str, model: str, raw: str) -> SemanticVerdict:
    confidence = {
        "confirmed": 0.9,
        "partial": 0.65,
        "contradicts": 0.85,
        "not_found": 0.55,
    }[status]
    return SemanticVerdict(
        status=status,
        confidence=confidence,
        rationale=(rationale or raw)[:280],
        model=model,
        raw_response=raw[:600],
    )


__all__ = [
    "SemanticVerdict",
    "is_enabled",
    "budget_per_pair",
    "judge",
]
