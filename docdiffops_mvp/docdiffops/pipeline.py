from __future__ import annotations

import logging
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from . import cache
from .compare import build_pairs, compare_pair
from .legal import (
    chunk_text as legal_chunk_text,
    claim_validation_events,
    legal_structural_diff,
    llm_pair_diff,
    llm_pair_diff_enabled,
)
from .legal.cross_pair import cluster_events
from .legal.llm_pair_diff import llm_pair_summary
from .legal.pair_score import pair_similarity_score, score_band
from .executive import render_executive_md
from .extract import extract_any
from .normalize import convert_to_canonical_pdf
from .render_docx import render_track_changes_docx
from .render_pdf import render_pair_redgreen_pdf
from .render_xlsx import render_evidence_matrix
from .state import add_artifact, batch_dir, load_state, save_state
from .utils import now_ts, read_json, stable_id, write_json, write_jsonl

logger = logging.getLogger(__name__)

# Placeholder versioning constants for PR-1.2; the formal definitions land
# in PR-1.6 alongside the cache key work. The DB requires non-null values
# on document_versions.extractor_version and pair_runs.comparator_version
# so we pin sensible strings here that PR-1.6 can replace.
from .settings import COMPARATOR_VERSION, EXTRACTOR_VERSION  # PR-1.6: single source of truth

# Repo wiring choice (PR-1.2): pipeline.run_batch instantiates ONE
# BatchRepository and threads it through to state.py and to the per-stage
# helpers. state.py also lazily builds its own repo when none is passed
# (used by the upload path in main.py); pipeline always passes its
# instance so a single run_batch call shares the same repo object.


def _attach_pair_score(summary: dict[str, Any], events: list[dict[str, Any]]) -> None:
    """Attach a single 0-100 similarity score + band label to ``summary``."""
    score = pair_similarity_score(events)
    summary["score_pct"] = score
    summary["score_band"] = score_band(score)


def _refresh_status_counts(summary: dict[str, Any], events: list[dict[str, Any]]) -> None:
    """Re-derive per-status counts in ``summary`` from ``events``.

    The fuzzy comparator pre-populated counts in compare.compare_pair;
    when llm_pair_diff replaces those events the counts go stale, so
    we recompute the canonical fields the renderers expect.
    """
    sev = Counter((e.get("severity") or "low").lower() for e in events)
    stat = Counter((e.get("status") or "").lower() for e in events)
    summary["events_total"] = len(events)
    summary["high_count"] = sev.get("high", 0)
    summary["medium_count"] = sev.get("medium", 0)
    summary["low_count"] = sev.get("low", 0)
    summary["same_count"] = stat.get("same", 0)
    summary["partial_count"] = stat.get("partial", 0)
    summary["modified_count"] = stat.get("modified", 0)
    summary["added_count"] = stat.get("added", 0)
    summary["deleted_count"] = stat.get("deleted", 0)
    summary["contradicts_count"] = stat.get("contradicts", 0)
    summary["review_required_count"] = sum(1 for e in events if e.get("review_required"))


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


def _doc_version_id_for(doc: dict[str, Any]) -> str:
    """Stable id for a document version row in the DB.

    Mirrors ``BatchRepository._document_version_id`` so callers can refer
    to the version by id without a separate lookup.
    """
    return "dv_" + stable_id(doc["doc_id"], "1", EXTRACTOR_VERSION, n=20)


def _safe(call_label: str, fn, *args, **kwargs) -> Any | None:
    """Run a DB call, log+swallow on failure (JSON write is authoritative)."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning("DB dual-write failed (%s): %s", call_label, e)
        return None


def normalize_and_extract(
    batch_id: str,
    state: dict[str, Any],
    prefer_pdf_visual: bool = True,
    repo: Any | None = None,
) -> None:
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
            # PR-1.6: content-addressed cache keyed by sha256 + EXTRACTOR_VERSION.
            # Two batches uploading the same PDF share the parsed result; bumping
            # EXTRACTOR_VERSION invalidates every cached extract automatically.
            def _do_extract() -> dict[str, Any]:
                d = extract_any(
                    raw_path, doc["doc_id"],
                    canonical_pdf=canonical_pdf,
                    prefer_pdf_visual=prefer_pdf_visual,
                )
                d["raw_path"] = str(raw_path.relative_to(base))
                d["canonical_pdf"] = str(canonical_pdf.relative_to(base)) if canonical_pdf else None
                return d

            ckey = cache.extract_key(doc["sha256"])
            data, hit = cache.get_or_compute("extract", ckey, _do_extract)
            doc["cache_extract_hit"] = hit
            write_json(extracted_path, data)
        doc["extracted_json"] = str(extracted_path.relative_to(base))
        doc["block_count"] = len(read_json(extracted_path, {}).get("blocks", []))
        doc["status"] = "extracted"

        # Dual-write: register the document and a document_version row so
        # downstream PairRun rows have FK targets. Idempotent on retry.
        if repo is not None:
            _safe(
                "add_document",
                repo.add_document,
                batch_id=batch_id,
                doc_id=doc["doc_id"],
                filename=doc.get("filename") or Path(doc["raw_path"]).name,
                sha256=doc["sha256"],
                extension=doc.get("ext"),
                source_rank=int(doc.get("source_rank") or 3),
                doc_type=doc.get("doc_type"),
                source_url=doc.get("source_url"),
            )
            _safe(
                "add_document_version",
                repo.add_document_version,
                document_id=doc["doc_id"],
                version=1,
                sha256=doc["sha256"],
                normalized_path=doc.get("canonical_pdf"),
                extracted_path=doc.get("extracted_json"),
                extractor_version=EXTRACTOR_VERSION,
            )
    save_state(batch_id, state)


def run_all_pairs(
    batch_id: str,
    state: dict[str, Any],
    profile: str = "fast",
    repo: Any | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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

        # Dual-write: pair_run row + status transitions + diff_event rows.
        if repo is not None:
            _safe(
                "add_pair_run",
                repo.add_pair_run,
                batch_id=batch_id,
                pair_id=pair["pair_id"],
                lhs_doc_version_id=_doc_version_id_for(lhs_doc),
                rhs_doc_version_id=_doc_version_id_for(rhs_doc),
                comparator_version=COMPARATOR_VERSION,
            )
            _safe(
                "update_pair_run_status",
                repo.update_pair_run_status,
                pair["pair_id"],
                "running",
            )

        # PR-1.6: cache the compare result keyed by (lhs_sha, rhs_sha) +
        # COMPARATOR_VERSION. Order-independent so swapping LHS/RHS hits.
        def _do_compare() -> dict[str, Any]:
            ev, sm = compare_pair(
                pair, lhs_doc, rhs_doc, lhs_blocks, rhs_blocks,
                same_threshold=same_threshold, partial_threshold=partial_threshold,
            )
            return {"events": ev, "summary": sm}

        ckey = cache.compare_key(lhs_doc["sha256"], rhs_doc["sha256"])
        bundle, hit = cache.get_or_compute("compare", ckey, _do_compare)
        events = bundle["events"]
        summary = bundle["summary"]
        summary["cache_hit"] = hit

        # PR-5.7: when the LLM pair-diff is active, replace the fuzzy
        # block_semantic_diff event noise with a curated semantic list.
        # KEEP_FUZZY_WITH_LLM_PAIR_DIFF=true retains both layers.
        # When LLM returns zero events (truncation, transport error,
        # empty parse), we still drop the fuzzy noise and emit a single
        # synthetic ``llm_unavailable`` placeholder so reviewers see a
        # clean signal instead of hundreds of token-overlap rows.
        if llm_pair_diff_enabled():
            try:
                llm_events = llm_pair_diff(pair, lhs_doc, rhs_doc, lhs_blocks, rhs_blocks)
            except Exception as e:
                logger.warning("llm_pair_diff failed for %s: %s", pair.get("pair_id"), e)
                llm_events = []
            keep_fuzzy = os.getenv("KEEP_FUZZY_WITH_LLM_PAIR_DIFF", "false").lower() == "true"
            if llm_events:
                if not keep_fuzzy:
                    events = list(llm_events)
                else:
                    events.extend(llm_events)
                summary["llm_pair_diff_events"] = len(llm_events)
                summary["events_total"] = len(events)
                _refresh_status_counts(summary, events)
            # Per-pair narrative (one-line LLM summary), best-effort.
            if os.getenv("LLM_PAIR_SUMMARY_ENABLED", "true").lower() != "false":
                try:
                    narrative = llm_pair_summary(pair, lhs_doc, rhs_doc, lhs_blocks, rhs_blocks)
                    if narrative:
                        summary["narrative"] = narrative
                except Exception as e:
                    logger.warning("llm_pair_summary failed for %s: %s", pair.get("pair_id"), e)

            if not llm_events and not keep_fuzzy:
                # Drop fuzzy noise; emit one placeholder event flagging
                # the pair for manual review so the absence is visible.
                placeholder = {
                    "event_id": "evt_llm_failed_" + (pair.get("pair_id") or "?")[-12:],
                    "pair_id": pair.get("pair_id"),
                    "comparison_type": "llm_unavailable",
                    "status": "manual_review",
                    "severity": "medium",
                    "score": None,
                    "confidence": 0.0,
                    "review_required": True,
                    "lhs_doc_id": lhs_doc.get("doc_id"),
                    "rhs_doc_id": rhs_doc.get("doc_id"),
                    "topic": "LLM-сравнение не удалось",
                    "lhs": {"doc_id": lhs_doc.get("doc_id"), "page_no": None, "block_id": None, "bbox": None, "quote": None},
                    "rhs": {"doc_id": rhs_doc.get("doc_id"), "page_no": None, "block_id": None, "bbox": None, "quote": None},
                    "explanation_short": "Семантический LLM-сравниватель не вернул валидные события для этой пары. Перезапустите с другой моделью (LLM_PAIR_DIFF_MODEL) или включите fuzzy fallback (KEEP_FUZZY_WITH_LLM_PAIR_DIFF=true).",
                }
                events = [placeholder]
                summary["llm_pair_diff_events"] = 0
                summary["llm_unavailable"] = True
                summary["events_total"] = 1
                _refresh_status_counts(summary, events)

        # PR-3.3 / PR-3.6: when both sides have a structurable doc_type,
        # ALSO emit legal_structural_diff events on top of the fuzzy ones.
        # The two layers are complementary: fuzzy catches block-level
        # changes; structural anchors a status to the article/section
        # number itself. apply_rank_gate is folded inside the comparator.
        STRUCTURABLE = {"LEGAL_NPA", "LEGAL_CONCEPT", "GOV_PLAN"}
        if (lhs_doc.get("doc_type") in STRUCTURABLE) and (rhs_doc.get("doc_type") in STRUCTURABLE):
            try:
                lhs_text = "\n".join(b.get("text", "") for b in lhs_blocks)
                rhs_text = "\n".join(b.get("text", "") for b in rhs_blocks)
                lhs_chunks = legal_chunk_text(lhs_doc.get("doc_type"), lhs_text, doc_id=lhs_doc["doc_id"])
                rhs_chunks = legal_chunk_text(rhs_doc.get("doc_type"), rhs_text, doc_id=rhs_doc["doc_id"])
                legal_events = legal_structural_diff(
                    pair, lhs_doc, rhs_doc, lhs_chunks, rhs_chunks
                )
                events.extend(legal_events)
                summary["legal_events"] = len(legal_events)
                summary["events_total"] = len(events)
            except Exception as e:
                logger.warning("legal_structural_diff failed for pair %s: %s", pair.get("pair_id"), e)

        # PR-3.5: claim validation for analytics ↔ NPA pairs.
        # When one side is rank-3 (analytics/presentation/blog) and the
        # other is rank-1 (official NPA/Concept), extract assertive
        # claims from the analytics side and validate against the NPA's
        # structural chunks. Brief §13: rank-3 cannot refute rank-1 —
        # the rank_gate inside the comparator enforces this.
        lhs_rank = int(lhs_doc.get("source_rank") or 3)
        rhs_rank = int(rhs_doc.get("source_rank") or 3)
        analytics, npa, analytics_blocks = None, None, None
        if lhs_rank == 3 and rhs_rank == 1:
            analytics, npa, analytics_blocks = lhs_doc, rhs_doc, lhs_blocks
        elif rhs_rank == 3 and lhs_rank == 1:
            analytics, npa, analytics_blocks = rhs_doc, lhs_doc, rhs_blocks
        if analytics is not None and npa is not None:
            try:
                npa_text = "\n".join(
                    b.get("text", "")
                    for b in (rhs_blocks if npa is rhs_doc else lhs_blocks)
                )
                npa_chunks = legal_chunk_text(
                    npa.get("doc_type"), npa_text, doc_id=npa["doc_id"]
                )
                cv_events = claim_validation_events(
                    pair, analytics, npa, analytics_blocks, npa_chunks
                )
                events.extend(cv_events)
                summary["claim_validation_events"] = len(cv_events)
                summary["events_total"] = len(events)
            except Exception as e:
                logger.warning("claim_validation failed for pair %s: %s", pair.get("pair_id"), e)

        pair_dir = base / "pairs" / pair["pair_id"]
        pair_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(pair_dir / "diff_events.jsonl", events)
        write_json(pair_dir / "pair_summary.json", summary)
        # Compute per-pair similarity score from final event list.
        _attach_pair_score(summary, events)

        all_events.extend(events)
        pair_summaries.append(summary)

        # Dual-write each event row to Postgres.
        if repo is not None:
            for ev in events:
                lhs_ev = ev.get("lhs") or {}
                rhs_ev = ev.get("rhs") or {}
                _safe(
                    "add_diff_event",
                    repo.add_diff_event,
                    event_id=ev["event_id"],
                    pair_run_id=ev["pair_id"],
                    comparison_type=ev.get("comparison_type") or "block_semantic_diff",
                    status=ev["status"],
                    severity=ev.get("severity") or "low",
                    confidence=ev.get("confidence"),
                    lhs_doc_id=lhs_ev.get("doc_id"),
                    lhs_page=lhs_ev.get("page_no"),
                    lhs_block_id=lhs_ev.get("block_id"),
                    lhs_bbox=lhs_ev.get("bbox") if isinstance(lhs_ev.get("bbox"), dict) else None,
                    lhs_quote=lhs_ev.get("quote"),
                    rhs_doc_id=rhs_ev.get("doc_id"),
                    rhs_page=rhs_ev.get("page_no"),
                    rhs_block_id=rhs_ev.get("block_id"),
                    rhs_bbox=rhs_ev.get("bbox") if isinstance(rhs_ev.get("bbox"), dict) else None,
                    rhs_quote=rhs_ev.get("quote"),
                    explanation_short=ev.get("explanation_short"),
                    review_required=bool(ev.get("review_required")),
                )
            _safe(
                "update_pair_run_status",
                repo.update_pair_run_status,
                pair["pair_id"],
                "finished",
            )

        # Pair synthetic DOCX redline report.
        docx_path = pair_dir / "track_changes.docx"
        render_track_changes_docx(docx_path, summary, events)
        add_artifact(state, "track_changes_docx", docx_path, f"Track changes {pair['pair_id']}", repo=repo)

        # Pair red/green PDF when both have canonical PDFs and there are material events.
        lhs_pdf = base / lhs_doc.get("canonical_pdf", "") if lhs_doc.get("canonical_pdf") else None
        rhs_pdf = base / rhs_doc.get("canonical_pdf", "") if rhs_doc.get("canonical_pdf") else None
        material_events = [e for e in events if e.get("status") in {"added", "deleted", "partial", "modified", "contradicts"}]
        if lhs_pdf and rhs_pdf and lhs_pdf.exists() and rhs_pdf.exists() and material_events:
            try:
                res = render_pair_redgreen_pdf(lhs_pdf, rhs_pdf, material_events, pair_dir, lhs_doc.get("filename", lhs_doc["doc_id"]), rhs_doc.get("filename", rhs_doc["doc_id"]))
                add_artifact(state, "redgreen_pdf", res["path"], f"Red/green PDF {pair['pair_id']}", repo=repo)
            except Exception as e:
                pair["pdf_render_error"] = str(e)

        save_state(batch_id, state)

    return all_events, pair_summaries


def render_global_reports(
    batch_id: str,
    state: dict[str, Any],
    all_events: list[dict[str, Any]],
    pair_summaries: list[dict[str, Any]],
    repo: Any | None = None,
) -> None:
    base = batch_dir(batch_id)
    xlsx_path = base / "reports" / "evidence_matrix.xlsx"
    render_evidence_matrix(xlsx_path, state, all_events, pair_summaries)
    add_artifact(state, "evidence_xlsx", xlsx_path, "Evidence matrix", repo=repo)

    md_path = base / "reports" / "executive_diff.md"
    render_executive_md(md_path, state, all_events, pair_summaries)
    add_artifact(state, "executive_md", md_path, "Executive diff", repo=repo)

    # PR-2.2: Executive DOCX (Word-formatted twin of the MD).
    try:
        from .render_executive_docx import render_executive_docx
        docx_path = base / "reports" / "executive_diff.docx"
        render_executive_docx(docx_path, state, all_events, pair_summaries)
        add_artifact(state, "executive_docx", docx_path, "Executive diff (DOCX)", repo=repo)
    except Exception as e:
        logger.warning("render_executive_docx failed: %s", e)

    # PR-2.5: standalone HTML report.
    try:
        from .render_html_report import render_html_report
        html_path = base / "reports" / "full_diff_report.html"
        render_html_report(html_path, state, all_events, pair_summaries)
        add_artifact(state, "full_html", html_path, "Full HTML report", repo=repo)
    except Exception as e:
        logger.warning("render_html_report failed: %s", e)

    # Cross-pair topic clusters: group same status+topic across all pairs.
    try:
        clusters = cluster_events(all_events)
        cl_path = base / "reports" / "topic_clusters.json"
        write_json(cl_path, {"clusters": clusters})
        add_artifact(state, "topic_clusters", cl_path, "Topic clusters JSON", repo=repo)
        state["topic_clusters"] = clusters
    except Exception as e:
        logger.warning("cluster_events failed: %s", e)

    # Machine-readable global exports.
    write_jsonl(base / "reports" / "diff_events_all.jsonl", all_events)
    write_json(base / "reports" / "pair_summaries.json", pair_summaries)
    add_artifact(state, "jsonl", base / "reports" / "diff_events_all.jsonl", "All diff events JSONL", repo=repo)
    add_artifact(state, "json", base / "reports" / "pair_summaries.json", "Pair summaries JSON", repo=repo)
    save_state(batch_id, state)


def _build_repo() -> Any | None:
    """Build a per-batch BatchRepository, or ``None`` if disabled."""
    import os

    if os.getenv("DUAL_WRITE_ENABLED", "true").lower() == "false":
        return None
    try:
        from .db.repository import BatchRepository

        return BatchRepository()
    except Exception as e:  # pragma: no cover
        logger.warning("DB dual-write disabled: import failed: %s", e)
        return None


def run_batch(batch_id: str, profile: str = "fast") -> dict[str, Any]:
    state = load_state(batch_id)
    repo = _build_repo()
    # Ensure the batch row exists in DB even when create_batch ran before
    # dual-write shipped (i.e. JSON-only batches predating PR-1.2).
    if repo is not None:
        _safe("create_batch", repo.create_batch, batch_id, title=state.get("title"))

    start = time.time()
    run = {"profile": profile, "started_at": now_ts(), "status": "running"}
    state.setdefault("runs", []).append(run)
    save_state(batch_id, state)

    try:
        normalize_and_extract(batch_id, state, prefer_pdf_visual=True, repo=repo)
        all_events, pair_summaries = run_all_pairs(batch_id, state, profile=profile, repo=repo)
        render_global_reports(batch_id, state, all_events, pair_summaries, repo=repo)
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
