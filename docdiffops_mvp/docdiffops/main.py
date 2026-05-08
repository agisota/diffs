from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from .schemas import CreateBatchRequest
from .settings import DATA_DIR
from .state import batch_dir, create_batch, load_state, save_state
from .utils import safe_name, sha256_file, stable_id
from .worker import run_batch_task
from .pipeline import run_batch as run_batch_sync

app = FastAPI(title="DocDiffOps", version="0.1.0")


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
async def upload_documents(batch_id: str, files: Annotated[list[UploadFile], File(description="Documents to compare")]):
    try:
        state = load_state(batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch not found")

    base = batch_dir(batch_id)
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing_sha = {d.get("sha256") for d in state.get("documents", [])}
    added = []

    for f in files:
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
        doc_id = "doc_" + stable_id(filename, digest, n=16)
        doc = {
            "doc_id": doc_id,
            "title": Path(filename).stem,
            "filename": filename,
            "raw_path": str(dst.relative_to(base)),
            "sha256": digest,
            "ext": Path(filename).suffix.lower(),
            "source_rank": 3,
            "doc_type": None,
            "status": "uploaded",
        }
        state.setdefault("documents", []).append(doc)
        existing_sha.add(digest)
        added.append(doc)

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
