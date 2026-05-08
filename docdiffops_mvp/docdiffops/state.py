from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from .settings import DATA_DIR
from .utils import now_ts, read_json, write_json

logger = logging.getLogger(__name__)


def batch_dir(batch_id: str) -> Path:
    return DATA_DIR / "batches" / batch_id


def state_path(batch_id: str) -> Path:
    return batch_dir(batch_id) / "state.json"


# ---------------------------------------------------------------------------
# Dual-write to Postgres (PR-1.2).
#
# JSON remains the read-of-truth in this PR; reads switch over to the DB in
# PR-1.3. The kill-switch ``DUAL_WRITE_ENABLED=false`` reverts to pure-JSON
# behavior so we can flip it off in production if the DB writes regress.
# All DB calls are wrapped in best-effort try/except: a failed DB write logs
# a warning but never raises — JSON is still authoritative.
# ---------------------------------------------------------------------------


def _dual_write_enabled() -> bool:
    return os.getenv("DUAL_WRITE_ENABLED", "true").lower() != "false"


def _get_repo() -> Optional[Any]:
    """Lazily build a BatchRepository.

    Returns ``None`` if the dual-write toggle is off OR if the import fails
    (e.g. SQLAlchemy not installed in some lightweight test contexts).
    """
    if not _dual_write_enabled():
        return None
    try:
        from .db.repository import BatchRepository

        return BatchRepository()
    except Exception as e:  # pragma: no cover - guard import-time failures
        logger.warning("DB dual-write disabled: import failed: %s", e)
        return None


def create_batch(
    title: str | None = None,
    config: dict[str, Any] | None = None,
    repo: Any | None = None,
) -> dict[str, Any]:
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

    # Dual-write: persist the batch row to Postgres alongside the JSON.
    db_repo = repo if repo is not None else _get_repo()
    if db_repo is not None:
        try:
            db_repo.create_batch(batch_id, title=state["title"])
        except Exception as e:
            logger.warning("DB dual-write failed: %s", e)
    return state


def load_state(batch_id: str) -> dict[str, Any]:
    state = read_json(state_path(batch_id))
    if not state:
        raise FileNotFoundError(f"Batch not found: {batch_id}")
    return state


def save_state(batch_id: str, state: dict[str, Any]) -> None:
    state["updated_at"] = now_ts()
    write_json(state_path(batch_id), state)


def add_artifact(
    state: dict[str, Any],
    artifact_type: str,
    path: Path,
    title: str | None = None,
    repo: Any | None = None,
) -> None:
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

    # Dual-write: persist the artifact row to Postgres alongside the JSON.
    # Sha256/size_bytes are not tracked in the JSON state today; pass ``None``
    # and let PR-1.3+ backfill them from the file when the read path moves
    # to the DB.
    db_repo = repo if repo is not None else _get_repo()
    if db_repo is not None:
        try:
            db_repo.add_artifact(
                batch_id=state["batch_id"],
                kind=artifact_type,
                path=rel,
            )
        except Exception as e:
            logger.warning("DB dual-write failed: %s", e)
