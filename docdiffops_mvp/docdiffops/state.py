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
# Dual-write to Postgres (PR-1.2) + read cutover (PR-1.3).
#
# Three env flags control the JSON ↔ DB plumbing:
#
# - ``DUAL_WRITE_ENABLED`` (default true): toggles DB writes. Set to false
#   to revert to pure-JSON if the DB regresses.
# - ``READ_FROM_DB`` (default true, PR-1.3): when true, ``load_state`` and
#   ``list_batches`` prefer the DB and only fall back to JSON when the DB
#   returns nothing or fails. When false, reads come straight from JSON
#   (the PR-1.2 behavior — kept as a safety valve).
# - ``WRITE_JSON_STATE`` (default true, PR-1.3): gates the JSON write side.
#   In this PR the default stays true so JSON acts as belt-and-suspenders
#   while the DB read path bakes in. PR-1.4 (or PR-1.6) is when we flip
#   the default to ``false`` and stop writing state.json on new batches.
#
# All DB calls are wrapped in best-effort try/except: a failed DB write
# logs a warning but never raises so the JSON write remains authoritative.
# ---------------------------------------------------------------------------


def _dual_write_enabled() -> bool:
    return os.getenv("DUAL_WRITE_ENABLED", "true").lower() != "false"


def _read_from_db() -> bool:
    return os.getenv("READ_FROM_DB", "true").lower() != "false"


def _write_json_state() -> bool:
    # NOTE: default is "true" in PR-1.3. PR-1.4/PR-1.6 will flip the default
    # to "false" once the DB read cutover has soaked.
    return os.getenv("WRITE_JSON_STATE", "true").lower() != "false"


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


def _get_read_repo() -> Optional[Any]:
    """Build a repo for the read path even when dual-write is disabled.

    The ``DUAL_WRITE_ENABLED`` flag only governs writes. Reads consult the
    DB whenever ``READ_FROM_DB`` is true; if SQLAlchemy is not importable
    we silently fall back to JSON.
    """
    if not _read_from_db():
        return None
    try:
        from .db.repository import BatchRepository

        return BatchRepository()
    except Exception as e:  # pragma: no cover
        logger.warning("DB read disabled: import failed: %s", e)
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


def _load_json_only(batch_id: str) -> dict[str, Any]:
    """Read state.json directly, bypassing the DB read path.

    Used by the integration parity test and as the JSON-fallback inside
    ``load_state``. Raises ``FileNotFoundError`` if the file is missing
    or empty so callers can detect a missing batch.
    """
    state = read_json(state_path(batch_id))
    if not state:
        raise FileNotFoundError(f"Batch not found: {batch_id}")
    return state


def load_state(batch_id: str) -> dict[str, Any]:
    """Read the canonical state dict for ``batch_id``.

    PR-1.3 prefers the DB when ``READ_FROM_DB=true`` and falls back to
    the JSON file when the DB has no row for the batch (or the DB query
    raises). This keeps old batches that predate the DB schema readable
    while new batches transparently move to Postgres.
    """
    repo = _get_read_repo()
    if repo is not None:
        try:
            db_state = repo.to_state_dict(batch_id)
        except Exception as e:
            logger.warning("DB read failed for %s, falling back to JSON: %s", batch_id, e)
            db_state = None
        if db_state:
            # Backfill JSON-only fields the DB doesn't track when the JSON
            # file still exists (config, runs, metrics, plus per-document
            # paths the DB schema doesn't carry yet).
            try:
                json_state = _load_json_only(batch_id)
            except FileNotFoundError:
                return db_state
            return _merge_db_with_json(db_state, json_state)
    # Read-from-DB disabled, repo unavailable, or empty DB row → JSON fallback.
    return _load_json_only(batch_id)


def list_batches() -> list[dict[str, Any]]:
    """List all known batches.

    Routes through the same ``READ_FROM_DB`` flag as ``load_state``.
    Falls back to scanning ``DATA_DIR/batches/*/state.json`` when the DB
    is unavailable or when the flag is off.
    """
    repo = _get_read_repo()
    if repo is not None:
        try:
            rows = repo.list_all_batches()
            if rows:
                return rows
        except Exception as e:
            logger.warning("DB list_batches failed, falling back to JSON: %s", e)
    return _list_batches_from_json()


def _list_batches_from_json() -> list[dict[str, Any]]:
    base = DATA_DIR / "batches"
    if not base.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        sp = d / "state.json"
        s = read_json(sp)
        if not s:
            continue
        out.append({
            "batch_id": s.get("batch_id") or d.name,
            "title": s.get("title") or s.get("batch_id") or d.name,
            "status": s.get("status"),
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
            "documents_count": len(s.get("documents") or []),
            "pair_runs_count": len(s.get("pairs") or []),
            "diff_events_count": 0,
        })
    return out


def _merge_db_with_json(db_state: dict[str, Any], json_state: dict[str, Any]) -> dict[str, Any]:
    """Combine a DB-backed state dict with JSON-only fields.

    DB rows are authoritative for ``documents``, ``pair_runs``,
    ``diff_events`` and ``artifacts``; JSON is authoritative for
    ``config``, ``runs``, ``metrics`` and per-document file paths the
    DB schema does not yet carry (``raw_path``, ``canonical_pdf``,
    ``extracted_json``, ``block_count``).
    """
    merged = dict(db_state)
    # Restore JSON-only top-level fields.
    for k in ("config", "runs", "metrics"):
        if k in json_state:
            merged[k] = json_state[k]

    # Backfill per-document paths from the JSON.
    docs_by_id = {d.get("doc_id"): d for d in json_state.get("documents", [])}
    for doc in merged.get("documents", []):
        j = docs_by_id.get(doc.get("doc_id"))
        if not j:
            continue
        for k in ("raw_path", "canonical_pdf", "extracted_json", "block_count", "title"):
            if j.get(k) is not None:
                doc[k] = j[k]
    return merged


def save_state(batch_id: str, state: dict[str, Any]) -> None:
    state["updated_at"] = now_ts()
    if _write_json_state():
        write_json(state_path(batch_id), state)


def register_source_for_url(
    url: str,
    rank: int,
    doc_type: str,
    repo: Any | None = None,
) -> None:
    """PR-1.5: best-effort dual-write of a registry row.

    The upload endpoint calls this after classify() returns. JSON state
    has no equivalent table — the registry is DB-only. Failures are
    logged and swallowed so the JSON write path stays authoritative.
    """
    db_repo = repo if repo is not None else _get_repo()
    if db_repo is None:
        return
    try:
        db_repo.register_source(url=url, rank=rank, doc_type=doc_type)
    except Exception as e:
        logger.warning("DB register_source failed: %s", e)


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
