"""Content-addressed cache for extract / compare stages (PR-1.6).

Cache key formula (locked):
    cache_key = sha256("|".join([
        scope,                      # 'extract' | 'compare' | 'normalize'
        version,                    # EXTRACTOR_VERSION | COMPARATOR_VERSION
        *content_sha256s_sorted,    # one or more upstream content hashes
    ]))

The key is deterministic across processes and re-runs. Two batches that
upload the same PDF (same sha256) produce the same extract cache key, so
the second run reads the JSON from cache instead of re-parsing.

Storage backend is whatever ``get_storage()`` returns; entries live under
``cache/{scope}/{cache_key}.json``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from .settings import COMPARATOR_VERSION, EXTRACTOR_VERSION
from .storage import get_storage

_CACHE_PREFIX = "cache"


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------


def make_key(scope: str, version: str, *content_sha256s: str) -> str:
    """Return the deterministic cache key for ``scope`` + ``version`` + inputs.

    Inputs are sorted before hashing so caller order doesn't matter
    (LHS/RHS of a pair produces the same key as RHS/LHS).
    """
    if not scope or "|" in scope:
        raise ValueError(f"invalid scope: {scope!r}")
    if not version:
        raise ValueError("version is required")
    if not content_sha256s:
        raise ValueError("at least one content sha256 is required")
    parts = [scope, version, *sorted(content_sha256s)]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def extract_key(content_sha256: str) -> str:
    """Cache key for a single-document extract result."""
    return make_key("extract", EXTRACTOR_VERSION, content_sha256)


def compare_key(lhs_sha: str, rhs_sha: str) -> str:
    """Cache key for a pair compare result. Order-independent."""
    return make_key("compare", COMPARATOR_VERSION, lhs_sha, rhs_sha)


# ---------------------------------------------------------------------------
# Storage I/O
# ---------------------------------------------------------------------------


def _path(scope: str, key: str) -> str:
    return f"{_CACHE_PREFIX}/{scope}/{key}.json"


def get(scope: str, key: str) -> Any | None:
    """Return cached value for ``(scope, key)`` or ``None`` if absent."""
    storage = get_storage()
    path = _path(scope, key)
    if not storage.exists(path):
        return None
    return json.loads(storage.get_bytes(path).decode("utf-8"))


def put(scope: str, key: str, value: Any) -> None:
    """Persist ``value`` (JSON-serializable) under ``(scope, key)``."""
    storage = get_storage()
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    )
    storage.put_bytes(_path(scope, key), payload, content_type="application/json")


def get_or_compute(
    scope: str, key: str, compute: Callable[[], Any]
) -> tuple[Any, bool]:
    """Return ``(value, cache_hit)``.

    On miss, ``compute()`` runs and the result is persisted. On hit, the
    cached JSON is returned without invoking ``compute``.
    """
    cached = get(scope, key)
    if cached is not None:
        return cached, True
    value = compute()
    put(scope, key, value)
    return value, False


def invalidate(scope: str, key: str) -> None:
    """Delete the cached entry. No-op if absent."""
    get_storage().delete(_path(scope, key))


def list_scope(scope: str) -> list[str]:
    """Return all cache keys present under ``scope``. Sorted."""
    storage = get_storage()
    prefix = f"{_CACHE_PREFIX}/{scope}/"
    paths = storage.list_prefix(prefix)
    out = []
    for p in paths:
        if p.startswith(prefix) and p.endswith(".json"):
            out.append(p[len(prefix) : -len(".json")])
    return sorted(out)
