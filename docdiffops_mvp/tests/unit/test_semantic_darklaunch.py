"""Dark-launch tests for the semantic comparator (PR-5.5)."""
from __future__ import annotations

from docdiffops.legal.semantic import is_enabled, judge


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SEMANTIC_COMPARATOR_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_enabled() is False
    assert judge("any claim", "any chunk") is None


def test_disabled_when_flag_set_but_no_key(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_enabled() is False


def test_enabled_with_key_but_returns_none_until_client_wired(monkeypatch):
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    assert is_enabled() is True
    # Stub _call_provider returns None until the real client lands.
    v = judge("стимулировать миграцию", "Цель: стимулировать миграцию.")
    assert v is None


def test_judge_truncates_long_inputs(monkeypatch):
    """Long inputs must not raise; truncation happens silently."""
    monkeypatch.setenv("SEMANTIC_COMPARATOR_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    huge_claim = "a" * 10_000
    huge_chunk = "b" * 10_000
    # No exception, returns None per dark-launch contract.
    assert judge(huge_claim, huge_chunk) is None
