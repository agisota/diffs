"""Storage protocol + FS backend.

The S3/MinIO backend (``S3Storage``) lands in PR-1.4b. ``get_storage``
already reads ``STORAGE_BACKEND`` so flipping the default later is one
line. ``FSStorage`` is the only working backend in this PR; selecting
``minio`` raises ``NotImplementedError`` until PR-1.4b.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..settings import DATA_DIR


class Storage(Protocol):
    """Minimal blob storage protocol used by pipeline + renderers.

    Implementations are stateless: each call opens its own resource. All
    keys are forward-slash-joined paths (no leading slash). Implementations
    MAY persist files under any prefix scheme as long as ``get_bytes`` /
    ``list_prefix`` round-trip whatever ``put_bytes`` wrote.
    """

    def put_bytes(
        self, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        """Write ``data`` at ``key``. Returns the sha256 hex digest."""

    def get_bytes(self, key: str) -> bytes:
        """Read all bytes at ``key``. Raises ``FileNotFoundError`` if absent."""

    def exists(self, key: str) -> bool:
        """True if a blob exists at ``key``."""

    def delete(self, key: str) -> None:
        """Remove the blob. No-op when ``key`` does not exist."""

    def list_prefix(self, prefix: str) -> list[str]:
        """Return all keys whose path starts with ``prefix``. Sorted."""

    def stat(self, key: str) -> dict:
        """Return ``{size, sha256, modified_at}``. Raises if absent."""

    def presigned_url(
        self, key: str, expires_seconds: int = 3600
    ) -> str | None:
        """Return a time-limited URL or ``None`` if backend doesn't support it."""


class FSStorage:
    """Local filesystem backend rooted at ``DATA_DIR``.

    Writes are atomic (write-temp + rename). Keys are joined under the
    root verbatim; callers MUST NOT use absolute paths or `..` segments.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else Path(DATA_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- key→path helpers ------------------------------------------------

    def _resolve(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"invalid storage key: {key!r}")
        return self.root / key

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    # ---- protocol --------------------------------------------------------

    def put_bytes(
        self, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return self._sha256(data)

    def get_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink()
        except FileNotFoundError:
            pass

    def list_prefix(self, prefix: str) -> list[str]:
        if prefix and (prefix.startswith("/") or ".." in prefix.split("/")):
            raise ValueError(f"invalid prefix: {prefix!r}")
        base = self.root / prefix if prefix else self.root
        if not base.exists():
            return []
        if base.is_file():
            return [str(base.relative_to(self.root))]
        return sorted(
            str(p.relative_to(self.root))
            for p in base.rglob("*")
            if p.is_file()
        )

    def stat(self, key: str) -> dict:
        path = self._resolve(key)
        st = path.stat()
        return {
            "size": st.st_size,
            "sha256": self._sha256(path.read_bytes()),
            "modified_at": datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
        }

    def presigned_url(
        self, key: str, expires_seconds: int = 3600
    ) -> str | None:
        return None  # FS doesn't support presigned URLs


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_STORAGE_INSTANCE: Storage | None = None


def get_storage() -> Storage:
    """Return a process-wide ``Storage`` instance based on env.

    ``STORAGE_BACKEND`` ∈ {``fs``, ``minio``}. Default is ``fs``.
    The instance is cached so subsequent calls return the same object.
    """
    global _STORAGE_INSTANCE
    if _STORAGE_INSTANCE is not None:
        return _STORAGE_INSTANCE

    backend = os.getenv("STORAGE_BACKEND", "fs").lower()
    if backend == "fs":
        _STORAGE_INSTANCE = FSStorage()
    elif backend == "minio" or backend == "s3":
        raise NotImplementedError(
            "S3/MinIO backend lands in PR-1.4b; set STORAGE_BACKEND=fs"
        )
    else:
        raise ValueError(f"unknown STORAGE_BACKEND: {backend!r}")
    return _STORAGE_INSTANCE


def reset_storage_for_tests() -> None:
    """Clear the cached singleton. Test fixtures only."""
    global _STORAGE_INSTANCE
    _STORAGE_INSTANCE = None
