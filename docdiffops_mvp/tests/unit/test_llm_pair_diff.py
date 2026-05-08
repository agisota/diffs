"""Tests for the LLM-driven pair diff comparator (PR-5.7-like)."""
from __future__ import annotations

import importlib

from docdiffops.legal.llm_pair_diff import (
    _doc_summary_text,
    _parse_json_array,
    is_enabled,
    llm_pair_diff,
)

# The package __init__ shadows the submodule name with the function;
# load the module explicitly so monkeypatches see ``mod._sem``.
mod = importlib.import_module("docdiffops.legal.llm_pair_diff")


def _doc(doc_id: str, rank: int, doc_type: str = "OTHER") -> dict:
    return {"doc_id": doc_id, "source_rank": rank, "doc_type": doc_type, "filename": doc_id + ".pdf"}


def _block(text: str, page: int = 1) -> dict:
    return {"block_id": f"b_{abs(hash(text))%10000:04d}", "text": text, "page_no": page}


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------


def test_disabled_when_flag_off(monkeypatch):
    monkeypatch.delenv("LLM_PAIR_DIFF_ENABLED", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    assert is_enabled() is False


def test_disabled_when_no_key(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_enabled() is False


def test_enabled_with_flag_and_key(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    assert is_enabled() is True


# ---------------------------------------------------------------------------
# _doc_summary_text
# ---------------------------------------------------------------------------


def test_doc_summary_concatenates_with_page_markers():
    text = _doc_summary_text([_block("hello", 1), _block("world", 2)], max_chars=200)
    assert "[p.1] hello" in text
    assert "[p.2] world" in text


def test_doc_summary_truncates_over_budget():
    blocks = [_block("a" * 200) for _ in range(5)]
    text = _doc_summary_text(blocks, max_chars=300)
    assert len(text) <= 310  # some slack for ellipsis
    assert text.endswith("…") or len(text) <= 300


def test_doc_summary_skips_empty():
    text = _doc_summary_text([_block(""), _block("real")], max_chars=100)
    assert "real" in text
    assert "[p.1] real" in text


# ---------------------------------------------------------------------------
# _parse_json_array
# ---------------------------------------------------------------------------


def test_parse_pure_json_array():
    out = _parse_json_array('[{"status":"added","topic":"x"}]')
    assert len(out) == 1
    assert out[0]["status"] == "added"


def test_parse_strips_markdown_fences():
    raw = "Some prose.\n```json\n[{\"status\":\"deleted\",\"topic\":\"y\"}]\n```\nMore prose."
    out = _parse_json_array(raw)
    assert len(out) == 1
    assert out[0]["status"] == "deleted"


def test_parse_handles_prose_around_json():
    raw = 'Here is the result: [{"status":"same","topic":"z"}] thanks!'
    out = _parse_json_array(raw)
    assert out[0]["topic"] == "z"


def test_parse_single_object_wrapped_to_list():
    raw = '{"status":"contradicts","topic":"k"}'
    out = _parse_json_array(raw)
    assert len(out) == 1
    assert out[0]["status"] == "contradicts"


def test_parse_recovers_from_trailing_comma():
    raw = '[{"status":"added","topic":"q",}]'
    out = _parse_json_array(raw)
    assert len(out) == 1


def test_parse_returns_empty_on_garbage():
    assert _parse_json_array("not json at all") == []
    assert _parse_json_array("") == []


# ---------------------------------------------------------------------------
# llm_pair_diff
# ---------------------------------------------------------------------------


def test_pair_diff_returns_empty_when_disabled(monkeypatch):
    monkeypatch.delenv("LLM_PAIR_DIFF_ENABLED", raising=False)
    out = llm_pair_diff(
        {"pair_id": "p"},
        _doc("a", 1), _doc("b", 1),
        [_block("hello")], [_block("world")],
    )
    assert out == []


def test_pair_diff_emits_events_from_llm_response(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    fake = (
        '[{"status":"added","severity":"high","topic":"новый пункт",'
        '"lhs_quote":"","rhs_quote":"Новый пункт о биометрии",'
        '"explanation":"Норма дополнена пунктом про биометрический учёт."}]'
    )
    monkeypatch.setattr(mod._sem, "_post_chat", lambda *a, **kw: fake)
    events = llm_pair_diff(
        {"pair_id": "p1"},
        _doc("a", 1), _doc("b", 1),
        [_block("Старая норма")], [_block("Новая норма")],
    )
    assert len(events) == 1
    e = events[0]
    assert e["status"] == "added"
    assert e["severity"] == "high"
    assert e["comparison_type"] == "llm_pair_diff"
    assert e["topic"] == "новый пункт"
    assert e["rhs"]["quote"] == "Новый пункт о биометрии"
    assert e["lhs"]["quote"] is None
    assert e["confidence"] >= 0.8


def test_pair_diff_filters_invalid_status(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    fake = '[{"status":"WHATEVER","topic":"x"},{"status":"modified","topic":"y"}]'
    monkeypatch.setattr(mod._sem, "_post_chat", lambda *a, **kw: fake)
    events = llm_pair_diff(
        {"pair_id": "p"},
        _doc("a", 1), _doc("b", 1),
        [_block("x")], [_block("y")],
    )
    assert len(events) == 1
    assert events[0]["status"] == "modified"


def test_pair_diff_caps_at_30_events(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    items = [{"status": "modified", "severity": "low", "topic": f"t{i}", "lhs_quote": "", "rhs_quote": "", "explanation": ""} for i in range(50)]
    fake = __import__("json").dumps(items)
    monkeypatch.setattr(mod._sem, "_post_chat", lambda *a, **kw: fake)
    events = llm_pair_diff(
        {"pair_id": "p"},
        _doc("a", 1), _doc("b", 1),
        [_block("x")], [_block("y")],
    )
    assert len(events) == 30


def test_pair_diff_returns_empty_on_transport_error(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")

    def boom(*a, **kw):
        raise RuntimeError("network")

    monkeypatch.setattr(mod._sem, "_post_chat", boom)
    events = llm_pair_diff(
        {"pair_id": "p"},
        _doc("a", 1), _doc("b", 1),
        [_block("x")], [_block("y")],
    )
    assert events == []


def test_pair_diff_event_ids_deterministic(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    fake = '[{"status":"same","topic":"t1"},{"status":"added","topic":"t2"}]'
    monkeypatch.setattr(mod._sem, "_post_chat", lambda *a, **kw: fake)
    a = llm_pair_diff({"pair_id": "p"}, _doc("a", 1), _doc("b", 1), [_block("x")], [_block("y")])
    b = llm_pair_diff({"pair_id": "p"}, _doc("a", 1), _doc("b", 1), [_block("x")], [_block("y")])
    assert [e["event_id"] for e in a] == [e["event_id"] for e in b]


def test_pair_diff_skips_when_blocks_empty(monkeypatch):
    monkeypatch.setenv("LLM_PAIR_DIFF_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-fake")
    monkeypatch.setattr(mod._sem, "_post_chat", lambda *a, **kw: '[]')
    out = llm_pair_diff({"pair_id": "p"}, _doc("a", 1), _doc("b", 1), [], [])
    assert out == []
