"""Cache + batch prune CLI (PR-5.4).

Removes batches and cache entries older than ``RETENTION_DAYS`` (Q3
closure: 30 days uniform). Designed for a daily cron / systemd timer.
Idempotent — safe to run multiple times.

Usage:

    python -m docdiffops.cli_prune              # use env defaults
    python -m docdiffops.cli_prune --days 7     # override
    python -m docdiffops.cli_prune --dry-run    # report only

Exit codes: 0 on success, 2 on partial failure (some deletes raised),
1 on hard error before any work.
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from pathlib import Path

from .settings import DATA_DIR

logger = logging.getLogger("docdiffops.prune")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _is_older_than(p: Path, cutoff: float) -> bool:
    try:
        return p.stat().st_mtime < cutoff
    except OSError:
        return False


def prune_cache(root: Path, cutoff: float, *, dry_run: bool = False) -> tuple[int, int]:
    """Remove cache/{scope}/{key}.json files older than cutoff.

    Returns ``(removed, kept)``.
    """
    cache_dir = root / "cache"
    if not cache_dir.exists():
        return 0, 0
    removed = kept = 0
    for entry in cache_dir.rglob("*.json"):
        if _is_older_than(entry, cutoff):
            logger.info("prune cache: %s", entry.relative_to(root))
            if not dry_run:
                try:
                    entry.unlink()
                except OSError as e:
                    logger.warning("could not remove %s: %s", entry, e)
                    continue
            removed += 1
        else:
            kept += 1
    return removed, kept


def prune_batches(root: Path, cutoff: float, *, dry_run: bool = False) -> tuple[int, int]:
    """Remove batches/{batch_id}/ directories older than cutoff.

    Returns ``(removed, kept)``. Decision based on the directory's
    ``state.json`` mtime (or directory mtime if absent).
    """
    batches_dir = root / "batches"
    if not batches_dir.exists():
        return 0, 0
    removed = kept = 0
    for d in sorted(batches_dir.iterdir()):
        if not d.is_dir():
            continue
        ref = d / "state.json"
        ref = ref if ref.exists() else d
        if _is_older_than(ref, cutoff):
            logger.info("prune batch: %s", d.name)
            if not dry_run:
                try:
                    shutil.rmtree(d)
                except OSError as e:
                    logger.warning("could not remove %s: %s", d, e)
                    continue
            removed += 1
        else:
            kept += 1
    return removed, kept


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DocDiffOps cache + batch prune (PR-5.4)")
    p.add_argument(
        "--days",
        type=int,
        default=int(os.getenv("RETENTION_DAYS", "30")),
        help="Retain entries newer than N days (default 30 / RETENTION_DAYS env)",
    )
    p.add_argument("--root", type=Path, default=Path(DATA_DIR), help="Data dir root")
    p.add_argument("--dry-run", action="store_true", help="Report only; don't delete")
    p.add_argument("--cache-only", action="store_true", help="Skip batch dirs")
    p.add_argument("--batches-only", action="store_true", help="Skip cache files")
    args = p.parse_args(argv)

    if args.days < 1:
        logger.error("--days must be ≥ 1")
        return 1

    cutoff = time.time() - args.days * 86400
    logger.info(
        "prune root=%s cutoff=%d days dry_run=%s",
        args.root, args.days, args.dry_run,
    )

    cache_removed = cache_kept = 0
    batch_removed = batch_kept = 0

    if not args.batches_only:
        cache_removed, cache_kept = prune_cache(args.root, cutoff, dry_run=args.dry_run)
        logger.info("cache: removed=%d kept=%d", cache_removed, cache_kept)

    if not args.cache_only:
        batch_removed, batch_kept = prune_batches(args.root, cutoff, dry_run=args.dry_run)
        logger.info("batches: removed=%d kept=%d", batch_removed, batch_kept)

    print(
        f"prune done: cache_removed={cache_removed} batches_removed={batch_removed} "
        f"days={args.days} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
