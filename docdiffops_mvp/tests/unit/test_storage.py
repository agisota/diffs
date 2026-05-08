"""Unit tests for the Storage abstraction (PR-1.4 FS backend)."""
from __future__ import annotations

import hashlib

import pytest

from docdiffops.storage import FSStorage, Storage, get_storage
from docdiffops.storage.backend import reset_storage_for_tests


@pytest.fixture
def fs(tmp_path):
    return FSStorage(root=tmp_path)


# ---------------------------------------------------------------------------
# put_bytes / get_bytes round trip
# ---------------------------------------------------------------------------


def test_put_and_get_round_trip(fs):
    data = b"hello world"
    sha = fs.put_bytes("batches/abc/raw/foo.txt", data)
    assert sha == hashlib.sha256(data).hexdigest()
    assert fs.get_bytes("batches/abc/raw/foo.txt") == data


def test_put_creates_parent_dirs(fs):
    fs.put_bytes("a/b/c/d/e/f.bin", b"x")
    assert fs.exists("a/b/c/d/e/f.bin")


def test_put_overwrites_atomically(fs):
    fs.put_bytes("k", b"first")
    fs.put_bytes("k", b"second")
    assert fs.get_bytes("k") == b"second"


def test_put_then_stat_returns_size_and_sha(fs):
    data = b"DocDiffOps"
    fs.put_bytes("k.bin", data)
    st = fs.stat("k.bin")
    assert st["size"] == len(data)
    assert st["sha256"] == hashlib.sha256(data).hexdigest()
    assert st["modified_at"].endswith("Z")


# ---------------------------------------------------------------------------
# exists / delete
# ---------------------------------------------------------------------------


def test_exists_false_for_missing(fs):
    assert fs.exists("nope/missing.txt") is False


def test_delete_removes_file(fs):
    fs.put_bytes("doomed.txt", b"")
    fs.delete("doomed.txt")
    assert fs.exists("doomed.txt") is False


def test_delete_missing_is_noop(fs):
    fs.delete("never-existed")  # must not raise


# ---------------------------------------------------------------------------
# list_prefix
# ---------------------------------------------------------------------------


def test_list_prefix_returns_sorted_keys(fs):
    fs.put_bytes("batches/a/raw/x.pdf", b"x")
    fs.put_bytes("batches/a/raw/y.pdf", b"y")
    fs.put_bytes("batches/a/reports/z.xlsx", b"z")
    fs.put_bytes("batches/b/raw/x.pdf", b"x")

    keys = fs.list_prefix("batches/a")
    assert keys == [
        "batches/a/raw/x.pdf",
        "batches/a/raw/y.pdf",
        "batches/a/reports/z.xlsx",
    ]


def test_list_prefix_empty_when_missing(fs):
    assert fs.list_prefix("does/not/exist") == []


def test_list_prefix_empty_string_returns_all(fs):
    fs.put_bytes("a", b"")
    fs.put_bytes("nested/b", b"")
    assert fs.list_prefix("") == ["a", "nested/b"]


def test_list_prefix_targeting_a_file_returns_just_that_key(fs):
    fs.put_bytes("solo.bin", b"")
    assert fs.list_prefix("solo.bin") == ["solo.bin"]


# ---------------------------------------------------------------------------
# Safety: invalid keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    ["", "/abs/path", "../escape", "ok/../bad"],
)
def test_invalid_keys_rejected(fs, bad_key):
    with pytest.raises(ValueError):
        fs.put_bytes(bad_key, b"x")


# ---------------------------------------------------------------------------
# Presigned URL — None for FS
# ---------------------------------------------------------------------------


def test_fs_presigned_url_is_none(fs):
    fs.put_bytes("k", b"")
    assert fs.presigned_url("k") is None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_get_storage_returns_fs_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.setattr("docdiffops.storage.backend.DATA_DIR", tmp_path)
    reset_storage_for_tests()
    s = get_storage()
    assert isinstance(s, FSStorage)


def test_get_storage_explicit_fs(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setattr("docdiffops.storage.backend.DATA_DIR", tmp_path)
    reset_storage_for_tests()
    assert isinstance(get_storage(), FSStorage)


def test_get_storage_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "azureblob")
    reset_storage_for_tests()
    with pytest.raises(ValueError):
        get_storage()


def test_get_storage_caches_instance(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setattr("docdiffops.storage.backend.DATA_DIR", tmp_path)
    reset_storage_for_tests()
    a = get_storage()
    b = get_storage()
    assert a is b


# ---------------------------------------------------------------------------
# Storage protocol structural conformance
# ---------------------------------------------------------------------------


def test_fs_storage_satisfies_protocol(fs):
    # Protocol check is structural in Python; this just exercises the
    # methods to confirm signature shape.
    assert isinstance(fs, FSStorage)
    fs.put_bytes("p", b"x")
    assert isinstance(fs.get_bytes("p"), bytes)
    assert isinstance(fs.exists("p"), bool)
    assert isinstance(fs.list_prefix(""), list)
    assert isinstance(fs.stat("p"), dict)
    assert fs.presigned_url("p") is None
    fs.delete("p")
    s: Storage = fs  # type checker assertion
    del s
