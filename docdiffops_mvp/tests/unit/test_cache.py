"""Unit tests for the content-addressed cache (PR-1.6)."""
from __future__ import annotations

import pytest

from docdiffops import cache
from docdiffops.storage.backend import reset_storage_for_tests


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setattr("docdiffops.storage.backend.DATA_DIR", tmp_path)
    reset_storage_for_tests()
    yield
    reset_storage_for_tests()


# ---------------------------------------------------------------------------
# make_key
# ---------------------------------------------------------------------------


def test_make_key_is_deterministic():
    a = cache.make_key("extract", "v1", "abc123")
    b = cache.make_key("extract", "v1", "abc123")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_make_key_changes_with_version():
    a = cache.make_key("extract", "v1", "abc")
    b = cache.make_key("extract", "v2", "abc")
    assert a != b


def test_make_key_changes_with_content():
    a = cache.make_key("extract", "v1", "abc")
    b = cache.make_key("extract", "v1", "def")
    assert a != b


def test_make_key_input_order_independent():
    """Pair compare key must not depend on LHS/RHS order."""
    a = cache.make_key("compare", "v1", "abc", "def")
    b = cache.make_key("compare", "v1", "def", "abc")
    assert a == b


def test_make_key_rejects_empty_scope():
    with pytest.raises(ValueError):
        cache.make_key("", "v1", "abc")


def test_make_key_rejects_pipe_in_scope():
    with pytest.raises(ValueError):
        cache.make_key("ex|tract", "v1", "abc")


def test_make_key_rejects_empty_version():
    with pytest.raises(ValueError):
        cache.make_key("extract", "", "abc")


def test_make_key_requires_at_least_one_content_hash():
    with pytest.raises(ValueError):
        cache.make_key("extract", "v1")


# ---------------------------------------------------------------------------
# extract_key / compare_key wrappers
# ---------------------------------------------------------------------------


def test_extract_key_uses_extractor_version(monkeypatch):
    monkeypatch.setattr("docdiffops.cache.EXTRACTOR_VERSION", "test-extr")
    k = cache.extract_key("doc-sha-123")
    expected = cache.make_key("extract", "test-extr", "doc-sha-123")
    assert k == expected


def test_compare_key_uses_comparator_version(monkeypatch):
    monkeypatch.setattr("docdiffops.cache.COMPARATOR_VERSION", "test-cmp")
    k = cache.compare_key("a", "b")
    expected = cache.make_key("compare", "test-cmp", "a", "b")
    assert k == expected


def test_compare_key_order_independence():
    assert cache.compare_key("x", "y") == cache.compare_key("y", "x")


# ---------------------------------------------------------------------------
# get / put / get_or_compute
# ---------------------------------------------------------------------------


def test_get_returns_none_when_missing():
    assert cache.get("extract", "nope") is None


def test_put_then_get_round_trip():
    cache.put("extract", "k1", {"blocks": [{"text": "hello"}], "n": 1})
    assert cache.get("extract", "k1") == {
        "blocks": [{"text": "hello"}],
        "n": 1,
    }


def test_get_or_compute_miss_runs_compute():
    calls = []

    def expensive():
        calls.append(1)
        return {"computed": True}

    val, hit = cache.get_or_compute("extract", "miss-key", expensive)
    assert hit is False
    assert val == {"computed": True}
    assert len(calls) == 1


def test_get_or_compute_hit_skips_compute():
    cache.put("extract", "hit-key", {"cached": True})
    calls = []

    def must_not_run():
        calls.append(1)
        return {"computed": True}

    val, hit = cache.get_or_compute("extract", "hit-key", must_not_run)
    assert hit is True
    assert val == {"cached": True}
    assert calls == []


def test_get_or_compute_persists_on_miss():
    """After miss+compute, a follow-up get must hit."""
    cache.get_or_compute("extract", "k", lambda: {"x": 1})
    val, hit = cache.get_or_compute("extract", "k", lambda: {"x": 99})
    assert hit is True
    assert val == {"x": 1}


def test_unicode_payload_roundtrip():
    """Cyrillic text must survive serialization (ensure_ascii=False)."""
    payload = {"quote": "Концепция миграционной политики"}
    cache.put("extract", "ru", payload)
    assert cache.get("extract", "ru") == payload


# ---------------------------------------------------------------------------
# invalidate / list_scope
# ---------------------------------------------------------------------------


def test_invalidate_removes_entry():
    cache.put("extract", "k", {})
    cache.invalidate("extract", "k")
    assert cache.get("extract", "k") is None


def test_invalidate_missing_is_noop():
    cache.invalidate("extract", "never-existed")  # no raise


def test_list_scope_returns_keys():
    cache.put("extract", "key-1", {})
    cache.put("extract", "key-2", {})
    cache.put("compare", "other", {})
    assert cache.list_scope("extract") == ["key-1", "key-2"]
    assert cache.list_scope("compare") == ["other"]


def test_list_scope_empty_when_nothing_cached():
    assert cache.list_scope("extract") == []
