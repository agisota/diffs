from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .schemas import CreateBatchRequest
from .settings import DATA_DIR
from .source_registry import classify
from .state import (
    batch_dir,
    create_batch,
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
    """Service landing page — minimal index that links to /docs and /health."""
    body = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>DocDiffOps</title>
<style>
  body { font: 15px/1.55 -apple-system, system-ui, "Segoe UI", sans-serif;
         background: #0f1115; color: #e9eef5; margin: 0;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; }
  main { max-width: 560px; padding: 32px; }
  h1 { font-size: 28px; margin: 0 0 8px; }
  .sub { color: #95a3b8; margin-bottom: 24px; }
  ul { list-style: none; padding: 0; }
  li { margin: 8px 0; }
  a { color: #4cc3ff; text-decoration: none; border-bottom: 1px dashed #2b3441; }
  a:hover { border-bottom-style: solid; }
  code { background: #1f2632; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
</style></head>
<body><main>
  <h1>DocDiffOps</h1>
  <div class="sub">Production pipeline for all-to-all document comparison.</div>
  <ul>
    <li><a href="/docs">Swagger UI</a> — interactive API explorer</li>
    <li><a href="/redoc">ReDoc</a> — alternative API docs</li>
    <li><a href="/health">/health</a> — liveness probe (JSON)</li>
    <li><code>POST /batches</code> · <code>POST /batches/{id}/documents</code> · <code>POST /batches/{id}/run</code></li>
  </ul>
  <div class="sub" style="margin-top:24px;font-size:12px">Source: <a href="https://github.com/agisota/diffs">github.com/agisota/diffs</a></div>
</main></body></html>"""
    return HTMLResponse(content=body)


@app.get("/health")
def health():
    return {"ok": True, "data_dir": str(DATA_DIR)}


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
