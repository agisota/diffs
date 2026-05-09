"""Tests for forensic_csv exports — pairs / docs / actions / changes / trend."""
from __future__ import annotations

from pathlib import Path

from docdiffops.forensic import build_forensic_bundle
from docdiffops.forensic_actions import apply_actions_to_bundle
from docdiffops.forensic_csv import (
    export_actions_csv,
    export_distribution_diff_csv,
    export_documents_csv,
    export_pairs_csv,
    export_status_changes_csv,
    export_trend_timeline_csv,
)
from docdiffops.forensic_delta import compare_bundles
from docdiffops.forensic_trend import compute_trend


def _bundle(corpus: str | None = None) -> dict:
    docs = [
        {"id": "D01", "code": "FZ_115", "rank": 1, "title": "115-ФЗ", "type": "law"},
        {"id": "D02", "code": "FZ_109", "rank": 1, "title": "109-ФЗ", "type": "law"},
    ]
    pairs = [{"id": "P1", "left": "D01", "right": "D02",
              "events": [{"status": "partial",
                          "explanation_short": "Расхождение в норме"}]}]
    b = build_forensic_bundle(documents=docs, pairs=pairs, events=[],
                              amendment_graph={})
    return apply_actions_to_bundle(b, corpus=corpus)


def _read(path: Path) -> str:
    # CSVs are written as utf-8-sig — decode the BOM transparently.
    return path.read_text(encoding="utf-8-sig")


def test_export_pairs_csv_has_russian_headers_and_status_label(tmp_path: Path):
    out = tmp_path / "pairs.csv"
    export_pairs_csv(_bundle(), out)
    txt = _read(out)
    assert "ИД пары" in txt
    assert "Статус (русский)" in txt
    assert "Частичное совпадение" in txt


def test_export_pairs_csv_first_row_starts_with_bom(tmp_path: Path):
    out = tmp_path / "pairs.csv"
    export_pairs_csv(_bundle(), out)
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "Excel-friendly UTF-8 BOM missing"


def test_export_documents_csv_lists_all_docs(tmp_path: Path):
    out = tmp_path / "docs.csv"
    export_documents_csv(_bundle(), out)
    txt = _read(out)
    assert "FZ_115" in txt
    assert "FZ_109" in txt


def test_export_actions_csv_includes_raci_columns(tmp_path: Path):
    out = tmp_path / "actions.csv"
    export_actions_csv(_bundle(corpus="migration_v8"), out)
    txt = _read(out)
    # Header includes RACI columns
    first_line = txt.splitlines()[0]
    assert "R" in first_line.split(",")
    assert "A" in first_line.split(",")
    # Body includes at least one FA-XX row
    assert "FA-" in txt


def test_export_status_changes_csv_has_direction_translation(tmp_path: Path):
    docs = [{"id": "D1", "code": "C1", "rank": 1, "title": "t", "type": "law"},
            {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"}]
    old = build_forensic_bundle(documents=docs,
                                pairs=[{"id": "P1", "left": "D1", "right": "D2",
                                        "events": [{"status": "contradicts"}]}],
                                events=[], amendment_graph={})
    new = build_forensic_bundle(documents=docs,
                                pairs=[{"id": "P1", "left": "D1", "right": "D2",
                                        "events": [{"status": "same"}]}],
                                events=[], amendment_graph={})
    delta = compare_bundles(old, new)
    out = tmp_path / "changes.csv"
    export_status_changes_csv(delta, out)
    txt = _read(out)
    assert "Улучшилось" in txt
    assert "Противоречие" in txt
    assert "Совпадение" in txt


def test_export_distribution_diff_csv_signed_delta(tmp_path: Path):
    docs = [{"id": "D1", "code": "C1", "rank": 1, "title": "t", "type": "law"},
            {"id": "D2", "code": "C2", "rank": 1, "title": "t2", "type": "law"}]
    old = build_forensic_bundle(documents=docs,
                                pairs=[{"id": "P1", "left": "D1", "right": "D2",
                                        "events": [{"status": "contradicts"}]}],
                                events=[], amendment_graph={})
    new = build_forensic_bundle(documents=docs,
                                pairs=[{"id": "P1", "left": "D1", "right": "D2",
                                        "events": [{"status": "same"}]}],
                                events=[], amendment_graph={})
    delta = compare_bundles(old, new)
    out = tmp_path / "dist.csv"
    export_distribution_diff_csv(delta, out)
    txt = _read(out)
    # contradiction goes down by 1; match goes up by 1 → signs preserved
    assert "+1" in txt
    assert "-1" in txt


def test_export_trend_timeline_csv_has_match_share_column(tmp_path: Path):
    b = _bundle()
    trend = compute_trend([b, b])
    out = tmp_path / "trend.csv"
    export_trend_timeline_csv(trend, out)
    txt = _read(out)
    assert "Доля совпадений (%)" in txt
    # Two timeline rows after header
    lines = [l for l in txt.splitlines() if l.strip()]
    assert len(lines) == 3  # header + 2 rows
