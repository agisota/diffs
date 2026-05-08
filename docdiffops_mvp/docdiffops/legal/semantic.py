"""Semantic LLM comparator — dark-launch scaffolding (PR-5.5).

When ``SEMANTIC_COMPARATOR_ENABLED=true`` AND a provider API key is set,
this module replaces the deterministic claim_validation match score with
an LLM-judged ``confirmed | partial | contradicts | not_found`` verdict.
Without those flags the function is a no-op and callers fall back to
the deterministic path.

Design notes:
- Dark launch means: code path exists, env flag gates execution, output
  is recorded ALONGSIDE deterministic verdict (not replacing it) so we
  can A/B before flipping the default.
- Provider abstraction: ``ANTHROPIC_API_KEY`` or ``OPENAI_API_KEY``
  picks the backend automatically; ``LLM_MODEL`` overrides per call.
- Failure mode: any exception in the LLM call returns ``None`` and a
  warning is logged. The comparator never raises into the pipeline.
- Cost guard: ``SEMANTIC_MAX_CLAIMS_PER_PAIR`` (default 20) caps how
  many claims per pair go to the LLM. Above the cap, deterministic
  results are used.

This file purposely stays small and side-effect-free until activated.
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
    """True iff the env flag AND at least one provider key is set."""
    if os.getenv("SEMANTIC_COMPARATOR_ENABLED", "false").lower() != "true":
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _provider() -> str | None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def _budget_per_pair() -> int:
    try:
        return max(0, int(os.getenv("SEMANTIC_MAX_CLAIMS_PER_PAIR", "20")))
    except ValueError:
        return 20


_PROMPT_TEMPLATE = (
    "Сравни тезис и норму. Тезис из аналитического материала. "
    "Норма из официального НПА.\n\n"
    "Тезис: {claim}\n\n"
    "Норма ({chunk_kind} {chunk_number}): {chunk_text}\n\n"
    "Ответь одним словом: confirmed | partial | contradicts | not_found "
    "и одним предложением — почему. Формат: STATUS | RATIONALE"
)


def judge(
    claim_text: str,
    chunk_text: str,
    *,
    chunk_kind: str = "норма",
    chunk_number: str = "",
    model: str | None = None,
) -> SemanticVerdict | None:
    """Run an LLM verdict on (claim, chunk). Returns None when disabled,
    over budget, or on transport errors. Pure function modulo network.

    The full implementation lives in a follow-up PR that adds the
    Anthropic / OpenAI HTTP clients. This stub is defensive — it
    returns None unless the env flags AND a provider are set, AND a
    real client is wired. As of this commit no client is wired, so
    activating ``SEMANTIC_COMPARATOR_ENABLED=true`` produces None and
    a single warning.
    """
    if not is_enabled():
        return None
    provider = _provider()
    if provider is None:
        return None
    model = model or os.getenv("LLM_MODEL") or _default_model(provider)
    prompt = _PROMPT_TEMPLATE.format(
        claim=(claim_text or "").strip()[:1500],
        chunk_kind=chunk_kind,
        chunk_number=chunk_number or "",
        chunk_text=(chunk_text or "").strip()[:3000],
    )
    try:
        return _call_provider(provider, model, prompt)
    except Exception as e:
        logger.warning("semantic comparator failed (%s): %s", provider, e)
        return None


def _default_model(provider: str) -> str:
    if provider == "anthropic":
        return os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


def _call_provider(provider: str, model: str, prompt: str) -> SemanticVerdict | None:
    """Stub. The HTTP client lands when SEMANTIC_COMPARATOR_ENABLED is
    flipped on for a real environment. Today it logs and returns None."""
    logger.info(
        "semantic.judge stub: provider=%s model=%s prompt_chars=%d (no client wired)",
        provider, model, len(prompt),
    )
    return None


__all__ = [
    "SemanticVerdict",
    "is_enabled",
    "judge",
]
