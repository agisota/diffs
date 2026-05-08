"""Unit tests for the PR-1.3 read cutover wiring in ``docdiffops.state``.

The two new toggles control:

- ``READ_FROM_DB`` — ``load_state``/``list_batches`` prefer the DB when on
- ``WRITE_JSON_STATE`` — ``save_state`` no-ops when off

These tests stub the repository so they can run without SQLAlchemy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from docdiffops import state as state_module


class _StubRepo:
    """Minimal fake matching the shape ``state._get_read_repo`` returns."""

    def __init__(self, state_dict=None, raises=False, batches=None):
        self._state = state_dict
        self._raises = raises
        self._batches = batches or []

    def to_state_dict(self, batch_id):
        if self._raises:
            raise RuntimeError("boom")
        return self._state

    def list_all_batches(self):
        if self._raises:
            raise RuntimeError("boom")
        return list(self._batches)


@pytest.fixture()
def tmp_data(monkeypatch, tmp_path) -> Path:
    """Point ``state.DATA_DIR`` at a per-test temp directory."""
    monkeypatch.setattr(state_module, "DATA_DIR", tmp_path)
    return tmp_path


def _write_json_state_file(tmp: Path, batch_id: str, payload: dict) -> None:
    p = tmp / "batches" / batch_id / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# load_state
# ---------------------------------------------------------------------------


def test_load_state_prefers_db_when_flag_on(tmp_data, monkeypatch):
    bid = "bat_db"
    _write_json_state_file(tmp_data, bid, {"batch_id": bid, "title": "JSON title",
                                            "config": {"k": "v"}, "runs": [{"i": 1}],
                                            "metrics": {"events": 0},
                                            "documents": [], "pairs": [],
                                            "artifacts": []})
    db_dict = {"batch_id": bid, "title": "DB title", "status": "created",
               "created_at": None, "updated_at": None, "config": {}, "runs": [],
               "metrics": {}, "documents": [], "pairs": [], "pair_runs": [],
               "diff_events": [], "artifacts": []}
    monkeypatch.setenv("READ_FROM_DB", "true")
    monkeypatch.setattr(state_module, "_get_read_repo",
                        lambda: _StubRepo(state_dict=db_dict))

    out = state_module.load_state(bid)
    # Title should come from DB; JSON-only fields backfilled.
    assert out["title"] == "DB title"
    assert out["config"] == {"k": "v"}  # merged in from JSON
    assert out["runs"] == [{"i": 1}]
    assert out["metrics"] == {"events": 0}


def test_load_state_falls_back_to_json_when_db_returns_none(tmp_data, monkeypatch):
    bid = "bat_fallback"
    _write_json_state_file(tmp_data, bid, {"batch_id": bid, "title": "JSON title",
                                            "documents": [], "pairs": [],
                                            "artifacts": []})
    monkeypatch.setenv("READ_FROM_DB", "true")
    monkeypatch.setattr(state_module, "_get_read_repo",
                        lambda: _StubRepo(state_dict=None))

    out = state_module.load_state(bid)
    assert out["title"] == "JSON title"


def test_load_state_falls_back_when_db_raises(tmp_data, monkeypatch):
    bid = "bat_raise"
    _write_json_state_file(tmp_data, bid, {"batch_id": bid, "title": "JSON",
                                            "documents": [], "pairs": [],
                                            "artifacts": []})
    monkeypatch.setenv("READ_FROM_DB", "true")
    monkeypatch.setattr(state_module, "_get_read_repo",
                        lambda: _StubRepo(raises=True))
    out = state_module.load_state(bid)
    assert out["title"] == "JSON"


def test_load_state_uses_json_when_flag_off(tmp_data, monkeypatch):
    bid = "bat_off"
    _write_json_state_file(tmp_data, bid, {"batch_id": bid, "title": "JSON",
                                            "documents": [], "pairs": [],
                                            "artifacts": []})
    monkeypatch.setenv("READ_FROM_DB", "false")
    # Even if a repo *would* be available, READ_FROM_DB=false short-circuits.
    out = state_module.load_state(bid)
    assert out["title"] == "JSON"


def test_load_state_raises_when_neither_db_nor_json(tmp_data, monkeypatch):
    monkeypatch.setenv("READ_FROM_DB", "true")
    monkeypatch.setattr(state_module, "_get_read_repo",
                        lambda: _StubRepo(state_dict=None))
    with pytest.raises(FileNotFoundError):
        state_module.load_state("bat_missing")


def test_load_json_only_helper(tmp_data):
    bid = "bat_jsononly"
    _write_json_state_file(tmp_data, bid, {"batch_id": bid, "title": "raw"})
    s = state_module._load_json_only(bid)
    assert s["title"] == "raw"


# ---------------------------------------------------------------------------
# list_batches
# ---------------------------------------------------------------------------


def test_list_batches_uses_db_when_flag_on(tmp_data, monkeypatch):
    db_rows = [{"batch_id": "bat_a", "title": "from-db", "documents_count": 0,
                "pair_runs_count": 0, "diff_events_count": 0}]
    monkeypatch.setenv("READ_FROM_DB", "true")
    monkeypatch.setattr(state_module, "_get_read_repo",
                        lambda: _StubRepo(batches=db_rows))
    out = state_module.list_batches()
    assert len(out) == 1
    assert out[0]["batch_id"] == "bat_a"


def test_list_batches_falls_back_to_json_when_db_empty(tmp_data, monkeypatch):
    _write_json_state_file(tmp_data, "bat_x", {"batch_id": "bat_x",
                                                "title": "json-x",
                                                "documents": [{"doc_id": "d"}],
                                                "pairs": []})
    monkeypatch.setenv("READ_FROM_DB", "true")
    monkeypatch.setattr(state_module, "_get_read_repo",
                        lambda: _StubRepo(batches=[]))
    out = state_module.list_batches()
    assert any(r["batch_id"] == "bat_x" for r in out)


# ---------------------------------------------------------------------------
# save_state respects WRITE_JSON_STATE
# ---------------------------------------------------------------------------


def test_save_state_writes_json_by_default(tmp_data, monkeypatch):
    monkeypatch.delenv("WRITE_JSON_STATE", raising=False)
    state = {"batch_id": "bat_w", "title": "t"}
    state_module.save_state("bat_w", state)
    assert (tmp_data / "batches" / "bat_w" / "state.json").exists()


def test_save_state_skips_json_when_flag_off(tmp_data, monkeypatch):
    monkeypatch.setenv("WRITE_JSON_STATE", "false")
    state = {"batch_id": "bat_n", "title": "t"}
    state_module.save_state("bat_n", state)
    assert not (tmp_data / "batches" / "bat_n" / "state.json").exists()
