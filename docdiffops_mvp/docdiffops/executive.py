from __future__ import annotations

from pathlib import Path
from typing import Any


def render_executive_md(out_path: Path, state: dict[str, Any], all_events: list[dict[str, Any]], pair_summaries: list[dict[str, Any]]) -> Path:
    high = [e for e in all_events if e.get("severity") == "high"]
    review = [e for e in all_events if e.get("review_required")]
    partial = [e for e in all_events if e.get("status") == "partial"]
    added = [e for e in all_events if e.get("status") == "added"]
    deleted = [e for e in all_events if e.get("status") == "deleted"]

    lines = []
    lines.append(f"# Executive diff: {state.get('title') or state['batch_id']}")
    lines.append("")
    lines.append("## Сводка")
    lines.append("")
    lines.append(f"- Документов: **{len(state.get('documents', []))}**")
    lines.append(f"- Пар сравнения: **{len(pair_summaries)}**")
    lines.append(f"- Diff-событий: **{len(all_events)}**")
    lines.append(f"- High risk: **{len(high)}**")
    lines.append(f"- Требуют проверки: **{len(review)}**")
    lines.append(f"- Added: **{len(added)}**, Deleted: **{len(deleted)}**, Partial: **{len(partial)}**")
    lines.append("")
    lines.append("## Топ high-risk событий")
    lines.append("")
    for e in high[:20]:
        lhs = e.get("lhs") or {}
        rhs = e.get("rhs") or {}
        lines.append(f"### {e.get('event_id')} — {e.get('status')} / {e.get('severity')}")
        lines.append(f"- Пара: `{e.get('lhs_doc_id')}` ↔ `{e.get('rhs_doc_id')}`")
        lines.append(f"- Score: `{e.get('score')}`")
        if lhs.get("quote"):
            lines.append(f"- LHS p.{lhs.get('page_no')}: {lhs.get('quote')}")
        if rhs.get("quote"):
            lines.append(f"- RHS p.{rhs.get('page_no')}: {rhs.get('quote')}")
        lines.append(f"- Пояснение: {e.get('explanation_short')}")
        lines.append("")
    lines.append("## Артефакты")
    lines.append("")
    for a in state.get("artifacts", []):
        lines.append(f"- `{a.get('type')}`: `{a.get('path')}`")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
