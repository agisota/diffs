"""Tests for the semantic LLM comparator (PR-5.5)."""
from __future__ import annotations

from docdiffops.legal import semantic
from docdiffops.legal.semantic import (
    SemanticVerdict,
    _parse_verdict,
    is_enabled,
    judge,
)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SEMANTIC_COMPARATOR_ENABLED", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_enabled() is False
    assert judge("any claim", "any chunk") is None


def test_disabled_when_flag_set_but_no_key(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_enabled() is False


def test_enabled_when_flag_and_llm_api_key_set(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    assert is_enabled() is True


def test_enabled_with_legacy_openai_key(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    assert is_enabled() is True


def test_judge_returns_none_on_http_error(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")

    def boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(semantic, "_post_chat", boom)
    assert judge("claim", "chunk") is None


def test_judge_parses_pipe_format(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    monkeypatch.setattr(
        semantic, "_post_chat",
        lambda *a, **kw: "confirmed | Тезис прямо отражён в норме.",
    )
    v = judge("стимулировать миграцию", "стимулировать миграцию")
    assert isinstance(v, SemanticVerdict)
    assert v.status == "confirmed"
    assert v.confidence == 0.9
    assert "норме" in v.rationale


def test_judge_parses_russian_alias(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    monkeypatch.setattr(
        semantic, "_post_chat",
        lambda *a, **kw: "Подтверждается | Норма прямо упоминает это.",
    )
    v = judge("x", "y")
    assert v is not None
    assert v.status == "confirmed"


def test_judge_extracts_status_from_prose(monkeypatch):
    """When the model returns plain prose without ``|``, we still find
    a recognized status token elsewhere in the response."""
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    monkeypatch.setattr(
        semantic, "_post_chat",
        lambda *a, **kw: "Норма не содержит этого тезиса. not_found",
    )
    v = judge("x", "y")
    assert v is not None
    assert v.status == "not_found"


def test_parse_verdict_rejects_unrecognized():
    assert _parse_verdict("blablabla without any status word", "m") is None


def test_parse_verdict_handles_empty():
    assert _parse_verdict("", "m") is None


def test_judge_truncates_long_inputs(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    captured = {}

    def fake_post(api_key, model, system, user):
        captured["user"] = user
        return "confirmed | ok"

    monkeypatch.setattr(semantic, "_post_chat", fake_post)
    judge("a" * 5000, "b" * 5000)
    # Truncation: claim 1500 + chunk 3000 + template wrapper ≈ 4600.
    assert len(captured["user"]) <= 5200


def test_budget_per_pair_default_and_override(monkeypatch):
    monkeypatch.delenv("SEMANTIC_MAX_CLAIMS_PER_PAIR", raising=False)
    assert semantic.budget_per_pair() == 10
    monkeypatch.setenv("SEMANTIC_MAX_CLAIMS_PER_PAIR", "3")
    assert semantic.budget_per_pair() == 3
    monkeypatch.setenv("SEMANTIC_MAX_CLAIMS_PER_PAIR", "garbage")
    assert semantic.budget_per_pair() == 10
