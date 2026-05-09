"""CSV exports for forensic v8 bundles, deltas, and trends.

Pure functions — write a single CSV file each. Russian column headers.
UTF-8 with BOM (``\\ufeff``) so Excel opens Cyrillic correctly without manual encoding.

Available exports:
  * ``export_pairs_csv(bundle, out)``         — pairs from a v8 bundle
  * ``export_documents_csv(bundle, out)``     — registry of documents
  * ``export_actions_csv(bundle, out)``       — actions catalogue + RACI
  * ``export_status_changes_csv(delta, out)`` — pair status shifts from a delta
  * ``export_distribution_diff_csv(delta, out)`` — distribution delta
  * ``export_trend_timeline_csv(trend, out)`` — per-bundle trend timeline
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

from .forensic_render import STATUS_RU


def _open_csv(out_path: Path | str) -> tuple[Any, Any]:
    """Open a UTF-8-with-BOM CSV file for Excel-friendly Cyrillic rendering."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(out_path, "w", encoding="utf-8-sig", newline="")
    return f, csv.writer(f, dialect="excel", quoting=csv.QUOTE_MINIMAL)


# ---------------------------------------------------------------------------
# Bundle exports
# ---------------------------------------------------------------------------


def export_pairs_csv(bundle: Mapping[str, Any], out_path: Path | str) -> None:
    """Write all pairs from a v8 bundle as CSV with Russian column names."""
    f, w = _open_csv(out_path)
    try:
        w.writerow([
            "ИД пары", "Слева", "Справа", "Ранг слева", "Ранг справа",
            "Статус (код)", "Статус (русский)", "Знак", "Темы",
            "Обоснование", "Действия", "Рангов. пара", "Событий",
        ])
        from .forensic import STATUS_TO_MARK
        for p in bundle.get("pairs", []):
            st = p.get("v8_status", "")
            w.writerow([
                p.get("id", ""), p.get("left", ""), p.get("right", ""),
                p.get("left_rank", ""), p.get("right_rank", ""),
                st, STATUS_RU.get(st, st), STATUS_TO_MARK.get(st, ""),
                "; ".join(p.get("topics", [])),
                "; ".join(p.get("explanations", [])),
                ", ".join(p.get("actions", [])),
                p.get("rank_pair", ""), p.get("events_count", 0),
            ])
    finally:
        f.close()


def export_documents_csv(bundle: Mapping[str, Any], out_path: Path | str) -> None:
    """Write the source document registry as CSV."""
    f, w = _open_csv(out_path)
    try:
        w.writerow(["ИД", "Код", "Название", "Тип", "Ранг", "URL"])
        for d in bundle.get("documents", []):
            w.writerow([
                d.get("id", ""), d.get("code", ""), d.get("title", ""),
                d.get("type", ""), d.get("rank", ""), d.get("url", ""),
            ])
    finally:
        f.close()


def export_actions_csv(bundle: Mapping[str, Any], out_path: Path | str) -> None:
    """Write the actions catalogue with RACI columns."""
    f, w = _open_csv(out_path)
    try:
        w.writerow([
            "ИД", "Категория", "Уровень", "Где", "Что не так", "Почему",
            "Что делать", "Ответственный",
            "R", "A", "C", "I", "Связанные документы", "Статус v8",
        ])
        for a in bundle.get("actions_catalogue", []) or []:
            raci = a.get("raci") or {}
            w.writerow([
                a.get("id", ""), a.get("category", ""), a.get("severity", ""),
                a.get("where", ""), a.get("what_is_wrong", ""), a.get("why", ""),
                a.get("what_to_do", ""), a.get("owner", ""),
                raci.get("R", ""), raci.get("A", ""),
                raci.get("C", ""), raci.get("I", ""),
                ", ".join(a.get("related_docs", [])),
                a.get("v8_status", ""),
            ])
    finally:
        f.close()


# ---------------------------------------------------------------------------
# Delta exports
# ---------------------------------------------------------------------------


def export_status_changes_csv(delta: Mapping[str, Any], out_path: Path | str) -> None:
    """Write pair-level status shifts from a delta report."""
    from .forensic_delta_render import DIRECTION_RU
    f, w = _open_csv(out_path)
    try:
        w.writerow([
            "ИД пары", "Слева", "Справа",
            "Было (код)", "Было (русский)",
            "Стало (код)", "Стало (русский)",
            "Направление (код)", "Направление (русский)",
        ])
        for ch in delta.get("status_changes", []):
            old = ch.get("old_status", "")
            new = ch.get("new_status", "")
            d = ch.get("direction", "")
            w.writerow([
                ch.get("pair_id", ""),
                ch.get("left_id", ""), ch.get("right_id", ""),
                old, STATUS_RU.get(old, old),
                new, STATUS_RU.get(new, new),
                d, DIRECTION_RU.get(d, d),
            ])
    finally:
        f.close()


def export_distribution_diff_csv(delta: Mapping[str, Any], out_path: Path | str) -> None:
    """Write distribution-diff (per-status delta count) as CSV."""
    f, w = _open_csv(out_path)
    try:
        w.writerow(["Статус (код)", "Статус (русский)", "Δ"])
        for st, d in sorted((delta.get("distribution_diff") or {}).items(),
                            key=lambda kv: -abs(kv[1])):
            w.writerow([st, STATUS_RU.get(st, st), f"{d:+d}"])
    finally:
        f.close()


# ---------------------------------------------------------------------------
# Trend exports
# ---------------------------------------------------------------------------


def export_trend_timeline_csv(trend: Mapping[str, Any], out_path: Path | str) -> None:
    """Write trend timeline as CSV — one row per bundle in chronological order."""
    f, w = _open_csv(out_path)
    try:
        w.writerow([
            "Индекс", "Дата создания", "Версия схемы",
            "Пар (всего)", "Совпадений", "Противоречий",
            "Ручная проверка", "Частичных", "Устаревших",
            "Пробел источника", "Несопоставимо",
            "Доля совпадений (%)",
        ])
        for snap in trend.get("timeline", []):
            w.writerow([
                snap.get("index", ""),
                snap.get("generated_at", ""),
                snap.get("schema_version", ""),
                snap.get("pairs_total", 0),
                snap.get("pairs_match", 0),
                snap.get("pairs_contradiction", 0),
                snap.get("pairs_manual_review", 0),
                snap.get("pairs_partial", 0),
                snap.get("pairs_outdated", 0),
                snap.get("pairs_source_gap", 0),
                snap.get("pairs_not_comparable", 0),
                snap.get("match_share", 0),
            ])
    finally:
        f.close()


__all__ = [
    "export_pairs_csv",
    "export_documents_csv",
    "export_actions_csv",
    "export_status_changes_csv",
    "export_distribution_diff_csv",
    "export_trend_timeline_csv",
]
