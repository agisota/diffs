"""Tests for the cache + batch prune CLI (PR-5.4)."""
from __future__ import annotations

import os
import time
from pathlib import Path

from docdiffops.cli_prune import main, prune_batches, prune_cache


def _touch(p: Path, *, age_days: float = 0.0) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    if age_days > 0:
        ts = time.time() - age_days * 86400
        os.utime(p, (ts, ts))
    return p


def test_prune_cache_removes_only_old_entries(tmp_path):
    _touch(tmp_path / "cache" / "extract" / "old.json", age_days=40)
    _touch(tmp_path / "cache" / "extract" / "new.json", age_days=1)
    _touch(tmp_path / "cache" / "compare" / "older.json", age_days=60)
    cutoff = time.time() - 30 * 86400
    removed, kept = prune_cache(tmp_path, cutoff)
    assert removed == 2
    assert kept == 1
    assert not (tmp_path / "cache" / "extract" / "old.json").exists()
    assert (tmp_path / "cache" / "extract" / "new.json").exists()


def test_prune_cache_dry_run_does_not_delete(tmp_path):
    _touch(tmp_path / "cache" / "extract" / "old.json", age_days=40)
    cutoff = time.time() - 30 * 86400
    removed, _ = prune_cache(tmp_path, cutoff, dry_run=True)
    assert removed == 1
    assert (tmp_path / "cache" / "extract" / "old.json").exists()


def test_prune_cache_handles_missing_dir(tmp_path):
    removed, kept = prune_cache(tmp_path, time.time())
    assert removed == 0
    assert kept == 0


def test_prune_batches_removes_old_batches(tmp_path):
    old_batch = tmp_path / "batches" / "bat_old"
    new_batch = tmp_path / "batches" / "bat_new"
    _touch(old_batch / "state.json", age_days=40)
    _touch(new_batch / "state.json", age_days=1)
    cutoff = time.time() - 30 * 86400
    removed, kept = prune_batches(tmp_path, cutoff)
    assert removed == 1
    assert kept == 1
    assert not old_batch.exists()
    assert new_batch.exists()


def test_prune_batches_falls_back_to_dir_mtime(tmp_path):
    """Batch dir without state.json (corrupt/early-stage) uses dir mtime."""
    batch = tmp_path / "batches" / "bat_no_state"
    batch.mkdir(parents=True)
    ts = time.time() - 60 * 86400
    os.utime(batch, (ts, ts))
    cutoff = time.time() - 30 * 86400
    removed, _ = prune_batches(tmp_path, cutoff)
    assert removed == 1


def test_main_returns_zero_on_clean_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "30")
    rc = main(["--root", str(tmp_path), "--dry-run"])
    assert rc == 0


def test_main_rejects_invalid_days(tmp_path):
    rc = main(["--root", str(tmp_path), "--days", "0"])
    assert rc == 1


def test_main_cache_only_flag(tmp_path):
    _touch(tmp_path / "cache" / "extract" / "old.json", age_days=40)
    _touch(tmp_path / "batches" / "bat_old" / "state.json", age_days=40)
    rc = main(["--root", str(tmp_path), "--days", "30", "--cache-only"])
    assert rc == 0
    assert not (tmp_path / "cache" / "extract" / "old.json").exists()
    # Batch dir untouched.
    assert (tmp_path / "batches" / "bat_old").exists()
