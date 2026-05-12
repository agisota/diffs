from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .app_html import APP_HTML
from pydantic import BaseModel, Field
from .schemas import CreateBatchRequest
from .settings import DATA_DIR
from .source_registry import classify
from .state import (
    batch_dir,
    create_batch,
    list_batches,
    load_state,
    register_source_for_url,
    save_state,
)
from .utils import safe_name, sha256_file, stable_id
from .worker import run_batch_task
from .pipeline import run_batch as run_batch_sync

logger = logging.getLogger(__name__)

app = FastAPI(title="DocDiffOps", version="0.1.0")

# Static assets (pdf.js bundled in Dockerfile). Tolerate missing dir on dev
# boxes that don't run the Docker build — viewer falls back gracefully.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def root():
    """Single-page DocDiffOps web UI (upload, batch dashboard, events explorer)."""
    return HTMLResponse(content=APP_HTML)


@app.get("/health")
def health():
    return {"ok": True, "data_dir": str(DATA_DIR)}


@app.get("/batches")
def list_batches_endpoint():
    """List all batches (used by the web UI). Routes through state.list_batches
    which honours READ_FROM_DB and falls back to JSON when DB is empty."""
    return list_batches()


@app.delete("/batches/{batch_id}")
def delete_batch(batch_id: str):
    """Delete a batch — DB rows (cascading via FK) + on-disk batch_dir.

    Irreversible. Use with care. Returns the deleted batch_id on success.
    """
    try:
        load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    # DB delete via cascading FKs.
    from .state import _get_repo
    repo = _get_repo()
    if repo is not None:
        try:
            from .db import get_session
            from .db.models import Batch
            with get_session() as session:
                row = session.get(Batch, batch_id)
                if row is not None:
                    session.delete(row)
                    session.flush()
        except Exception as e:
            logger.warning("batch delete: DB removal failed: %s", e)
    # Filesystem cleanup.
    import shutil
    bdir = batch_dir(batch_id)
    if bdir.exists():
        try:
            shutil.rmtree(bdir)
        except Exception as e:
            logger.warning("batch delete: rmtree failed: %s", e)
    return {"batch_id": batch_id, "deleted": True}


@app.post("/batches")
def create_batch_endpoint(req: CreateBatchRequest):
    state = create_batch(title=req.title, config=req.config)
    return {"batch_id": state["batch_id"], "state": state}


@app.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    # M3: enrich each event with its latest review decision (batched, no N+1).
    from .state import _get_repo
    repo = _get_repo()
    if repo is not None:
        try:
            latest = repo.list_reviews_for_batch(batch_id)
            for e in (state.get("diff_events") or []):
                eid = e.get("event_id")
                if eid and eid in latest:
                    e["last_review"] = latest[eid]
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("list_reviews_for_batch enrich failed: %s", exc)
    return state


@app.post("/batches/{batch_id}/documents")
async def upload_documents(
    batch_id: str,
    files: Annotated[list[UploadFile], File(description="Documents to compare")],
    source_urls: Annotated[
        list[str] | None,
        Form(description="Optional provenance URLs, one per uploaded file in order"),
    ] = None,
):
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")

    base = batch_dir(batch_id)
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing_sha = {d.get("sha256") for d in state.get("documents", [])}
    added = []

    # Pad source_urls so callers can omit per-file URLs without erroring.
    # PR-1.5: classify falls back to rank-3 OTHER when URL is None.
    urls: list[str | None] = list(source_urls or [])
    while len(urls) < len(files):
        urls.append(None)

    for f, url in zip(files, urls):
        filename = safe_name(f.filename or "upload")
        dst = raw_dir / filename
        # Avoid overwriting same basename.
        if dst.exists():
            dst = raw_dir / f"{Path(filename).stem}_{stable_id(filename, str(len(state.get('documents', []))))}{Path(filename).suffix}"
        content = await f.read()
        dst.write_bytes(content)
        digest = sha256_file(dst)
        if digest in existing_sha:
            dst.unlink(missing_ok=True)
            continue

        # PR-1.5: classify using filename + URL host + first 4 KB of bytes.
        # Empty URL strings (form quirk) collapse to None so rank stays 3.
        clean_url = (url or "").strip() or None
        doc_type, source_rank = classify(
            filename=filename,
            source_url=clean_url,
            content_head=content[:4096],
        )

        doc_id = "doc_" + stable_id(filename, digest, n=16)
        doc = {
            "doc_id": doc_id,
            "title": Path(filename).stem,
            "filename": filename,
            "raw_path": str(dst.relative_to(base)),
            "sha256": digest,
            "ext": Path(filename).suffix.lower(),
            "source_rank": source_rank,
            "doc_type": doc_type,
            "source_url": clean_url,
            "status": "uploaded",
        }
        state.setdefault("documents", []).append(doc)
        existing_sha.add(digest)
        added.append(doc)

        # Dual-write to Postgres at upload time so reads via READ_FROM_DB
        # see the doc immediately, not only after pipeline.run_batch
        # backfills via normalize_and_extract.
        try:
            from .state import _get_repo as _get_db_repo  # local import to avoid cycle
            _r = _get_db_repo()
            if _r is not None:
                _r.add_document(
                    batch_id=batch_id,
                    doc_id=doc_id,
                    filename=filename,
                    sha256=digest,
                    extension=Path(filename).suffix.lower(),
                    source_rank=int(source_rank),
                    doc_type=doc_type,
                    source_url=clean_url,
                )
        except Exception as e:
            logger.warning("DB dual-write of document failed (best-effort): %s", e)

        # PR-1.5: register the URL once so PR-4.4 polling has a target.
        if clean_url:
            try:
                register_source_for_url(clean_url, source_rank, doc_type)
            except Exception as e:
                logger.warning("source_registry registration failed: %s", e)

    save_state(batch_id, state)
    return {"added": added, "documents_total": len(state.get("documents", []))}


@app.post("/batches/{batch_id}/run")
def run_batch_endpoint(batch_id: str, profile: str = Query("fast", pattern="^(fast|full)$"), sync: bool = Query(False)):
    try:
        load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")

    if sync:
        metrics = run_batch_sync(batch_id, profile=profile)
        return {"mode": "sync", "batch_id": batch_id, "metrics": metrics}

    task = run_batch_task.delay(batch_id, profile)
    return {"mode": "async", "batch_id": batch_id, "task_id": task.id}


@app.post("/batches/{batch_id}/rerender-compare")
def rerender_compare_endpoint(batch_id: str, sync: bool = Query(False)):
    """Re-run compare+enrich on an existing batch without re-uploading.

    Useful after pipeline fixes (bbox isinstance bug, normalize TEXT_EXTS,
    enrich threshold tuning) — old batches stay with stale event positions
    until manually re-compared. This endpoint reuses cached extract blocks
    on disk, regenerates events, upserts into DB preserving review_decisions.

    By default dispatches asynchronously via Celery; pass sync=true for
    small batches that complete within the HTTP timeout.
    """
    try:
        load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    if sync:
        from .pipeline import rerender_compare
        try:
            metrics = rerender_compare(batch_id)
        except Exception as e:
            logger.exception("rerender_compare failed for %s", batch_id)
            raise HTTPException(status_code=500, detail=f"rerender failed: {e}")
        return {"batch_id": batch_id, "mode": "rerender-compare-sync", "metrics": metrics}
    from .worker import rerender_compare_task
    task = rerender_compare_task.delay(batch_id)
    return {"batch_id": batch_id, "mode": "rerender-compare-async", "task_id": task.id}


@app.post("/batches/{batch_id}/rerender-full")
def rerender_full_endpoint(batch_id: str, sync: bool = Query(False)):
    """Deep rerender: drop cached extracts, re-run normalize+extract+compare+enrich.

    Use when previously-uploaded documents need to pick up updated extract
    behaviour (e.g. HTML uploaded before normalize.py learned to convert
    text formats to canonical PDF). Preserves review_decisions via stable
    event_ids upsert.

    By default dispatches asynchronously via Celery; pass sync=true for
    small batches that complete within the HTTP timeout.
    """
    try:
        load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    if sync:
        from .pipeline import rerender_full
        try:
            metrics = rerender_full(batch_id)
        except Exception as e:
            logger.exception("rerender_full failed for %s", batch_id)
            raise HTTPException(status_code=500, detail=f"rerender-full failed: {e}")
        return {"batch_id": batch_id, "mode": "rerender-full-sync", "metrics": metrics}
    from .worker import rerender_full_task
    task = rerender_full_task.delay(batch_id)
    return {"batch_id": batch_id, "mode": "rerender-full-async", "task_id": task.id}


@app.get("/batches/{batch_id}/pair/{pair_id}/merged.docx")
def get_merged_docx(batch_id: str, pair_id: str):
    """Generate a 'merged' DOCX with accept/reject decisions applied.

    On-demand generation — not cached, so reflects the latest reviews.
    Pending events stay as Word track-changes; decided events are
    materialized into normal paragraphs.
    """
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    pair = next(
        (p for p in (state.get("pair_runs") or state.get("pairs") or []) if p.get("pair_id") == pair_id),
        None,
    )
    if not pair:
        raise HTTPException(status_code=404, detail="pair not found")
    docs = {d["doc_id"]: d for d in (state.get("documents") or [])}
    lhs_doc = docs.get(pair.get("lhs_doc_id"))
    rhs_doc = docs.get(pair.get("rhs_doc_id"))
    events = [e for e in (state.get("diff_events") or []) if e.get("pair_id") == pair_id]
    # Enrich with last_review so render_merged_docx sees confirmed/rejected.
    # load_state() does NOT add last_review — only get_batch() does (M3).
    # Without this, every event was treated as pending and the merged DOCX
    # produced track-changes for everything regardless of reviewer decisions.
    from .state import _get_repo
    repo = _get_repo()
    if repo is not None:
        try:
            latest = repo.list_reviews_for_batch(batch_id)
            for e in events:
                eid = e.get("event_id")
                if eid and eid in latest:
                    e["last_review"] = latest[eid]
        except Exception as exc:
            logger.warning("merged_docx: last_review enrich failed: %s", exc)
    from .render_merged_docx import render_merged_docx
    out_dir = batch_dir(batch_id) / "pairs" / pair_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "merged.docx"
    try:
        counts = render_merged_docx(out_path, pair_id, events, lhs_doc=lhs_doc, rhs_doc=rhs_doc)
    except Exception as e:
        logger.exception("merged docx render failed for %s/%s", batch_id, pair_id)
        raise HTTPException(status_code=500, detail=f"merged render failed: {e}")
    fname = f"merged_{pair_id[-12:]}.docx"
    resp = FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=fname,
    )
    resp.headers["X-Merge-Counts"] = ",".join(f"{k}={v}" for k, v in counts.items())
    # Bust caches: this document mutates with every accept/reject decision,
    # and Cloudflare was serving the stale first-rendered version by ETag.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/batches/{batch_id}/merged.zip")
def get_merged_zip(batch_id: str):
    """Bulk download: merged DOCX for every pair in the batch, packed as ZIP.

    Each pair's file is named merged_{pair_id_last12}.docx inside the
    archive. Same per-pair semantics as /pair/{pid}/merged.docx (confirmed
    materialized, rejected restored to LHS, pending kept as track-changes).
    Cache-Control: no-store so freshly-reviewed batches are always current.
    """
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    pairs = state.get("pair_runs") or state.get("pairs") or []
    if not pairs:
        raise HTTPException(status_code=400, detail="no pairs in batch")
    docs = {d["doc_id"]: d for d in (state.get("documents") or [])}
    all_events = state.get("diff_events") or []

    # Enrich with last_review once (batched, no N+1).
    from .state import _get_repo
    repo = _get_repo()
    if repo is not None:
        try:
            latest = repo.list_reviews_for_batch(batch_id)
            for e in all_events:
                eid = e.get("event_id")
                if eid and eid in latest:
                    e["last_review"] = latest[eid]
        except Exception as exc:
            logger.warning("merged_zip: last_review enrich failed: %s", exc)

    from .render_merged_docx import render_merged_docx
    base = batch_dir(batch_id)
    buf = io.BytesIO()
    total_counts: dict[str, int] = {"confirmed": 0, "rejected": 0, "pending": 0, "skipped": 0, "ambiguous": 0}
    rendered = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pair in pairs:
            pid = pair.get("pair_id")
            if not pid:
                continue
            lhs_doc = docs.get(pair.get("lhs_doc_id"))
            rhs_doc = docs.get(pair.get("rhs_doc_id"))
            evs = [e for e in all_events if e.get("pair_id") == pid]
            out_dir = base / "pairs" / pid
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "merged.docx"
            try:
                counts = render_merged_docx(out_path, pid, evs, lhs_doc=lhs_doc, rhs_doc=rhs_doc)
                for k, v in counts.items():
                    total_counts[k] = total_counts.get(k, 0) + v
                arcname = f"merged_{pid[-12:]}.docx"
                zf.write(out_path, arcname=arcname)
                rendered += 1
            except Exception as e:
                logger.exception("merged_zip: pair %s failed: %s", pid, e)
                # Continue with other pairs; don't fail the whole archive
                continue

        # Audit manifest inside the ZIP
        manifest = (
            f"DocDiffOps merged.zip\n"
            f"batch_id: {batch_id}\n"
            f"rendered_pairs: {rendered} / {len(pairs)}\n"
            f"total_events: {len(all_events)}\n"
            f"counts: " + ", ".join(f"{k}={v}" for k, v in total_counts.items()) + "\n"
        )
        zf.writestr("README.txt", manifest)

    buf.seek(0)
    fname = f"merged_{batch_id[-12:]}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Merge-Counts": ",".join(f"{k}={v}" for k, v in total_counts.items()),
            "X-Pairs-Rendered": f"{rendered}/{len(pairs)}",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    res = run_batch_task.AsyncResult(task_id)
    return {"task_id": task_id, "state": res.state, "result": res.result if res.ready() else None}


@app.get("/batches/{batch_id}/artifacts")
def list_artifacts(batch_id: str):
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    artifacts = []
    for a in state.get("artifacts", []):
        item = dict(a)
        item["download_url"] = f"/batches/{batch_id}/download/{a['path']}"
        artifacts.append(item)
    return {"batch_id": batch_id, "artifacts": artifacts}


@app.get("/batches/{batch_id}/download/{path:path}")
def download_artifact(batch_id: str, path: str):
    base = batch_dir(batch_id).resolve()
    p = (base / path).resolve()
    if not str(p).startswith(str(base)) or not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(p)


@app.get("/batches/{batch_id}/docs/{doc_id}/canonical.pdf")
def download_canonical_pdf(batch_id: str, doc_id: str):
    """Stream the canonical PDF of a single document.

    Used by the inline viewer to render any format (DOCX/PPTX/HTML/PDF) — the
    normalize stage already converts everything to PDF via LibreOffice. Falls
    back to raw_path when the document is itself a .pdf and no separate
    canonical was produced.
    """
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    doc = next((d for d in state.get("documents", []) if d.get("doc_id") == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="doc not found")
    rel = doc.get("canonical_pdf") or (doc.get("raw_path") if (doc.get("ext") or "").lower() == ".pdf" else None)
    if not rel:
        raise HTTPException(status_code=404, detail="no canonical PDF for this document")
    base = batch_dir(batch_id).resolve()
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)) or not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="canonical PDF file missing on disk")
    return FileResponse(p, media_type="application/pdf")


# ---------------------------------------------------------------------------
# PR-4.1: review decisions
# ---------------------------------------------------------------------------


class ReviewRequest(BaseModel):
    decision: str = Field(..., description="confirmed|rejected|needs_more_info|deferred")
    reviewer_name: str = Field("anonymous", description="Free-text name; service is anonymous")
    comment: str | None = None


@app.post("/events/{event_id}/review")
def review_event(event_id: str, req: ReviewRequest):
    """Record a reviewer decision against a diff_event.

    The service is anonymous (Q1 closure); reviewer_name is whatever
    the form sends. Decisions are append-only — earlier decisions are
    preserved. Returns the new decision row plus the updated review
    history for the event.
    """
    from .state import _get_repo  # local import to avoid cycle
    repo = _get_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    decision_id = "rd_" + stable_id(
        event_id, req.reviewer_name, req.decision, str(now_ts_int()), n=20
    )
    try:
        row = repo.add_review_decision(
            decision_id=decision_id,
            event_id=event_id,
            reviewer_name=req.reviewer_name,
            decision=req.decision,
            comment=req.comment,
        )
    except Exception as e:
        logger.warning("review write failed: %s", e)
        raise HTTPException(status_code=400, detail=f"review failed: {e}")
    # Audit (best-effort). Resolve event → pair_run → batch so the entry
    # surfaces in the per-batch audit view.
    audit_batch_id = None
    try:
        from .db import get_session
        from .db.models import DiffEvent, PairRun
        with get_session() as session:
            ev = session.get(DiffEvent, event_id)
            if ev is not None:
                pr = session.get(PairRun, ev.pair_run_id)
                if pr is not None:
                    audit_batch_id = pr.batch_id
    except Exception:
        pass
    try:
        repo.add_audit_entry(
            entry_id="ae_" + stable_id(decision_id, "review", n=20),
            action="event.review",
            batch_id=audit_batch_id,
            actor=req.reviewer_name,
            target_kind="diff_event",
            target_id=event_id,
            payload={"decision": req.decision, "comment": req.comment},
        )
    except Exception as e:
        logger.warning("audit write failed: %s", e)
    history = repo.list_event_reviews(event_id)
    return {"decision": row, "history": history}


@app.get("/events/{event_id}/reviews")
def list_event_reviews(event_id: str):
    from .state import _get_repo
    repo = _get_repo()
    if repo is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    return {"event_id": event_id, "history": repo.list_event_reviews(event_id)}


@app.post("/events/{event_id}/ai-suggest")
def ai_suggest_event(event_id: str):
    """Return AI recommendation (accept/reject + reasoning) for one event.

    Calls the same LLM stack used elsewhere in the project. Read-only —
    does not record a decision, just returns the suggestion so the SPA
    can pre-fill the popover.
    """
    from .state import _get_repo  # local import to avoid cycle
    repo = _get_repo()
    event: dict | None = None
    batch_id: str | None = None
    if repo is not None:
        try:
            from .db import get_session
            from .db.models import DiffEvent, PairRun
            with get_session() as session:
                row = session.get(DiffEvent, event_id)
                if row is not None:
                    event = {
                        "event_id": row.id,
                        "status": row.status,
                        "severity": row.severity,
                        "explanation_short": row.explanation_short,
                        "lhs": {"quote": row.lhs_quote, "doc_id": row.lhs_doc_id},
                        "rhs": {"quote": row.rhs_quote, "doc_id": row.rhs_doc_id},
                    }
                    if row.pair_run_id:
                        pr = session.get(PairRun, row.pair_run_id)
                        if pr is not None:
                            batch_id = pr.batch_id
        except Exception as e:
            logger.warning("ai_suggest: DB lookup failed: %s", e)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    # Best-effort doc enrichment from batch state.
    lhs_doc: dict | None = None
    rhs_doc: dict | None = None
    if batch_id:
        try:
            st = load_state(batch_id)
            docs = {d["doc_id"]: d for d in (st.get("documents") or [])}
            lhs_doc = docs.get(event["lhs"].get("doc_id"))
            rhs_doc = docs.get(event["rhs"].get("doc_id"))
        except Exception:
            pass
    from .ai_suggest import suggest_for_event
    try:
        result = suggest_for_event(event, lhs_doc=lhs_doc, rhs_doc=rhs_doc)
    except Exception as e:
        logger.exception("ai_suggest failed for %s", event_id)
        raise HTTPException(status_code=502, detail=f"AI suggest failed: {e}")
    return {"event_id": event_id, "suggestion": result}


# ---------------------------------------------------------------------------
# PR-4.2: anchor rerender
# ---------------------------------------------------------------------------


@app.post("/batches/{batch_id}/render")
def rerender_reports(batch_id: str, anchor_doc_id: str | None = Query(None)):
    """Re-run report generation without re-extracting or re-comparing.

    The compare results are cached per (lhs_sha, rhs_sha) by PR-1.6, so
    this endpoint is cheap. ``anchor_doc_id`` shapes the report layout
    so the chosen doc is the LHS in every pair. The compare graph
    itself is symmetric (PR-1.5 ADR-4) so no data needs to be recomputed.
    """
    from .pipeline import (
        render_global_reports,
        run_all_pairs,  # to rebuild events list from cache
    )
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")

    # Optional reorientation: surface the chosen anchor as LHS in every
    # pair-card and update state["anchor_doc_id"] so downstream renderers
    # can use it. We don't physically swap pair_runs because the diff is
    # already symmetric.
    if anchor_doc_id:
        if not any(d.get("doc_id") == anchor_doc_id for d in state.get("documents", [])):
            raise HTTPException(status_code=400, detail="anchor_doc_id not in this batch")
        state["anchor_doc_id"] = anchor_doc_id
        save_state(batch_id, state)

    # Recompute events list by re-running run_all_pairs (it's cache-hit
    # for content unchanged) — this gives us the inputs to render.
    events, summaries = run_all_pairs(batch_id, state)
    render_global_reports(batch_id, state, events, summaries)
    save_state(batch_id, state)

    # Audit
    from .state import _get_repo
    repo = _get_repo()
    if repo is not None:
        try:
            repo.add_audit_entry(
                entry_id="ae_" + stable_id(batch_id, "rerender", anchor_doc_id or "", str(now_ts_int()), n=20),
                action="batch.rerender",
                batch_id=batch_id,
                target_kind="batch",
                target_id=batch_id,
                payload={"anchor_doc_id": anchor_doc_id},
            )
        except Exception as e:
            logger.warning("audit write failed: %s", e)

    return {
        "batch_id": batch_id,
        "anchor_doc_id": anchor_doc_id,
        "events": len(events),
        "pairs": len(summaries),
    }


# ---------------------------------------------------------------------------
# PR-4.6: audit log read
# ---------------------------------------------------------------------------


@app.get("/batches/{batch_id}/audit")
def get_batch_audit(batch_id: str, limit: int = Query(200, ge=1, le=2000)):
    from .state import _get_repo
    repo = _get_repo()
    if repo is None:
        return {"batch_id": batch_id, "entries": []}
    return {"batch_id": batch_id, "entries": repo.list_audit_for_batch(batch_id, limit=limit)}


@app.get("/batches/{batch_id}/events.csv")
def export_events_csv(batch_id: str):
    """Export all events of a batch as UTF-8 CSV with BOM (Excel-friendly).

    Columns: event_id, pair_id, status, severity, confidence,
    lhs_doc_id, lhs_page, lhs_quote, rhs_doc_id, rhs_page, rhs_quote,
    last_review_decision, last_review_reviewer, last_review_date,
    last_review_comment, explanation_short.
    """
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    # Enrich with last_review (same M3 pattern as get_batch).
    from .state import _get_repo
    repo = _get_repo()
    events = state.get("diff_events") or []
    if repo is not None:
        try:
            latest = repo.list_reviews_for_batch(batch_id)
            for e in events:
                eid = e.get("event_id")
                if eid and eid in latest:
                    e["last_review"] = latest[eid]
        except Exception as exc:
            logger.warning("csv export: last_review enrich failed: %s", exc)

    import csv
    import io as _io
    buf = _io.StringIO()
    buf.write("﻿")  # UTF-8 BOM for Excel
    cols = [
        "event_id", "pair_id", "status", "severity", "confidence",
        "lhs_doc_id", "lhs_page", "lhs_quote",
        "rhs_doc_id", "rhs_page", "rhs_quote",
        "last_review_decision", "last_review_reviewer", "last_review_date", "last_review_comment",
        "explanation_short",
    ]
    w = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    w.writerow(cols)
    for e in events:
        lhs = e.get("lhs") or {}
        rhs = e.get("rhs") or {}
        lr = e.get("last_review") or {}
        w.writerow([
            e.get("event_id") or "",
            e.get("pair_id") or "",
            e.get("status") or "",
            e.get("severity") or "",
            e.get("confidence") or "",
            lhs.get("doc_id") or "",
            lhs.get("page_no") or "",
            (lhs.get("quote") or "").replace("\n", " ").replace("\r", " "),
            rhs.get("doc_id") or "",
            rhs.get("page_no") or "",
            (rhs.get("quote") or "").replace("\n", " ").replace("\r", " "),
            lr.get("decision") or "",
            lr.get("reviewer_name") or "",
            lr.get("decided_at") or "",
            (lr.get("comment") or "").replace("\n", " ").replace("\r", " "),
            (e.get("explanation_short") or "").replace("\n", " ").replace("\r", " "),
        ])
    csv_bytes = buf.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="events_{batch_id[-12:]}.csv"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/batches/{batch_id}/clusters")
def get_batch_clusters(batch_id: str):
    """Cross-pair topic clusters — same status+topic grouped across pairs."""
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    clusters = state.get("topic_clusters")
    if clusters is None:
        from .legal.cross_pair import cluster_events
        clusters = cluster_events(state.get("diff_events", []))
    return {"batch_id": batch_id, "clusters": clusters}


@app.get("/batches/{batch_id}/forensic")
def get_batch_forensic(batch_id: str):
    """Return the v8 forensic JSON bundle for ``batch_id``.

    The bundle is rendered by ``pipeline._render_forensic_bundle`` after a
    batch finishes; if the file is missing the endpoint returns 404 — no
    on-the-fly recomputation. Inspect ``state["forensic_v8"]`` for a
    summary if the full bundle is too large.
    """
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")
    bundle_path = batch_dir(batch_id) / "reports" / "forensic_v8" / "bundle.json"
    if not bundle_path.exists():
        raise HTTPException(
            status_code=404,
            detail="forensic v8 bundle not generated yet — run /batches/{batch_id}/run first",
        )
    import json
    return json.loads(bundle_path.read_text(encoding="utf-8"))


@app.get("/batches/{old_batch_id}/forensic/compare/{new_batch_id}")
def get_forensic_compare(
    old_batch_id: str,
    new_batch_id: str,
    persist: bool = Query(False, description="If true, save delta as a batch artifact"),
    artifacts: bool = Query(False, description="If true, also render .xlsx/.docx/.pdf delta reports (implies persist)"),
):
    """Compare two forensic v8 bundles and return a delta report.

    Returns 404 if either bundle is not yet generated. Returns 422 if the
    bundles have incompatible schema versions. When ``persist=true`` the
    delta JSON is written to the new batch's reports dir and registered as
    an artifact so it appears in /batches/{id}/artifacts.
    """
    import json as _json
    from .forensic_delta import compare_bundles

    def _load(bid: str) -> dict:
        p = batch_dir(bid) / "reports" / "forensic_v8" / "bundle.json"
        if not p.exists():
            raise HTTPException(
                status_code=404,
                detail=f"forensic bundle for batch {bid!r} not generated yet",
            )
        return _json.loads(p.read_text(encoding="utf-8"))

    old_bundle = _load(old_batch_id)
    new_bundle = _load(new_batch_id)
    try:
        delta = compare_bundles(old_bundle, new_bundle)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if persist or artifacts:
        out_dir = batch_dir(new_batch_id) / "reports" / "forensic_v8"
        out_dir.mkdir(parents=True, exist_ok=True)
        delta_path = out_dir / f"delta_from_{old_batch_id}.json"
        delta_path.write_text(
            _json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            from .state import add_artifact as _add_artifact
            state = load_state(new_batch_id)
            _add_artifact(
                state, "forensic_delta", delta_path,
                title=f"Forensic delta vs {old_batch_id}",
            )
            if artifacts:
                from .forensic_delta_render import (
                    render_delta_docx, render_delta_pdf, render_delta_xlsx,
                )
                xlsx_path = out_dir / f"delta_from_{old_batch_id}.xlsx"
                docx_path = out_dir / f"delta_from_{old_batch_id}.docx"
                pdf_path = out_dir / f"delta_from_{old_batch_id}.pdf"
                render_delta_xlsx(delta, xlsx_path)
                render_delta_docx(delta, docx_path)
                render_delta_pdf(delta, pdf_path)
                _add_artifact(state, "forensic_delta_xlsx", xlsx_path,
                              title=f"Forensic delta XLSX vs {old_batch_id}")
                _add_artifact(state, "forensic_delta_docx", docx_path,
                              title=f"Forensic delta DOCX vs {old_batch_id}")
                _add_artifact(state, "forensic_delta_pdf", pdf_path,
                              title=f"Forensic delta PDF vs {old_batch_id}")
            save_state(new_batch_id, state)
        except Exception as e:
            logger.warning("delta artifact registration failed: %s", e)
    return delta


@app.get("/forensic/trend")
def get_forensic_trend(ids: str = Query(..., description="Comma-separated batch IDs in chronological order")):
    """Aggregate N forensic bundles into a time-series trend report.

    Returns 404 if any batch's bundle is not yet generated. Returns 422
    on schema version mismatch. ``ids`` order is taken as chronological.
    """
    import json as _json
    from .forensic_trend import compute_trend

    batch_ids = [b.strip() for b in ids.split(",") if b.strip()]
    if not batch_ids:
        raise HTTPException(status_code=400, detail="ids parameter is empty")

    bundles = []
    for bid in batch_ids:
        p = batch_dir(bid) / "reports" / "forensic_v8" / "bundle.json"
        if not p.exists():
            raise HTTPException(
                status_code=404,
                detail=f"forensic bundle for batch {bid!r} not generated yet",
            )
        bundles.append(_json.loads(p.read_text(encoding="utf-8")))

    try:
        return compute_trend(bundles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/batches/{batch_id}/forensic/v10")
def get_batch_v10_bundle(batch_id: str):
    """Return URLs for all v10 artifacts.

    Returns 404 if v10 bundle not generated (V10_BUNDLE_ENABLED=false or
    pipeline hasn't completed).
    """
    base = batch_dir(batch_id) / "reports" / "v10"
    if not base.exists() or not (base / "correlation_matrix.csv").exists():
        raise HTTPException(
            status_code=404,
            detail="v10 bundle not generated for this batch (V10_BUNDLE_ENABLED=false?)",
        )
    return {
        "batch_id": batch_id,
        "artifacts": {
            "xlsx": f"/batches/{batch_id}/forensic/xlsx_v10",
            "note_docx": f"/batches/{batch_id}/forensic/note_docx",
            "note_pdf": f"/batches/{batch_id}/forensic/note_pdf",
            "integral_matrix_pdf": f"/batches/{batch_id}/forensic/integral_matrix_pdf",
            "correlation_matrix_csv": f"/batches/{batch_id}/forensic/correlation_matrix_csv",
            "dependency_graph_csv": f"/batches/{batch_id}/forensic/dependency_graph_csv",
            "claim_provenance_csv": f"/batches/{batch_id}/forensic/claim_provenance_csv",
            "coverage_heatmap_csv": f"/batches/{batch_id}/forensic/coverage_heatmap_csv",
        },
    }


@app.get("/batches/{batch_id}/forensic/v10.zip")
def download_batch_v10_zip(batch_id: str):
    """Stream a ZIP archive containing all 8 v10 forensic artifacts.

    Convenience for downloading the full v10 bundle in one request instead of
    8 separate /forensic/{kind} calls.

    Returns 404 if v10 dir is missing or any expected artifact is absent.
    """
    base = batch_dir(batch_id) / "reports" / "v10"
    if not base.exists():
        raise HTTPException(
            status_code=404,
            detail="v10 bundle not generated for this batch (V10_BUNDLE_ENABLED=false?)",
        )

    expected_files = [
        "Интегральное_перекрестное_сравнение_v10.xlsx",
        "Пояснительная_записка_v10.docx",
        "Пояснительная_записка_v10.pdf",
        "Интегральное_перекрестное_сравнение_v10.pdf",
        "correlation_matrix.csv",
        "dependency_graph.csv",
        "claim_provenance.csv",
        "coverage_heatmap.csv",
    ]
    missing = [f for f in expected_files if not (base / f).exists()]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"v10 bundle incomplete; missing files: {missing}",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname in expected_files:
            zf.write(base / fname, arcname=fname)
    buf.seek(0)
    payload = buf.getvalue()

    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="forensic_v10_{batch_id}.zip"',
            "Content-Length": str(len(payload)),
        },
    )


@app.get("/batches/{batch_id}/forensic/{kind}")
def download_forensic(batch_id: str, kind: str):
    """Download forensic artifact: v8 (json/xlsx/docx/redgreen_docx/pdf) or
    v10 (xlsx_v10/note_docx/note_pdf/integral_matrix_pdf/correlation_matrix_csv/
    dependency_graph_csv/claim_provenance_csv/coverage_heatmap_csv).

    Files served from batch_dir/reports/{forensic_v8|v10}/. Unknown kinds -> 400;
    missing files -> 404.
    """
    v8_filenames = {
        "json": "bundle.json",
        "xlsx": "forensic_v8.xlsx",
        "docx": "forensic_v8_explanatory.docx",
        "redgreen_docx": "forensic_v8_redgreen.docx",
        "pdf": "forensic_v8_summary.pdf",
    }
    v10_filenames = {
        "xlsx_v10": "Интегральное_перекрестное_сравнение_v10.xlsx",
        "note_docx": "Пояснительная_записка_v10.docx",
        "note_pdf": "Пояснительная_записка_v10.pdf",
        "integral_matrix_pdf": "Интегральное_перекрестное_сравнение_v10.pdf",
        "correlation_matrix_csv": "correlation_matrix.csv",
        "dependency_graph_csv": "dependency_graph.csv",
        "claim_provenance_csv": "claim_provenance.csv",
        "coverage_heatmap_csv": "coverage_heatmap.csv",
    }
    if kind in v8_filenames:
        p = batch_dir(batch_id) / "reports" / "forensic_v8" / v8_filenames[kind]
    elif kind in v10_filenames:
        p = batch_dir(batch_id) / "reports" / "v10" / v10_filenames[kind]
    else:
        all_kinds = sorted(list(v8_filenames) + list(v10_filenames))
        raise HTTPException(
            status_code=400,
            detail=f"unknown kind {kind!r}; expected one of {all_kinds}",
        )
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"forensic artifact {kind!r} not found")
    return FileResponse(p, filename=p.name)


def now_ts_int() -> int:
    """Monotonic-ish unix-ms helper for unique decision ids."""
    import time
    return int(time.time() * 1000)
