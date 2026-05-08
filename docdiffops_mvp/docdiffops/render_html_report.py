"""Standalone HTML report (PR-2.5).

One self-contained HTML file with inline CSS so a reviewer can open it
without a server. Includes a filterable events table, source inventory,
and pair matrix. No external assets, no JS frameworks — vanilla JS for
the filter input and severity/status chip styling.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


_STYLE = """
:root {
  --bg: #0f1115; --fg: #e9eef5; --mute: #95a3b8; --line: #1f2632;
  --green: #2ec27e; --red: #e5484d; --amber: #ffb224; --blue: #4cc3ff; --gray: #5b6473;
  --row: #161a22; --row-alt: #11141b; --hi: #ffd60a;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 14px/1.45 -apple-system, system-ui, "Segoe UI", Inter, sans-serif; }
header { padding: 24px 32px; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--bg); z-index: 10; }
header h1 { margin: 0 0 4px; font-size: 22px; }
header .sub { color: var(--mute); font-size: 13px; }
nav { padding: 0 32px; display: flex; gap: 16px; border-bottom: 1px solid var(--line); background: var(--bg); position: sticky; top: 70px; z-index: 9; }
nav a { color: var(--mute); padding: 12px 0; text-decoration: none; border-bottom: 2px solid transparent; }
nav a:hover, nav a.active { color: var(--fg); border-color: var(--blue); }
main { padding: 24px 32px 80px; max-width: 1400px; margin: 0 auto; }
section { margin-bottom: 40px; }
section h2 { font-size: 16px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--mute); border-bottom: 1px solid var(--line); padding-bottom: 8px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }
.kpi { background: var(--row); border: 1px solid var(--line); border-radius: 6px; padding: 12px; }
.kpi .v { font-size: 22px; font-weight: 600; }
.kpi .l { font-size: 11px; color: var(--mute); text-transform: uppercase; letter-spacing: 0.05em; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
th { text-align: left; background: var(--row-alt); padding: 8px 10px; border-bottom: 1px solid var(--line); position: sticky; top: 100px; cursor: pointer; }
td { padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
tr:nth-child(even) td { background: var(--row-alt); }
tr:hover td { background: #1c222d; }
.chip { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; letter-spacing: 0.04em; }
.chip-same { background: rgba(46,194,126,0.15); color: var(--green); }
.chip-added { background: rgba(76,195,255,0.15); color: var(--blue); }
.chip-deleted { background: rgba(229,72,77,0.15); color: var(--red); }
.chip-modified, .chip-partial { background: rgba(255,178,36,0.15); color: var(--amber); }
.chip-contradicts, .chip-manual_review { background: rgba(229,72,77,0.18); color: var(--red); }
.chip-high { background: rgba(229,72,77,0.18); color: var(--red); }
.chip-medium { background: rgba(255,178,36,0.18); color: var(--amber); }
.chip-low { background: rgba(91,100,115,0.25); color: var(--mute); }
.quote { color: var(--mute); font-style: italic; max-width: 360px; word-wrap: break-word; }
.toolbar { display: flex; gap: 12px; margin: 8px 0 16px; flex-wrap: wrap; }
.toolbar input, .toolbar select { background: var(--row); border: 1px solid var(--line); color: var(--fg); padding: 6px 10px; border-radius: 4px; font: inherit; }
.toolbar input { flex: 1 1 280px; }
.empty { color: var(--mute); font-style: italic; padding: 16px; }
.foot { color: var(--mute); font-size: 11px; padding: 16px 32px; border-top: 1px solid var(--line); }
mark { background: var(--hi); color: #000; padding: 0 2px; border-radius: 2px; }
"""

_JS = """
function chip(text, cls) {
  const span = document.createElement('span');
  span.className = 'chip chip-' + cls;
  span.textContent = text;
  return span;
}
function setupFilter(tableId, inputId) {
  const input = document.getElementById(inputId);
  const tbody = document.querySelector('#' + tableId + ' tbody');
  if (!input || !tbody) return;
  const sevSel = document.getElementById(inputId + '-sev');
  const statSel = document.getElementById(inputId + '-stat');
  function apply() {
    const q = input.value.toLowerCase().trim();
    const sev = sevSel ? sevSel.value : '';
    const stat = statSel ? statSel.value : '';
    let visible = 0;
    for (const tr of tbody.rows) {
      const txt = tr.dataset.search || tr.textContent.toLowerCase();
      const okQ = !q || txt.indexOf(q) >= 0;
      const okSev = !sev || tr.dataset.sev === sev;
      const okStat = !stat || tr.dataset.stat === stat;
      const show = okQ && okSev && okStat;
      tr.style.display = show ? '' : 'none';
      if (show) visible++;
    }
    const counter = document.getElementById(inputId + '-count');
    if (counter) counter.textContent = visible + ' visible';
  }
  input.addEventListener('input', apply);
  if (sevSel) sevSel.addEventListener('change', apply);
  if (statSel) statSel.addEventListener('change', apply);
}
document.addEventListener('DOMContentLoaded', () => setupFilter('events', 'q'));
"""


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return html.escape(str(s), quote=False)


def render_html_report(
    out_path: Path,
    state: dict[str, Any],
    all_events: list[dict[str, Any]],
    pair_summaries: list[dict[str, Any]],
) -> Path:
    """Render a self-contained HTML report at ``out_path``."""
    docs = state.get("documents", [])
    title = state.get("title") or state["batch_id"]
    high = [e for e in all_events if e.get("severity") == "high"]
    review = [e for e in all_events if e.get("review_required")]
    extract_hits = sum(1 for d in docs if d.get("cache_extract_hit"))
    compare_hits = sum(1 for p in (pair_summaries or []) if p.get("cache_hit"))

    kpis = [
        ("Documents", len(docs)),
        ("Pair runs", len(pair_summaries or [])),
        ("Events", len(all_events)),
        ("High risk", len(high)),
        ("Review required", len(review)),
        (
            "Cache hits",
            f"{extract_hits + compare_hits}/{len(docs) + len(pair_summaries or [])}",
        ),
    ]

    parts: list[str] = []
    parts.append("<!doctype html><html lang='ru'><head><meta charset='utf-8'>")
    parts.append(f"<title>{_esc(title)} — DocDiffOps</title>")
    parts.append(f"<style>{_STYLE}</style>")
    parts.append("</head><body>")
    parts.append(
        f"<header><h1>{_esc(title)}</h1>"
        f"<div class='sub'>batch_id: <code>{_esc(state['batch_id'])}</code></div></header>"
    )
    parts.append(
        "<nav><a href='#summary' class='active'>Сводка</a>"
        "<a href='#events'>События</a><a href='#docs'>Документы</a>"
        "<a href='#pairs'>Пары</a></nav>"
    )
    parts.append("<main>")

    # Summary
    parts.append("<section id='summary'><h2>Сводка</h2><div class='kpis'>")
    for label, value in kpis:
        parts.append(
            f"<div class='kpi'><div class='v'>{_esc(value)}</div>"
            f"<div class='l'>{_esc(label)}</div></div>"
        )
    parts.append("</div></section>")

    # Events table
    parts.append("<section id='events'><h2>События</h2>")
    parts.append(
        "<div class='toolbar'>"
        "<input id='q' placeholder='Filter (text, doc_id, quote)…'>"
        "<select id='q-sev'><option value=''>severity (all)</option>"
        "<option>high</option><option>medium</option><option>low</option></select>"
        "<select id='q-stat'><option value=''>status (all)</option>"
        "<option>same</option><option>partial</option><option>modified</option>"
        "<option>added</option><option>deleted</option><option>contradicts</option>"
        "<option>manual_review</option></select>"
        f"<span id='q-count'>{len(all_events)} visible</span>"
        "</div>"
    )
    parts.append(
        "<table id='events'><thead><tr>"
        "<th>event_id</th><th>pair</th><th>status</th><th>severity</th>"
        "<th>conf</th><th>LHS quote</th><th>RHS quote</th>"
        "</tr></thead><tbody>"
    )
    for e in all_events[:5000]:  # safety cap
        lhs = e.get("lhs") or {}
        rhs = e.get("rhs") or {}
        sev = (e.get("severity") or "low").lower()
        stat = (e.get("status") or "").lower()
        search = " ".join([
            str(e.get("event_id") or ""),
            str(e.get("lhs_doc_id") or ""),
            str(e.get("rhs_doc_id") or ""),
            str(lhs.get("quote") or ""),
            str(rhs.get("quote") or ""),
        ]).lower()
        parts.append(
            f"<tr data-sev='{_esc(sev)}' data-stat='{_esc(stat)}' "
            f"data-search='{_esc(search)}'>"
            f"<td><code>{_esc(e.get('event_id'))}</code></td>"
            f"<td><code>{_esc(e.get('pair_id'))}</code></td>"
            f"<td><span class='chip chip-{_esc(stat)}'>{_esc(stat)}</span></td>"
            f"<td><span class='chip chip-{_esc(sev)}'>{_esc(sev)}</span></td>"
            f"<td>{_esc(e.get('confidence'))}</td>"
            f"<td class='quote'>{_esc(lhs.get('quote'))}</td>"
            f"<td class='quote'>{_esc(rhs.get('quote'))}</td>"
            "</tr>"
        )
    if not all_events:
        parts.append("<tr><td colspan='7' class='empty'>(нет событий)</td></tr>")
    parts.append("</tbody></table></section>")

    # Documents
    parts.append("<section id='docs'><h2>Документы</h2>")
    parts.append(
        "<table><thead><tr>"
        "<th>doc_id</th><th>filename</th><th>doc_type</th><th>rank</th>"
        "<th>sha256</th><th>blocks</th><th>cache</th>"
        "</tr></thead><tbody>"
    )
    for d in docs:
        parts.append(
            "<tr>"
            f"<td><code>{_esc(d.get('doc_id'))}</code></td>"
            f"<td>{_esc(d.get('filename'))}</td>"
            f"<td>{_esc(d.get('doc_type'))}</td>"
            f"<td>{_esc(d.get('source_rank'))}</td>"
            f"<td><code>{_esc((d.get('sha256') or '')[:12])}…</code></td>"
            f"<td>{_esc(d.get('block_count'))}</td>"
            f"<td>{'hit' if d.get('cache_extract_hit') else '—'}</td>"
            "</tr>"
        )
    parts.append("</tbody></table></section>")

    # Pairs
    parts.append("<section id='pairs'><h2>Пары</h2>")
    parts.append(
        "<table><thead><tr>"
        "<th>pair_id</th><th>LHS</th><th>RHS</th><th>events</th>"
        "<th>partial</th><th>added</th><th>deleted</th><th>cache</th>"
        "</tr></thead><tbody>"
    )
    for s in pair_summaries or []:
        parts.append(
            "<tr>"
            f"<td><code>{_esc(s.get('pair_id'))}</code></td>"
            f"<td><code>{_esc(s.get('lhs_doc_id'))}</code></td>"
            f"<td><code>{_esc(s.get('rhs_doc_id'))}</code></td>"
            f"<td>{_esc(s.get('events_total'))}</td>"
            f"<td>{_esc(s.get('partial_count'))}</td>"
            f"<td>{_esc(s.get('added_count'))}</td>"
            f"<td>{_esc(s.get('deleted_count'))}</td>"
            f"<td>{'hit' if s.get('cache_hit') else '—'}</td>"
            "</tr>"
        )
    parts.append("</tbody></table></section>")

    parts.append("</main>")
    parts.append(
        "<div class='foot'>Generated by DocDiffOps · "
        f"events={len(all_events)} · pairs={len(pair_summaries or [])}</div>"
    )
    parts.append(f"<script>{_JS}</script></body></html>")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(parts), encoding="utf-8")
    return out_path
