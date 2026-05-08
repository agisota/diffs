from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .settings import DATA_DIR
from .utils import now_ts, read_json, write_json


def batch_dir(batch_id: str) -> Path:
    return DATA_DIR / "batches" / batch_id


def state_path(batch_id: str) -> Path:
    return batch_dir(batch_id) / "state.json"


def create_batch(title: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    batch_id = "bat_" + uuid4().hex[:12]
    d = batch_dir(batch_id)
    for sub in ["raw", "normalized", "extracted", "pairs", "reports", "tmp"]:
        (d / sub).mkdir(parents=True, exist_ok=True)
    state = {
        "batch_id": batch_id,
        "title": title or batch_id,
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "config": config or {},
        "documents": [],
        "pairs": [],
        "runs": [],
        "artifacts": [],
        "metrics": {},
    }
    save_state(batch_id, state)
    return state


def load_state(batch_id: str) -> dict[str, Any]:
    state = read_json(state_path(batch_id))
    if not state:
        raise FileNotFoundError(f"Batch not found: {batch_id}")
    return state


def save_state(batch_id: str, state: dict[str, Any]) -> None:
    state["updated_at"] = now_ts()
    write_json(state_path(batch_id), state)


def add_artifact(state: dict[str, Any], artifact_type: str, path: Path, title: str | None = None) -> None:
    base = batch_dir(state["batch_id"])
    rel = str(path.relative_to(base)) if path.is_absolute() and path.exists() else str(path)
    key = (artifact_type, rel)
    existing = {(a.get("type"), a.get("path")) for a in state.get("artifacts", [])}
    if key not in existing:
        state.setdefault("artifacts", []).append({
            "type": artifact_type,
            "title": title or path.name,
            "path": rel,
        })
