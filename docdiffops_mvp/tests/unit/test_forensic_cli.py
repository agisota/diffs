"""CLI tests for forensic_cli rebuild and compare subcommands."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_cli import main


def _write_bundle(path: Path) -> Path:
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    pairs = [{"id": "P1", "left": "D1", "right": "D2",
              "events": [{"status": "same"}]}]
    b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    path.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return path


def test_cli_rebuild_creates_all_artifacts(tmp_path: Path):
    bundle_file = _write_bundle(tmp_path / "bundle.json")
    out_dir = tmp_path / "out"
    rc = main(["rebuild", str(bundle_file), "--out", str(out_dir)])
    assert rc == 0
    assert (out_dir / "bundle.json").exists()
    assert (out_dir / "forensic_v8.xlsx").exists()
    assert (out_dir / "forensic_v8_explanatory.docx").exists()
    assert (out_dir / "forensic_v8_redgreen.docx").exists()
    assert (out_dir / "forensic_v8_summary.pdf").exists()


def test_cli_rebuild_with_actions_includes_catalogue(tmp_path: Path):
    bundle_file = _write_bundle(tmp_path / "bundle.json")
    out_dir = tmp_path / "out"
    rc = main(["rebuild", str(bundle_file), "--out", str(out_dir), "--with-actions"])
    assert rc == 0
    rebuilt = json.loads((out_dir / "bundle.json").read_text(encoding="utf-8"))
    assert "actions_catalogue" in rebuilt


def test_cli_rebuild_without_actions_omits_catalogue(tmp_path: Path):
    bundle_file = _write_bundle(tmp_path / "bundle.json")
    out_dir = tmp_path / "out"
    rc = main(["rebuild", str(bundle_file), "--out", str(out_dir)])
    assert rc == 0
    rebuilt = json.loads((out_dir / "bundle.json").read_text(encoding="utf-8"))
    assert "actions_catalogue" not in rebuilt


def test_cli_compare_creates_delta_json(tmp_path: Path):
    old_file = _write_bundle(tmp_path / "old.json")
    # New bundle has a status change on P1
    docs = [
        {"id": "D1", "code": "C1", "rank": 1, "title": "t1", "type": "law"},
        {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"},
    ]
    pairs = [{"id": "P1", "left": "D1", "right": "D2",
              "events": [{"status": "contradicts"}]}]
    new_b = build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={})
    new_file = tmp_path / "new.json"
    new_file.write_text(json.dumps(new_b, ensure_ascii=False), encoding="utf-8")

    out_file = tmp_path / "delta.json"
    rc = main(["compare", str(old_file), str(new_file), "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    delta = json.loads(out_file.read_text(encoding="utf-8"))
    assert delta["schema_version"] == "v8-delta"
    assert delta["control_numbers"]["pairs_changed"] == 1


def test_cli_invalid_subcommand_exits_nonzero(tmp_path: Path):
    with pytest.raises(SystemExit) as exc_info:
        main(["invalid-command"])
    assert exc_info.value.code != 0


def test_cli_output_dir_created_if_missing(tmp_path: Path):
    bundle_file = _write_bundle(tmp_path / "bundle.json")
    out_dir = tmp_path / "nested" / "deep" / "out"
    assert not out_dir.exists()
    rc = main(["rebuild", str(bundle_file), "--out", str(out_dir)])
    assert rc == 0
    assert out_dir.exists()
