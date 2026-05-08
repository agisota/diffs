from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .compare import build_pairs, compare_pair
from .executive import render_executive_md
from .extract import extract_any
from .normalize import convert_to_canonical_pdf
from .render_docx import render_track_changes_docx
from .render_pdf import render_pair_redgreen_pdf
from .render_xlsx import render_evidence_matrix
from .state import add_artifact, batch_dir, load_state, save_state
from .utils import now_ts, read_json, write_json, write_jsonl


def _doc_by_id(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {d["doc_id"]: d for d in state.get("documents", [])}


def _infer_doc_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".ppt", ".pptx"}:
        return "PRESENTATION"
    if ext in {".xls", ".xlsx", ".csv"}:
        return "TABLE"
    if ext in {".html", ".htm"}:
        return "WEB_DIGEST"
    # Default. User can override source_rank/doc_type in future config/API.
    return "OTHER"


def normalize_and_extract(batch_id: str, state: dict[str, Any], prefer_pdf_visual: bool = True) -> None:
    base = batch_dir(batch_id)
    for doc in state.get("documents", []):
        raw_path = base / doc["raw_path"]
        norm_dir = base / "normalized" / doc["doc_id"]
        ext_dir = base / "extracted"
        if not doc.get("doc_type"):
            doc["doc_type"] = _infer_doc_type(raw_path)
        if not doc.get("source_rank"):
            doc["source_rank"] = 3

        canonical_pdf = None
        if not doc.get("canonical_pdf"):
            canonical_pdf = convert_to_canonical_pdf(raw_path, norm_dir)
            if canonical_pdf:
                doc["canonical_pdf"] = str(canonical_pdf.relative_to(base))
        else:
            canonical_pdf = base / doc["canonical_pdf"]

        extracted_path = ext_dir / f"{doc['doc_id']}.json"
        if not extracted_path.exists():
            data = extract_any(raw_path, doc["doc_id"], canonical_pdf=canonical_pdf, prefer_pdf_visual=prefer_pdf_visual)
            data["raw_path"] = str(raw_path.relative_to(base))
            data["canonical_pdf"] = str(canonical_pdf.relative_to(base)) if canonical_pdf else None
            write_json(extracted_path, data)
        doc["extracted_json"] = str(extracted_path.relative_to(base))
        doc["block_count"] = len(read_json(extracted_path, {}).get("blocks", []))
        doc["status"] = "extracted"
    save_state(batch_id, state)


def run_all_pairs(batch_id: str, state: dict[str, Any], profile: str = "fast") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = batch_dir(batch_id)
    docs = state.get("documents", [])
    pairs = build_pairs(docs)
    state["pairs"] = pairs
    docs_map = _doc_by_id(state)
    all_events: list[dict[str, Any]] = []
    pair_summaries: list[dict[str, Any]] = []

    config = state.get("config") or {}
    q = config.get("quality_policy", {}) if isinstance(config.get("quality_policy"), dict) else {}
    same_threshold = int(q.get("same_threshold", 92))
    partial_threshold = int(q.get("partial_threshold", 78))

    for pair in pairs:
        lhs_doc = docs_map[pair["lhs_doc_id"]]
        rhs_doc = docs_map[pair["rhs_doc_id"]]
        lhs_ex = read_json(base / lhs_doc["extracted_json"], {})
        rhs_ex = read_json(base / rhs_doc["extracted_json"], {})
        lhs_blocks = lhs_ex.get("blocks", [])
        rhs_blocks = rhs_ex.get("blocks", [])
        events, summary = compare_pair(pair, lhs_doc, rhs_doc, lhs_blocks, rhs_blocks, same_threshold=same_threshold, partial_threshold=partial_threshold)

        pair_dir = base / "pairs" / pair["pair_id"]
        pair_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(pair_dir / "diff_events.jsonl", events)
        write_json(pair_dir / "pair_summary.json", summary)
        all_events.extend(events)
        pair_summaries.append(summary)

        # Pair synthetic DOCX redline report.
        docx_path = pair_dir / "track_changes.docx"
        render_track_changes_docx(docx_path, summary, events)
        add_artifact(state, "track_changes_docx", docx_path, f"Track changes {pair['pair_id']}")

        # Pair red/green PDF when both have canonical PDFs and there are material events.
        lhs_pdf = base / lhs_doc.get("canonical_pdf", "") if lhs_doc.get("canonical_pdf") else None
        rhs_pdf = base / rhs_doc.get("canonical_pdf", "") if rhs_doc.get("canonical_pdf") else None
        material_events = [e for e in events if e.get("status") in {"added", "deleted", "partial", "modified", "contradicts"}]
        if lhs_pdf and rhs_pdf and lhs_pdf.exists() and rhs_pdf.exists() and material_events:
            try:
                res = render_pair_redgreen_pdf(lhs_pdf, rhs_pdf, material_events, pair_dir, lhs_doc.get("filename", lhs_doc["doc_id"]), rhs_doc.get("filename", rhs_doc["doc_id"]))
                add_artifact(state, "redgreen_pdf", res["path"], f"Red/green PDF {pair['pair_id']}")
            except Exception as e:
                pair["pdf_render_error"] = str(e)

        save_state(batch_id, state)

    return all_events, pair_summaries


def render_global_reports(batch_id: str, state: dict[str, Any], all_events: list[dict[str, Any]], pair_summaries: list[dict[str, Any]]) -> None:
    base = batch_dir(batch_id)
    xlsx_path = base / "reports" / "evidence_matrix.xlsx"
    render_evidence_matrix(xlsx_path, state, all_events, pair_summaries)
    add_artifact(state, "evidence_xlsx", xlsx_path, "Evidence matrix")

    md_path = base / "reports" / "executive_diff.md"
    render_executive_md(md_path, state, all_events, pair_summaries)
    add_artifact(state, "executive_md", md_path, "Executive diff")

    # Machine-readable global exports.
    write_jsonl(base / "reports" / "diff_events_all.jsonl", all_events)
    write_json(base / "reports" / "pair_summaries.json", pair_summaries)
    add_artifact(state, "jsonl", base / "reports" / "diff_events_all.jsonl", "All diff events JSONL")
    add_artifact(state, "json", base / "reports" / "pair_summaries.json", "Pair summaries JSON")
    save_state(batch_id, state)


def run_batch(batch_id: str, profile: str = "fast") -> dict[str, Any]:
    state = load_state(batch_id)
    start = time.time()
    run = {"profile": profile, "started_at": now_ts(), "status": "running"}
    state.setdefault("runs", []).append(run)
    save_state(batch_id, state)

    try:
        normalize_and_extract(batch_id, state, prefer_pdf_visual=True)
        all_events, pair_summaries = run_all_pairs(batch_id, state, profile=profile)
        render_global_reports(batch_id, state, all_events, pair_summaries)
        state["metrics"] = {
            "time_to_report_sec": round(time.time() - start, 2),
            "documents": len(state.get("documents", [])),
            "pairs": len(pair_summaries),
            "events": len(all_events),
            "review_required": sum(1 for e in all_events if e.get("review_required")),
        }
        state["runs"][-1].update({"status": "done", "finished_at": now_ts(), "duration_sec": round(time.time() - start, 2)})
        save_state(batch_id, state)
        return state["metrics"]
    except Exception as e:
        state["runs"][-1].update({"status": "error", "finished_at": now_ts(), "error": str(e)})
        save_state(batch_id, state)
        raise
