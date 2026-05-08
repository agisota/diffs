"""Storage abstraction for DocDiffOps artifacts.

Backends are swappable behind a single ``Storage`` protocol so the
pipeline can write to local FS today and to S3/MinIO tomorrow without
caller changes. PR-1.4 ships the protocol and the FS backend; the
S3/MinIO backend lands in PR-1.4b.

Key naming convention (locked in PR-1.4):
    batches/{batch_id}/{stage}/{filename}
where ``stage`` ∈ {raw, normalized, extracted, pairs/{pair_id}, reports, cache}.
"""

from .backend import FSStorage, Storage, get_storage

__all__ = ["Storage", "FSStorage", "get_storage"]
