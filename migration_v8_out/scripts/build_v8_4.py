#!/usr/bin/env python3
"""v8.4 — interactive HTML report + SUMMARY.md + MASTER_INDEX.md with SHA-256.

Outputs:
  docs/Forensic_v8_report.html  — single-file, no deps, vanilla JS
  SUMMARY.md                    — markdown short summary
  MASTER_INDEX.md               — SHA-256 fingerprints + sizes of every artifact
  logs/qa_v8_4.json
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path("/home/dev/diff/migration_v8_out")
DATA = ROOT / "data"
DOCS = ROOT / "docs"
LOGS = ROOT / "logs"

GENERATED_AT = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

sys.path.insert(0, "/home/dev/diff/docdiffops_mvp")
from docdiffops.forensic_actions import DEFAULT_ACTIONS, raci_for_action  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(encoding="utf-8-sig"), delimiter=";"))


# ---------------------------------------------------------------------------
# 1. SUMMARY.md
# ---------------------------------------------------------------------------

def build_summary_md() -> Path:
    qa = json.loads((LOGS / "qa.json").read_text(encoding="utf-8"))
    cn = qa["control_numbers_actual"]
    sd = qa["status_distribution_pairs"]

    md = f"""# Forensic v8 — Summary

> Не является юридическим заключением. Evidence-grade сравнительная матрица.
> Сгенерировано: {GENERATED_AT}

## TL;DR

- **{cn['documents']} документов** мигр.политики РФ (Указы Президента, ФЗ, ПП, КоАП, НК, Договор ЕАЭС, ведомственные материалы Минэка, аналитика Клерка/ВЦИОМ).
- **{cn['pairs']} пар** (C(26,2)) сравнения; **{cn['events']} событий**.
- **{cn['manual_reviews']} элементов** ручной проверки, ожидают юриста.
- **3 финальных противоречия** (C-01..C-03), **3 source gaps** (U-01..U-03), **3 defect-flag** (D-001..D-003).
- **10 actionable FA-rules** (FA-01..FA-10), **6 brochure red→green правок**, **6 Klerk footnotes**, **3 ЕАЭС группы**, **5 amendment chains**.

## Распределение пар по v8-статусам

| Статус | Пар | % |
|---|---:|---:|
"""
    total = sum(sd.values()) or 1
    for st, c in sorted(sd.items(), key=lambda kv: -kv[1]):
        md += f"| `{st}` | {c} | {c * 100 / total:.1f}% |\n"
    md += f"| **Итого** | **{total}** | **100%** |\n"

    md += """
## 3 ключевых риска (top of mind)

1. **Брошюра Минэка ↔ ПП №2573** (FA-01 / BR-01..BR-06). Брошюра использует «более X», ПП говорит «не менее X». Инвестор с пороговой суммой формально выпадает из критерия. → 6 cells правки.
2. **Минэк «Работа в ЕАЭС»** включает Узбекистан/Таджикистан в один блок с государствами-членами ЕАЭС (FA-02). Граждане этих стран работают по 115-ФЗ через **патент**, не по ст.97 Договора ЕАЭС. → 3 группы split.
3. **Клерк (D09) — rank-3 без footnote** на 6 первичных НПА (FA-03 / KL-01..KL-06). Каждый тезис должен иметь ссылку на конкретную статью 115/109/КоАП/НК/Указа 467/ПП 1510.

## Иерархия источников (invariant)

- **rank-1** — НПА (D04..D08, D11..D17, D19..D26).
- **rank-2** — ведомственное Минэка (D10, D18).
- **rank-3** — аналитика (D01, D02, D03, D09).
- rank-3 не опровергает rank-1 → пересечение всегда `manual_review`.

## Что почитать дальше

- [`Forensic_v8_report.html`](docs/Forensic_v8_report.html) — interactive single-page report.
- [`Forensic_v8_cover.pdf`](docs/Forensic_v8_cover.pdf) — обложка с heatmap.
- [`Что_делать.pdf`](docs/Что_делать.pdf) — план действий FA-01..FA-10.
- [`Лист_согласования.pdf`](docs/Лист_согласования.pdf) — sign-off form для юриста.
- [`MASTER_INDEX.md`](MASTER_INDEX.md) — все артефакты с SHA-256.
- [`NAVIGATION.md`](NAVIGATION.md) — полный навигатор.
"""
    p = ROOT / "SUMMARY.md"
    p.write_text(md, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 2. MASTER_INDEX.md — SHA-256 of every artifact
# ---------------------------------------------------------------------------

def build_master_index() -> Path:
    rows: list[tuple[str, str, int]] = []
    for sub in ("docs", "data", "logs", "scripts"):
        d = ROOT / sub
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            try:
                sha = sha256_of(p)
                rows.append((str(p.relative_to(ROOT)), sha, p.stat().st_size))
            except Exception:
                continue
    # Top-level files
    for p in sorted(ROOT.glob("*")):
        if p.is_file():
            sha = sha256_of(p)
            rows.append((str(p.relative_to(ROOT)), sha, p.stat().st_size))

    md = f"""# MASTER INDEX — Forensic v8 пакет

Provenance-grade список всех артефактов с SHA-256 fingerprint.
Сгенерировано: {GENERATED_AT}

| Размер | SHA-256 (16) | Путь |
|---:|:---|:---|
"""
    for path, sha, size in sorted(rows):
        md += f"| {size:>9,} | `{sha[:16]}…` | `{path}` |\n"

    md += f"""

## Total

- **Файлов**: {len(rows)}
- **Совокупный размер**: {sum(r[2] for r in rows):,}b ({sum(r[2] for r in rows) / 1024 / 1024:.2f} MB)

## Re-verify

```bash
cd /home/dev/diff/migration_v8_out
python3 -c "import hashlib, sys; [print(hashlib.sha256(open(f, 'rb').read()).hexdigest()[:16], f) for f in sys.argv[1:]]" \\
  data/v8_bundle.schema.json data/integral_cross_comparison.json
```
"""
    p = ROOT / "MASTER_INDEX.md"
    p.write_text(md, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 3. Interactive HTML report (single file, no deps)
# ---------------------------------------------------------------------------

def build_html_report() -> Path:
    sources = read_csv(DATA / "01_источники_v8.csv")
    pairs = read_csv(DATA / "02_pairs_v8.csv")
    matrix = read_csv(DATA / "03_doc_x_doc_matrix.csv")
    actions = read_csv(DATA / "10_actions_catalogue.csv")
    brochure = read_csv(DATA / "11_brochure_redgreen_diff.csv")
    klerk = read_csv(DATA / "12_klerk_npa_links.csv")
    eaeu = read_csv(DATA / "13_eaeu_split.csv")
    amendments = read_csv(DATA / "14_amendment_chain.csv")
    top = read_csv(DATA / "16_top_priority_review.csv")
    raci = read_csv(DATA / "17_raci_matrix.csv")
    qa = json.loads((LOGS / "qa.json").read_text(encoding="utf-8"))

    # Pre-compute a JS-friendly pair lookup
    pair_lookup: dict[str, dict[str, Any]] = {}
    for p in pairs:
        key = "|".join(sorted([p["L"], p["R"]]))
        pair_lookup[key] = {
            "id": p["ИД пары"], "L": p["L"], "R": p["R"],
            "status": p["Статус v8"], "events": int(p["Кол-во событий"] or 0),
            "topics": p.get("Темы v8", ""),
            "basis": p.get("Основание", ""),
            "manual": p.get("Manual-review", "нет"),
            "lr_rank": f"{p.get('L-ранг','?')}—{p.get('R-ранг','?')}",
        }

    doc_codes = {s["ИД"]: s["Код"] for s in sources}
    doc_titles = {s["ИД"]: s["Название"] for s in sources}
    doc_ranks = {s["ИД"]: s["Ранг"] for s in sources}

    html_str = (
        '<!DOCTYPE html>\n<html lang="ru" data-theme="light">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<title>Forensic v8 — Interactive Report</title>\n'
        + _STYLE
        + '</head>\n<body>\n'
        + _HEADER.format(generated=html.escape(GENERATED_AT),
                         total_docs=qa["control_numbers_actual"]["documents"],
                         total_pairs=qa["control_numbers_actual"]["pairs"],
                         total_events=qa["control_numbers_actual"]["events"],
                         total_manual=qa["control_numbers_actual"]["manual_reviews"])
        + _LEGEND
        + _build_status_bar_html(qa["status_distribution_pairs"])
        + _build_matrix_html(sources, matrix, doc_codes, doc_titles, doc_ranks)
        + _build_actions_html(actions, raci)
        + _build_brochure_html(brochure)
        + _build_klerk_html(klerk)
        + _build_eaeu_html(eaeu)
        + _build_amendments_html(amendments)
        + _build_top_html(top)
        + _build_sources_html(sources)
        + _SCRIPT.format(pair_lookup=json.dumps(pair_lookup, ensure_ascii=False),
                         doc_titles=json.dumps(doc_titles, ensure_ascii=False))
        + '</body></html>\n'
    )

    p = DOCS / "Forensic_v8_report.html"
    p.write_text(html_str, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# HTML chunks
# ---------------------------------------------------------------------------

_STYLE = """<style>
:root {
  --bg: #fafafa; --fg: #111827; --panel: #ffffff; --border: #d1d5db;
  --muted: #6b7280; --hl: #2563eb;
  --c-match: #16a34a; --c-partial: #f59e0b; --c-contradiction: #dc2626;
  --c-outdated: #2563eb; --c-source_gap: #7c3aed; --c-manual: #ea580c; --c-nc: #9ca3af;
}
[data-theme="dark"] {
  --bg: #0f172a; --fg: #f1f5f9; --panel: #1e293b; --border: #334155; --muted: #94a3b8;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Arial, sans-serif;
  background: var(--bg); color: var(--fg); margin: 0; line-height: 1.5;
}
header { padding: 32px 24px 18px; border-bottom: 1px solid var(--border); }
header h1 { margin: 0 0 8px; font-size: 26px; }
header p { margin: 4px 0; color: var(--muted); font-size: 14px; }
.kpis { display: flex; gap: 18px; margin-top: 12px; flex-wrap: wrap; }
.kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
       padding: 10px 14px; min-width: 100px; text-align: center; }
.kpi .v { font-size: 22px; font-weight: 700; }
.kpi .l { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
section { padding: 24px; max-width: 1400px; margin: 0 auto; }
h2 { border-left: 4px solid var(--hl); padding-left: 10px; margin-top: 28px; }
.legend { display: flex; gap: 6px; flex-wrap: wrap; margin: 16px 0; }
.legend .item { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
                border-radius: 12px; font-size: 12px; background: var(--panel);
                border: 1px solid var(--border); }
.legend .swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
.swatch.match { background: var(--c-match); } .swatch.partial { background: var(--c-partial); }
.swatch.contradiction { background: var(--c-contradiction); }
.swatch.outdated { background: var(--c-outdated); } .swatch.source_gap { background: var(--c-source_gap); }
.swatch.manual { background: var(--c-manual); } .swatch.nc { background: var(--c-nc); }
.bar { display: flex; height: 28px; border-radius: 6px; overflow: hidden;
       border: 1px solid var(--border); margin: 6px 0; }
.bar > span { display: flex; align-items: center; justify-content: center;
              color: white; font-size: 11px; font-weight: 600; }

table.matrix { border-collapse: collapse; font-size: 11px; background: var(--panel); }
table.matrix th, table.matrix td { width: 30px; height: 26px; padding: 0;
                                    text-align: center; border: 1px solid #ffffff;
                                    cursor: pointer; }
table.matrix th { background: var(--bg); font-weight: 700; font-size: 10px;
                  position: sticky; top: 0; z-index: 2; }
table.matrix th.row { position: sticky; left: 0; z-index: 3; }
table.matrix td.match { background: var(--c-match); color: white; }
table.matrix td.partial_overlap { background: var(--c-partial); color: white; }
table.matrix td.contradiction { background: var(--c-contradiction); color: white; }
table.matrix td.outdated { background: var(--c-outdated); color: white; }
table.matrix td.source_gap { background: var(--c-source_gap); color: white; }
table.matrix td.manual_review { background: var(--c-manual); color: white; }
table.matrix td.not_comparable { background: var(--c-nc); color: white; }
table.matrix td.diag { background: #1f2937; color: white; }
table.matrix td:hover { outline: 2px solid #111; outline-offset: -2px; z-index: 1; }
.matrix-wrap { overflow: auto; max-height: 660px; border: 1px solid var(--border);
               border-radius: 6px; margin-bottom: 12px; }

table.normal { border-collapse: collapse; width: 100%; background: var(--panel);
               font-size: 13px; }
table.normal th, table.normal td { padding: 8px 10px; text-align: left;
                                    border-bottom: 1px solid var(--border); vertical-align: top; }
table.normal th { background: #1f2937; color: white; font-weight: 600; position: sticky; top: 0; }
table.normal tr:nth-child(even) { background: var(--bg); }
table.normal td.red { color: var(--c-contradiction); font-weight: 500; }
table.normal td.green { color: var(--c-match); font-weight: 500; }

.tag { display: inline-block; padding: 2px 8px; border-radius: 10px;
       font-size: 10px; font-weight: 600; text-transform: uppercase; }
.tag.high { background: #fecaca; color: #991b1b; }
.tag.medium { background: #fef3c7; color: #92400e; }
.tag.low { background: #dcfce7; color: #166534; }
.tag.rank-1 { background: #dbeafe; color: #1e40af; }
.tag.rank-2 { background: #fef3c7; color: #92400e; }
.tag.rank-3 { background: #fce7f3; color: #9d174d; }

#detail { position: fixed; top: 24px; right: 24px; width: 360px;
          max-height: calc(100vh - 48px); overflow: auto;
          background: var(--panel); border: 1px solid var(--border);
          border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.15);
          padding: 16px; display: none; z-index: 100; font-size: 13px; }
#detail.open { display: block; }
#detail h3 { margin: 0 0 8px; font-size: 15px; }
#detail .close { float: right; cursor: pointer; color: var(--muted); }
#detail dl { margin: 0; }
#detail dt { font-weight: 600; color: var(--muted); margin-top: 8px; font-size: 11px;
              text-transform: uppercase; }
#detail dd { margin: 2px 0 0; }

.theme-toggle { position: fixed; top: 16px; right: 16px; padding: 6px 12px;
                background: var(--panel); border: 1px solid var(--border);
                border-radius: 6px; cursor: pointer; font-size: 13px; }

details { margin: 12px 0; padding: 12px; background: var(--panel);
          border: 1px solid var(--border); border-radius: 6px; }
details summary { cursor: pointer; font-weight: 600; }
</style>
"""

_HEADER = """<button class="theme-toggle" onclick="document.documentElement.dataset.theme = (document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark')">🌓</button>
<header>
  <h1>Forensic v8 — Interactive Report</h1>
  <p>Evidence-grade сравнительная матрица миграционного корпуса РФ. Не является юр.заключением.</p>
  <p>Сгенерировано: <code>{generated}</code></p>
  <div class="kpis">
    <div class="kpi"><div class="v">{total_docs}</div><div class="l">документов</div></div>
    <div class="kpi"><div class="v">{total_pairs}</div><div class="l">пар</div></div>
    <div class="kpi"><div class="v">{total_events}</div><div class="l">событий</div></div>
    <div class="kpi"><div class="v">{total_manual}</div><div class="l">manual review</div></div>
  </div>
</header>
<div id="detail"><span class="close" onclick="document.getElementById('detail').classList.remove('open')">×</span><div id="detail-body"></div></div>
"""

_LEGEND = """<section><h2>Легенда статусов v8</h2>
<div class="legend">
  <span class="item"><span class="swatch match"></span> match — совпадает</span>
  <span class="item"><span class="swatch partial"></span> partial_overlap — частично</span>
  <span class="item"><span class="swatch contradiction"></span> contradiction — противоречие</span>
  <span class="item"><span class="swatch outdated"></span> outdated — устарело</span>
  <span class="item"><span class="swatch source_gap"></span> source_gap — пробел</span>
  <span class="item"><span class="swatch manual"></span> manual_review — юрист</span>
  <span class="item"><span class="swatch nc"></span> not_comparable — несравнимы</span>
</div>
</section>
"""


def _build_status_bar_html(dist: dict[str, int]) -> str:
    total = sum(dist.values()) or 1
    out = '<section><h2>Распределение пар по статусам</h2><div class="bar">'
    for st in ("match", "partial_overlap", "contradiction", "outdated",
               "source_gap", "manual_review", "not_comparable"):
        count = dist.get(st, 0)
        if not count:
            continue
        pct = count * 100 / total
        out += f'<span style="width: {pct:.2f}%; background: var(--c-{st.replace("partial_overlap","partial").replace("manual_review","manual").replace("not_comparable","nc")});">{st} {count}</span>'
    out += "</div></section>\n"
    return out


def _build_matrix_html(sources, matrix, codes, titles, ranks) -> str:
    doc_ids = [s["ИД"] for s in sources]
    out = '<section><h2>Doc × Doc матрица — кликни на ячейку</h2>'
    out += '<div class="matrix-wrap"><table class="matrix"><thead><tr><th class="row">ИД</th>'
    for did in doc_ids:
        code = codes.get(did, did)
        out += f'<th title="{html.escape(titles.get(did,""))}">{html.escape(code[:8])}</th>'
    out += "</tr></thead><tbody>"
    for row in matrix:
        di = row["ИД"]
        out += f'<tr><th class="row" title="{html.escape(titles.get(di,""))}">{html.escape(di)}</th>'
        for dj in doc_ids:
            cell = (row.get(dj) or "").strip()
            if di == dj:
                out += '<td class="diag">—</td>'
                continue
            mark = cell[0] if cell else ""
            status_class = {
                "✓": "match", "≈": "partial_overlap", "⚠": "contradiction",
                "↻": "outdated", "∅": "source_gap", "?": "manual_review",
            }.get(mark, "not_comparable")
            cnt = ""
            if "(" in cell:
                cnt = cell[cell.index("(") + 1:cell.index(")")]
            out += f'<td class="{status_class}" data-l="{html.escape(di)}" data-r="{html.escape(dj)}" onclick="showPair(this)">{html.escape(cnt)}</td>'
        out += "</tr>"
    out += '</tbody></table></div></section>\n'
    return out


def _build_actions_html(actions, raci) -> str:
    out = '<section><h2>FA-actions — каталог действий</h2><table class="normal">'
    out += "<tr><th>ID</th><th>Категория</th><th>Серьёзность</th><th>Где</th><th>Что не так</th><th>Что сделать</th><th>Кто</th></tr>"
    raci_by = {r["ID"]: r for r in raci}
    for a in actions:
        sev = a.get("Серьёзность", "")
        sev_class = ("high" if "высокая" in sev.lower() else
                     "low" if "низкая" in sev.lower() else "medium")
        rc = raci_by.get(a["ID"], {})
        owner = f"{rc.get('R (исполнитель)','')}; A: {rc.get('A (подписывает)','')}"
        out += (f"<tr><td><b>{html.escape(a['ID'])}</b></td>"
                f"<td>{html.escape(a.get('Категория',''))}</td>"
                f"<td><span class='tag {sev_class}'>{html.escape(sev)}</span></td>"
                f"<td>{html.escape(a.get('Где',''))}</td>"
                f"<td class='red'>{html.escape(a.get('Что не так',''))}</td>"
                f"<td class='green'>{html.escape(a.get('Что сделать',''))}</td>"
                f"<td>{html.escape(owner)}</td></tr>")
    out += "</table></section>\n"
    return out


def _build_brochure_html(brochure) -> str:
    out = '<section><h2>Брошюра Минэка — red/green правки</h2><table class="normal">'
    out += "<tr><th>ID</th><th>Раздел</th><th>RED — сейчас</th><th>GREEN — должно быть</th><th>Основание</th></tr>"
    for b in brochure:
        out += (f"<tr><td><b>{html.escape(b['ID'])}</b></td>"
                f"<td>{html.escape(b['Раздел'])}</td>"
                f"<td class='red'>{html.escape(b['Сейчас (RED)'])}</td>"
                f"<td class='green'>{html.escape(b['Должно быть (GREEN)'])}</td>"
                f"<td>{html.escape(b['Основание (ПП №2573)'])}</td></tr>")
    out += "</table></section>\n"
    return out


def _build_klerk_html(klerk) -> str:
    out = '<section><h2>Клерк → НПА footnotes</h2><table class="normal">'
    out += "<tr><th>ID</th><th>Тезис</th><th>НПА</th><th>Место</th><th>Footnote</th></tr>"
    for k in klerk:
        out += (f"<tr><td><b>{html.escape(k['ID'])}</b></td>"
                f"<td>{html.escape(k['Тезис Клерка (D09)'])}</td>"
                f"<td>{html.escape(k['Связанный НПА'])}</td>"
                f"<td>{html.escape(k['Конкретное место'])}</td>"
                f"<td class='green'>{html.escape(k['Что добавить в Клерк'])}</td></tr>")
    out += "</table></section>\n"
    return out


def _build_eaeu_html(eaeu) -> str:
    out = '<section><h2>ЕАЭС split (3 группы)</h2><table class="normal">'
    out += "<tr><th>ID</th><th>Группа</th><th>Страны</th><th>Режим работы</th><th>Основание</th></tr>"
    for e in eaeu:
        out += (f"<tr><td><b>{html.escape(e['ID'])}</b></td>"
                f"<td>{html.escape(e['Гражданство'])}</td>"
                f"<td>{html.escape(e['Страны'])}</td>"
                f"<td><b>{html.escape(e['Правовой режим работы'])}</b></td>"
                f"<td>{html.escape(e['Основание'])}</td></tr>")
    out += "</table></section>\n"
    return out


def _build_amendments_html(amendments) -> str:
    out = '<section><h2>Amendment chains</h2><table class="normal">'
    out += "<tr><th>ID</th><th>Цепочка</th><th>Базовый акт</th><th>Поправки</th><th>Что цитировать сейчас</th></tr>"
    for a in amendments:
        out += (f"<tr><td><b>{html.escape(a['ID'])}</b></td>"
                f"<td>{html.escape(a['Цепочка'])}</td>"
                f"<td class='red'>{html.escape(a['Базовый акт'])}</td>"
                f"<td>{html.escape(a['Поправки в хронологии'])}</td>"
                f"<td class='green'>{html.escape(a['Что цитировать сейчас'])}</td></tr>")
    out += "</table></section>\n"
    return out


def _build_top_html(top) -> str:
    out = '<section><details open><summary>Top-20 приоритетов (с дедлайнами)</summary><table class="normal">'
    out += "<tr><th>№</th><th>Пара</th><th>Тема</th><th>Действие</th><th>Срок</th><th>Кто</th></tr>"
    for t in top:
        out += (f"<tr><td>{html.escape(t['Ранг'])}</td>"
                f"<td><b>{html.escape(t['Пара'])}</b></td>"
                f"<td>{html.escape(t['Тема'])}</td>"
                f"<td>{html.escape(t['Действие'])}</td>"
                f"<td><b>{html.escape(t['Срок'])}</b></td>"
                f"<td>{html.escape(t['Кто'])}</td></tr>")
    out += "</table></details></section>\n"
    return out


def _build_sources_html(sources) -> str:
    out = '<section><details><summary>Реестр источников (26)</summary><table class="normal">'
    out += "<tr><th>ИД</th><th>Код</th><th>Название</th><th>Тип</th><th>Ранг</th></tr>"
    for s in sources:
        rank = s["Ранг"]
        out += (f"<tr><td><b>{html.escape(s['ИД'])}</b></td>"
                f"<td>{html.escape(s['Код'])}</td>"
                f"<td>{html.escape(s['Название'])}</td>"
                f"<td>{html.escape(s['Тип'])}</td>"
                f"<td><span class='tag rank-{html.escape(rank)}'>rank-{html.escape(rank)}</span></td></tr>")
    out += "</table></details></section>\n"
    return out


_SCRIPT = """<script>
const PAIRS = {pair_lookup};
const TITLES = {doc_titles};
function showPair(td) {{
  const l = td.dataset.l, r = td.dataset.r;
  const key = [l,r].sort().join("|");
  const p = PAIRS[key];
  const detail = document.getElementById("detail-body");
  if (!p) {{
    detail.innerHTML = "<h3>"+l+" ↔ "+r+"</h3><p>Нет данных пары.</p>";
  }} else {{
    detail.innerHTML = "<h3>"+p.id+": "+p.L+" ↔ "+p.R+"</h3>" +
      "<dl>" +
      "<dt>Слева ("+p.L+")</dt><dd>"+(TITLES[p.L]||"")+"</dd>" +
      "<dt>Справа ("+p.R+")</dt><dd>"+(TITLES[p.R]||"")+"</dd>" +
      "<dt>Статус v8</dt><dd><b>"+p.status+"</b></dd>" +
      "<dt>Ранги</dt><dd>"+p.lr_rank+"</dd>" +
      "<dt>Событий</dt><dd>"+p.events+"</dd>" +
      "<dt>Темы</dt><dd>"+(p.topics||"—")+"</dd>" +
      "<dt>Manual review</dt><dd>"+p.manual+"</dd>" +
      "<dt>Основание</dt><dd>"+(p.basis||"")+"</dd>" +
      "</dl>";
  }}
  document.getElementById("detail").classList.add("open");
}}
</script>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    summary = build_summary_md()
    print(f"  ✓ {summary.relative_to(ROOT)}: {summary.stat().st_size:,}b")

    html_path = build_html_report()
    print(f"  ✓ {html_path.relative_to(ROOT)}: {html_path.stat().st_size:,}b")

    master = build_master_index()
    print(f"  ✓ {master.relative_to(ROOT)}: {master.stat().st_size:,}b")

    qa = {
        "generated_at": GENERATED_AT,
        "schema": "v8.4",
        "added_artifacts": {
            "summary_md": str(summary.relative_to(ROOT)),
            "html_report": str(html_path.relative_to(ROOT)),
            "master_index_md": str(master.relative_to(ROOT)),
        },
    }
    (LOGS / "qa_v8_4.json").write_text(
        json.dumps(qa, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
