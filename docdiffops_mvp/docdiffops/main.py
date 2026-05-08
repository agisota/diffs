from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

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


@app.post("/batches")
def create_batch_endpoint(req: CreateBatchRequest):
    state = create_batch(title=req.title, config=req.config)
    return {"batch_id": state["batch_id"], "state": state}


@app.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    try:
        return load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")


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


def now_ts_int() -> int:
    """Monotonic-ish unix-ms helper for unique decision ids."""
    import time
    return int(time.time() * 1000)
