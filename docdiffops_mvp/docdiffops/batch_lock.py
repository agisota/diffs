"""Per-batch advisory lock backed by Redis SETNX with TTL.

Prevents concurrent long-running tasks (run_batch, rerender_compare,
rerender_full) on the same batch_id. Lock auto-expires after 2h to
avoid permanently stuck batches if the worker crashes.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

import redis

from .settings import REDIS_URL

logger = logging.getLogger(__name__)

_LOCK_TTL_SEC = int(os.getenv("BATCH_LOCK_TTL_SEC", str(2 * 60 * 60)))
_DISABLED = os.getenv("BATCH_LOCK_DISABLED", "false").lower() == "true"

_client: redis.Redis | None = None


def _get_client() -> redis.Redis | None:
    global _client
    if _client is not None:
        return _client
    try:
        c = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1.0)
        c.ping()
        _client = c
        return c
    except Exception as e:
        logger.warning("batch_lock: Redis unavailable, disabling: %s", e)
        return None


def _key(batch_id: str) -> str:
    return f"batchlock:{batch_id}"


def try_acquire(batch_id: str, task_id: str | None = None) -> bool:
    """Atomic SETNX. Returns True if acquired (lock now owned), False if already held."""
    if _DISABLED:
        return True
    client = _get_client()
    if client is None:
        return True  # Fail-open if Redis is down
    try:
        return bool(client.set(_key(batch_id), task_id or "1", nx=True, ex=_LOCK_TTL_SEC))
    except Exception as e:
        logger.warning("batch_lock: try_acquire failed for %s: %s", batch_id, e)
        return True


def release(batch_id: str) -> None:
    if _DISABLED:
        return
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(_key(batch_id))
    except Exception as e:
        logger.warning("batch_lock: release failed for %s: %s", batch_id, e)


def current_holder(batch_id: str) -> str | None:
    if _DISABLED:
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        v = client.get(_key(batch_id))
        return v if v else None
    except Exception:
        return None


@contextmanager
def acquired(batch_id: str, task_id: str | None = None) -> Iterator[bool]:
    """Context manager — auto-release on exit even on exception."""
    ok = try_acquire(batch_id, task_id)
    try:
        yield ok
    finally:
        if ok:
            release(batch_id)
