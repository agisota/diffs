"""Read all v10 source artifacts into typed Python structures.

Single point of contact with ``migration_v10_out/``. Every other module
calls :func:`load_data` once and operates on the returned :class:`V10Data`
namedtuple. Validates control numbers (27/351/312, QA 12/12) so a bad bundle
is caught before any slide is rendered.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .theme import V8_STATUSES

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUNDLE_DIR = REPO_ROOT / "migration_v10_out"


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8-BOM CSV into a list of dicts."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class V10Data:
    """Frozen snapshot of the v10 bundle, ready for rendering."""

    # Core JSON
    bundle: dict[str, Any]
    delta: dict[str, Any]
    trend: dict[str, Any]
    qa: dict[str, Any]

    # Bundle CSVs
    documents: list[dict[str, str]]      # 27 rows
    pairs: list[dict[str, str]]          # 351 rows
    actions: list[dict[str, str]]        # 10 rows (FA-01..FA-10)

    # machine_appendix CSVs
    sources_registry: list[dict[str, str]]   # 27 rows (01_*)
    pair_matrix_long: list[dict[str, str]]   # 351 (02_*)
    theme_doc: list[dict[str, str]]          # 378 (03_*)
    theses: list[dict[str, str]]             # 87 (04_*)
    risks: list[dict[str, str]]              # 54 (05_*)
    review_queue: list[dict[str, str]]       # 103 (06_*)
    provenance: list[dict[str, str]]         # 112 (07_*)
    redgreen_meta: list[dict[str, str]]      # 10 (08_*)
    qa_csv: list[dict[str, str]]             # 8 (09_*)
    events_all: list[dict[str, str]]         # 312 (10_*)
    eaeu_appendix: list[dict[str, str]]      # 5 (11_*)
    ruid_appendix: list[dict[str, str]]      # 15 (12_*)
    invnzh_appendix: list[dict[str, str]]    # 11 (13_*)
    vciom_appendix: list[dict[str, str]]     # 12 (14_*)
    correlation_matrix: list[dict[str, str]] # 14×27
    coverage_heatmap: list[dict[str, str]]   # 14×27
    dependency_graph: list[dict[str, str]]   # 85 edges
    claim_provenance: list[dict[str, str]]   # 87 rows

    # Derived
    bundle_dir: Path
    readme_text: str = ""
    derived: dict[str, Any] = field(default_factory=dict)

    # --- Helpers -----------------------------------------------------------

    @property
    def control_numbers(self) -> dict[str, int]:
        return self.bundle.get("control_numbers", {})

    def status_distribution(self) -> dict[str, int]:
        """Count events by v8 status from events_all."""
        out = {s: 0 for s in V8_STATUSES}
        for ev in self.events_all:
            s = ev.get("status", "").strip()
            if s in out:
                out[s] += 1
        return out

    def doc_by_id(self, doc_id: str) -> dict[str, str] | None:
        for d in self.documents:
            if d.get("id") == doc_id:
                return d
        return None

    def doc_short(self, doc_id: str) -> str:
        d = self.doc_by_id(doc_id)
        if not d:
            return doc_id
        code = (d.get("code") or "").strip()
        return f"{doc_id} {code}" if code else doc_id

    def docs_by_rank(self) -> dict[int, list[dict[str, str]]]:
        out: dict[int, list[dict[str, str]]] = {1: [], 2: [], 3: []}
        for d in self.documents:
            try:
                r = int(d.get("rank") or 0)
            except ValueError:
                r = 0
            out.setdefault(r, []).append(d)
        return out

    def pairs_by_status(self) -> dict[str, int]:
        out = {s: 0 for s in V8_STATUSES}
        for p in self.pairs:
            s = p.get("v8_status", "").strip()
            if s in out:
                out[s] += 1
        return out

    def review_by_priority(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.review_queue:
            p = (r.get("priority") or "").strip() or "—"
            out[p] = out.get(p, 0) + 1
        return out

    def actions_by_severity(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self.actions:
            s = (a.get("severity") or "").strip() or "—"
            out[s] = out.get(s, 0) + 1
        return out

    def themes_distribution(self) -> dict[str, int]:
        """Count events per theme (theme_id label)."""
        out: dict[str, int] = {}
        for ev in self.events_all:
            t = (ev.get("theme") or "").strip() or "—"
            out[t] = out.get(t, 0) + 1
        return out


def load_data(bundle_dir: Path | str | None = None, *, validate: bool = True) -> V10Data:
    """Load the entire v10 bundle into memory.

    Args:
        bundle_dir: path to ``migration_v10_out/``; defaults to repo root.
        validate: if True, assert control numbers match the QA gate.

    Returns:
        A frozen :class:`V10Data` snapshot.
    """
    root = Path(bundle_dir) if bundle_dir else DEFAULT_BUNDLE_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"bundle_dir not found: {root}")

    b = root / "bundle"
    m = root / "machine_appendix"
    d = root / "delta"
    t = root / "trend"

    data = V10Data(
        bundle=_read_json(b / "bundle.json"),
        delta=_read_json(d / "delta.json"),
        trend=_read_json(t / "trend.json"),
        qa=_read_json(root / "qa_report.json"),
        documents=_read_csv(b / "documents.csv"),
        pairs=_read_csv(b / "pairs.csv"),
        actions=_read_csv(b / "actions.csv"),
        sources_registry=_read_csv(m / "01_реестр_источников.csv"),
        pair_matrix_long=_read_csv(m / "02_документ_документ.csv"),
        theme_doc=_read_csv(m / "03_тема_документ.csv"),
        theses=_read_csv(m / "04_тезисы_НПА.csv"),
        risks=_read_csv(m / "05_риски_и_противоречия.csv"),
        review_queue=_read_csv(m / "06_очередь_ручной_проверки.csv"),
        provenance=_read_csv(m / "07_provenance_downloaded_sources.csv"),
        redgreen_meta=_read_csv(m / "08_redgreen_diff_layer.csv"),
        qa_csv=_read_csv(m / "09_QA.csv"),
        events_all=_read_csv(m / "10_все_события.csv"),
        eaeu_appendix=_read_csv(m / "11_ЕАЭС.csv"),
        ruid_appendix=_read_csv(m / "12_ruID_ПП1510.csv"),
        invnzh_appendix=_read_csv(m / "13_ВНЖ_инвестор.csv"),
        vciom_appendix=_read_csv(m / "14_ВЦИОМ.csv"),
        correlation_matrix=_read_csv(m / "correlation_matrix.csv"),
        coverage_heatmap=_read_csv(m / "coverage_heatmap.csv"),
        dependency_graph=_read_csv(m / "dependency_graph.csv"),
        claim_provenance=_read_csv(m / "claim_provenance.csv"),
        bundle_dir=root,
        readme_text=(root / "README_v10.txt").read_text(encoding="utf-8"),
    )

    if validate:
        _validate(data)

    return data


def _validate(data: V10Data) -> None:
    """Sanity-check the loaded bundle against QA control numbers.

    Raises ``AssertionError`` on mismatch — caller must abort the build.
    """
    cn = data.control_numbers
    assert cn.get("documents") == 27, f"docs={cn.get('documents')} (expected 27)"
    assert cn.get("pairs") == 351, f"pairs={cn.get('pairs')} (expected 351)"
    assert cn.get("events") == 312, f"events={cn.get('events')} (expected 312)"
    assert len(data.documents) == 27, f"documents.csv rows={len(data.documents)}"
    assert len(data.pairs) == 351, f"pairs.csv rows={len(data.pairs)}"
    assert len(data.events_all) == 312, f"events rows={len(data.events_all)}"
    assert len(data.review_queue) == 103, f"review_queue rows={len(data.review_queue)}"
    assert data.qa.get("verdict") == "PASS", f"QA verdict={data.qa.get('verdict')}"
    assert data.qa.get("passed") == 12, f"QA passed={data.qa.get('passed')}"
