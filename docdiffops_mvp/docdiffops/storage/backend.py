"""Storage protocol + FS/S3 backends.

PR-1.4 introduced the Storage protocol with ``FSStorage``. PR-1.4b adds
``S3Storage`` (boto3, MinIO-compatible) and wires ``get_storage`` to
return it when ``STORAGE_BACKEND`` is ``minio`` or ``s3``. The default
remains ``fs`` so production behavior is unchanged.
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


class S3Storage:
    """S3 / MinIO-compatible backend (boto3).

    Configuration is read from environment variables on instantiation:

    - ``S3_ENDPOINT_URL`` (optional; ``None`` for real AWS S3)
    - ``S3_ACCESS_KEY``
    - ``S3_SECRET_KEY``
    - ``S3_BUCKET``
    - ``S3_REGION`` (default ``us-east-1``)

    The bucket is verified / auto-created on first call. A single boto3
    client is reused per instance.
    """

    def __init__(
        self,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        # Lazy import: boto3 is only required when the S3 backend is
        # actually selected. Keeps test environments without boto3 happy.
        import boto3  # noqa: F401  (imported for side-effects via client)

        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL") or None
        self.access_key = access_key or os.getenv("S3_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("S3_SECRET_KEY")
        self.bucket = bucket or os.getenv("S3_BUCKET")
        self.region = region or os.getenv("S3_REGION", "us-east-1")

        if not self.bucket:
            raise ValueError("S3_BUCKET env var is required for S3Storage")

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )
        self._bucket_verified = False

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _ensure_bucket(self) -> None:
        if self._bucket_verified:
            return
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            status = e.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if code in ("404", "NoSuchBucket") or status == 404:
                try:
                    if self.region and self.region != "us-east-1":
                        self._client.create_bucket(
                            Bucket=self.bucket,
                            CreateBucketConfiguration={
                                "LocationConstraint": self.region
                            },
                        )
                    else:
                        self._client.create_bucket(Bucket=self.bucket)
                except ClientError as ce:
                    cc = ce.response.get("Error", {}).get("Code", "")
                    if cc not in (
                        "BucketAlreadyOwnedByYou",
                        "BucketAlreadyExists",
                    ):
                        raise
            else:
                raise
        self._bucket_verified = True

    @staticmethod
    def _validate_key(key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"invalid storage key: {key!r}")
        return key

    # ---- protocol --------------------------------------------------------

    def put_bytes(
        self, key: str, data: bytes, content_type: str | None = None
    ) -> str:
        self._ensure_bucket()
        key = self._validate_key(key)
        sha = self._sha256(data)
        kwargs: dict = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "Metadata": {"x-amz-meta-sha256": sha},
        }
        if content_type:
            kwargs["ContentType"] = content_type
        self._client.put_object(**kwargs)
        return sha

    def get_bytes(self, key: str) -> bytes:
        self._ensure_bucket()
        key = self._validate_key(key)
        from botocore.exceptions import ClientError

        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(key) from e
            raise
        return obj["Body"].read()

    def exists(self, key: str) -> bool:
        self._ensure_bucket()
        key = self._validate_key(key)
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            status = e.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if code in ("404", "NoSuchKey", "NotFound") or status == 404:
                return False
            raise

    def delete(self, key: str) -> None:
        self._ensure_bucket()
        key = self._validate_key(key)
        from botocore.exceptions import ClientError

        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                return
            raise

    def list_prefix(self, prefix: str) -> list[str]:
        self._ensure_bucket()
        if prefix and (prefix.startswith("/") or ".." in prefix.split("/")):
            raise ValueError(f"invalid prefix: {prefix!r}")
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                keys.append(obj["Key"])
        return sorted(keys)

    def stat(self, key: str) -> dict:
        """Return size/sha256/modified_at for ``key``.

        ``sha256`` is read from object metadata when present
        (``x-amz-meta-sha256``). When absent, falls back to a full
        GetObject + hash, which is slow for large objects.
        """
        self._ensure_bucket()
        key = self._validate_key(key)
        from botocore.exceptions import ClientError

        try:
            head = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            status = e.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if code in ("404", "NoSuchKey", "NotFound") or status == 404:
                raise FileNotFoundError(key) from e
            raise

        metadata = head.get("Metadata", {}) or {}
        sha = metadata.get("x-amz-meta-sha256") or metadata.get("sha256")
        if not sha:
            sha = self._sha256(self.get_bytes(key))
        size = head.get("ContentLength", 0)
        last_mod = head.get("LastModified")
        if last_mod is not None:
            if last_mod.tzinfo is None:
                last_mod = last_mod.replace(tzinfo=timezone.utc)
            modified_at = last_mod.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
        else:
            modified_at = datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
        return {"size": size, "sha256": sha, "modified_at": modified_at}

    def presigned_url(
        self, key: str, expires_seconds: int = 3600
    ) -> str | None:
        self._ensure_bucket()
        key = self._validate_key(key)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_STORAGE_INSTANCE: Storage | None = None


def get_storage() -> Storage:
    """Return a process-wide ``Storage`` instance based on env.

    ``STORAGE_BACKEND`` ∈ {``fs``, ``minio``, ``s3``}. Default is ``fs``.
    The instance is cached so subsequent calls return the same object.
    """
    global _STORAGE_INSTANCE
    if _STORAGE_INSTANCE is not None:
        return _STORAGE_INSTANCE

    backend = os.getenv("STORAGE_BACKEND", "fs").lower()
    if backend == "fs":
        _STORAGE_INSTANCE = FSStorage()
    elif backend in ("minio", "s3"):
        _STORAGE_INSTANCE = S3Storage()
    else:
        raise ValueError(f"unknown STORAGE_BACKEND: {backend!r}")
    return _STORAGE_INSTANCE


def reset_storage_for_tests() -> None:
    """Clear the cached singleton. Test fixtures only."""
    global _STORAGE_INSTANCE
    _STORAGE_INSTANCE = None
