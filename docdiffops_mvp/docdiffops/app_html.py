"""Single-file web UI for DocDiffOps served at /.

Vanilla JS + inline CSS — no build step, no external runtime deps. Loads
from /batches, /batches/{id}, and the existing upload/run/download
endpoints. PDFs render via pdf.js loaded from a public CDN; HTML preview
uses sandboxed iframes against /batches/{id}/download/*.
"""

APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DocDiffOps</title>
<style>
:root {
  --bg: #0b0d12; --panel: #11141b; --panel-2: #161a22; --line: #1f2632;
  --fg: #e9eef5; --mute: #8b97aa; --strong: #ffffff;
  --blue: #4cc3ff; --blue-dim: #1d4d6b;
  --green: #2ec27e; --red: #e5484d; --amber: #ffb224; --gray: #5b6473;
  --hi: rgba(255,214,10,0.85);
  --rad: 6px; --rad-lg: 10px;
  --shadow: 0 6px 28px rgba(0,0,0,0.45);
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 ui-sans-serif, -apple-system, system-ui, "Segoe UI", Inter, sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
button { font: inherit; cursor: pointer; }
input, select, textarea { font: inherit; color: inherit; }
code, pre, .mono { font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace; font-size: 12.5px; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: #232a36; border-radius: 4px; }

/* ------------------- top bar ------------------- */
header.topbar {
  display: flex; align-items: center; gap: 24px;
  padding: 12px 24px; border-bottom: 1px solid var(--line);
  background: var(--panel); position: sticky; top: 0; z-index: 30;
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 600; letter-spacing: 0.02em; }
.brand-dot { width: 22px; height: 22px; border-radius: 5px; background: linear-gradient(135deg, #ff5470, #4cc3ff); display: inline-block; }
.tabs { display: flex; gap: 4px; margin-left: auto; }
.tab { background: transparent; border: 1px solid transparent; color: var(--mute); padding: 6px 12px; border-radius: 6px; font-size: 13px; }
.tab.active { color: var(--strong); background: var(--panel-2); border-color: var(--line); }
.topbar .ext { display: flex; gap: 14px; color: var(--mute); font-size: 12px; align-items: center; }
.topbar .ext a { color: var(--mute); }
.dot-online { width: 8px; height: 8px; border-radius: 50%; background: var(--green); display: inline-block; box-shadow: 0 0 8px var(--green); }

/* ------------------- layout ------------------- */
main.app { padding: 28px 32px 64px; max-width: 1500px; margin: 0 auto; }
.section-title { font-size: 11px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--mute); margin: 0 0 12px; }

/* ------------------- upload ------------------- */
.upload-wrap { display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px; }
@media (max-width: 1100px) { .upload-wrap { grid-template-columns: 1fr; } }

.dropzone {
  background: var(--panel); border: 2px dashed #2a3340; border-radius: var(--rad-lg);
  padding: 40px; text-align: center; transition: all 0.15s ease;
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  min-height: 240px; justify-content: center;
}
.dropzone.dragging { border-color: var(--blue); background: rgba(76,195,255,0.06); transform: scale(1.005); }
.dropzone .icon { width: 48px; height: 48px; color: var(--blue); }
.dropzone .title { font-size: 18px; font-weight: 600; }
.dropzone .hint { color: var(--mute); font-size: 13px; }
.dropzone .browse { background: var(--blue); color: #04111a; border: 0; padding: 8px 18px; border-radius: 6px; font-weight: 600; font-size: 13px; }

.staged { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad-lg); padding: 18px; }
.staged .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.staged .head h3 { margin: 0; font-size: 15px; }
.staged .clear { background: transparent; border: 1px solid var(--line); color: var(--mute); padding: 4px 10px; border-radius: 5px; font-size: 12px; }
.staged ul { list-style: none; padding: 0; margin: 0 0 12px; max-height: 220px; overflow: auto; }
.staged li { display: grid; grid-template-columns: 1fr 100px 24px; gap: 10px; align-items: center; padding: 8px 10px; border-radius: 5px; }
.staged li:nth-child(odd) { background: var(--panel-2); }
.staged li .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.staged li .size { color: var(--mute); font-size: 11.5px; text-align: right; font-variant-numeric: tabular-nums; }
.staged li .x { background: transparent; border: 0; color: var(--mute); font-size: 16px; line-height: 1; }
.staged li .x:hover { color: var(--red); }
.batch-input { width: 100%; background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 8px 10px; border-radius: 5px; margin-bottom: 10px; }
.staged .actions { display: flex; gap: 10px; }
.btn { padding: 9px 16px; border-radius: 6px; border: 1px solid var(--line); background: var(--panel-2); color: var(--fg); font-weight: 500; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: linear-gradient(135deg, #4cc3ff, #2b95cc); color: #04111a; border-color: transparent; font-weight: 600; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.progress-bar { height: 4px; background: var(--panel-2); border-radius: 2px; overflow: hidden; margin: 10px 0; }
.progress-bar > div { height: 100%; background: var(--blue); transition: width 0.2s ease; }

/* ------------------- batch list ------------------- */
.batches-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.batch-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad-lg); padding: 16px; cursor: pointer; transition: all 0.15s ease; }
.batch-card:hover { border-color: var(--blue-dim); transform: translateY(-1px); }
.batch-card .id { font-family: ui-monospace, monospace; font-size: 11px; color: var(--mute); }
.batch-card .title { font-size: 15px; font-weight: 600; margin: 4px 0 12px; }
.batch-card .row { display: flex; justify-content: space-between; font-size: 12px; color: var(--mute); padding: 3px 0; }
.batch-card .row .v { color: var(--fg); font-weight: 500; font-variant-numeric: tabular-nums; }
.batch-card .when { font-size: 11px; color: var(--mute); margin-top: 8px; }

/* ------------------- batch detail ------------------- */
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; gap: 24px; }
.detail-head h2 { margin: 0 0 4px; font-size: 22px; }
.detail-head .id { color: var(--mute); font-family: ui-monospace, monospace; font-size: 12px; }
.back { background: var(--panel-2); border: 1px solid var(--line); color: var(--mute); padding: 6px 12px; border-radius: 5px; font-size: 12px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 24px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); padding: 12px 14px; }
.kpi .v { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.kpi .l { font-size: 11px; color: var(--mute); text-transform: uppercase; letter-spacing: 0.06em; }
.kpi.high .v { color: var(--red); }
.kpi.review .v { color: var(--amber); }

.tabs-line { display: flex; gap: 2px; border-bottom: 1px solid var(--line); margin-bottom: 16px; }
.tab-line { background: transparent; border: 0; color: var(--mute); padding: 10px 16px; border-bottom: 2px solid transparent; font-size: 13px; }
.tab-line.active { color: var(--strong); border-color: var(--blue); }

/* ------------------- events ------------------- */
.events-toolbar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.events-toolbar input, .events-toolbar select { background: var(--panel); border: 1px solid var(--line); color: var(--fg); padding: 7px 10px; border-radius: 5px; font-size: 13px; }
.events-toolbar input { flex: 1 1 280px; }
.events-toolbar .count { color: var(--mute); font-size: 12px; align-self: center; margin-left: auto; }

.evt-table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); overflow: hidden; }
.evt-table th { background: var(--panel-2); text-align: left; padding: 10px 12px; font-size: 12px; font-weight: 600; color: var(--mute); border-bottom: 1px solid var(--line); position: sticky; top: 56px; z-index: 5; }
.evt-table td { padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; font-size: 13px; }
.evt-table tr:last-child td { border-bottom: 0; }
.evt-table tr:hover td { background: rgba(76,195,255,0.04); cursor: pointer; }
.evt-table tr.expanded td { background: rgba(76,195,255,0.08); }
.evt-detail { padding: 0 !important; }
.evt-detail .inner { padding: 14px 16px; background: var(--panel-2); border-top: 1px solid var(--line); }
.quote-box { background: var(--bg); border: 1px solid var(--line); border-left: 3px solid var(--gray); padding: 10px 12px; border-radius: 4px; margin: 6px 0; font-size: 13px; line-height: 1.6; }
.quote-box.lhs { border-left-color: var(--red); }
.quote-box.rhs { border-left-color: var(--green); }
.quote-box .label { color: var(--mute); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }

.chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; letter-spacing: 0.03em; }
.chip-same { background: rgba(46,194,126,0.14); color: var(--green); }
.chip-added { background: rgba(76,195,255,0.14); color: var(--blue); }
.chip-deleted { background: rgba(229,72,77,0.16); color: var(--red); }
.chip-modified, .chip-partial { background: rgba(255,178,36,0.14); color: var(--amber); }
.chip-contradicts, .chip-manual_review { background: rgba(229,72,77,0.20); color: var(--red); border: 1px solid rgba(229,72,77,0.3); }
.chip-high { background: rgba(229,72,77,0.20); color: var(--red); }
.chip-medium { background: rgba(255,178,36,0.18); color: var(--amber); }
.chip-low { background: rgba(91,100,115,0.20); color: var(--mute); }
.rank-1 { color: var(--red); }
.rank-2 { color: var(--amber); }
.rank-3 { color: var(--mute); }
.muted { color: var(--mute); }
.short-id { font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--mute); }

/* ------------------- pair viewer ------------------- */
.pairs-list { display: grid; gap: 10px; }
.pair-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); padding: 12px 14px; }
.pair-card .head { display: flex; justify-content: space-between; align-items: center; gap: 14px; }
.pair-card .pair-id { font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--mute); }
.pair-card .docs { font-size: 14px; font-weight: 500; }
.pair-card .arrow { color: var(--mute); margin: 0 6px; }
.pair-card .stats { display: flex; gap: 14px; font-size: 12px; color: var(--mute); margin-top: 8px; }
.pair-card .stats span { color: var(--fg); font-variant-numeric: tabular-nums; }
.pair-card .links { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.pill-link { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 4px 10px; border-radius: 4px; font-size: 11.5px; }
.pill-link:hover { border-color: var(--blue); text-decoration: none; }

/* ------------------- documents ------------------- */
.docs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.doc-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); padding: 14px; }
.doc-card .name { font-weight: 500; word-break: break-word; }
.doc-card .meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px 12px; margin-top: 10px; font-size: 12px; }
.doc-card .meta .l { color: var(--mute); }
.doc-card .meta .v { font-variant-numeric: tabular-nums; }
.doc-card .sha { color: var(--mute); font-family: ui-monospace, monospace; font-size: 10.5px; margin-top: 8px; word-break: break-all; }

/* ------------------- artifacts ------------------- */
.arts-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.art-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); padding: 12px 14px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.art-card .info { min-width: 0; }
.art-card .type { font-size: 11px; color: var(--mute); text-transform: uppercase; letter-spacing: 0.05em; }
.art-card .name { font-weight: 500; font-size: 13px; word-break: break-word; }

/* ------------------- toast ------------------- */
.toast-wrap { position: fixed; bottom: 24px; right: 24px; display: flex; flex-direction: column; gap: 8px; z-index: 100; }
.toast { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--blue); border-radius: 5px; padding: 10px 14px; min-width: 240px; box-shadow: var(--shadow); animation: slide-in 0.2s ease; font-size: 13px; }
.toast.error { border-left-color: var(--red); }
.toast.success { border-left-color: var(--green); }
@keyframes slide-in { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

/* ------------------- empty / loading ------------------- */
.empty { text-align: center; color: var(--mute); padding: 40px; font-style: italic; }
.spinner { width: 18px; height: 18px; border: 2px solid var(--blue-dim); border-top-color: var(--blue); border-radius: 50%; animation: spin 0.7s linear infinite; display: inline-block; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ------------------- viewer (inline pdf/html preview) ------------------- */
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; min-height: 500px; }
.viewer-pane { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); display: flex; flex-direction: column; min-height: 400px; }
.viewer-pane .vhead { padding: 8px 12px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; }
.viewer-pane .vhead .name { font-weight: 500; font-size: 13px; word-break: break-all; }
.viewer-pane .vbody { flex: 1; min-height: 0; overflow: auto; position: relative; }
.viewer-pane iframe { width: 100%; height: 100%; min-height: 400px; border: 0; background: white; }
.viewer-pane .empty-frame { color: var(--mute); padding: 40px; text-align: center; font-style: italic; font-size: 13px; }

mark { background: var(--hi); color: #000; padding: 0 2px; border-radius: 2px; }
</style>
</head>
<body>

<header class="topbar">
  <div class="brand"><span class="brand-dot"></span> DocDiffOps</div>
  <div class="tabs">
    <button class="tab" data-view="upload">Upload</button>
    <button class="tab" data-view="batches">Batches</button>
  </div>
  <div class="ext">
    <span><span class="dot-online"></span> live</span>
    <a href="/docs" target="_blank">API ↗</a>
    <a href="https://github.com/agisota/diffs" target="_blank">GitHub ↗</a>
  </div>
</header>

<main class="app">

  <!-- ============== upload view ============== -->
  <section id="view-upload" hidden>
    <h2 class="section-title">Создать пакет сравнения</h2>
    <div class="upload-wrap">
      <div id="dropzone" class="dropzone">
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 16V4M12 4l-4 4M12 4l4 4M5 16v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg>
        <div class="title">Перетащите файлы сюда</div>
        <div class="hint">PDF, DOCX, PPTX, XLSX, HTML, TXT — до 50 за раз</div>
        <button type="button" class="browse" onclick="document.getElementById('file-input').click()">Browse files</button>
        <input id="file-input" type="file" multiple style="display:none">
      </div>

      <div class="staged">
        <div class="head">
          <h3>Staged files (<span id="staged-count">0</span>)</h3>
          <button class="clear" id="clear-staged">Clear all</button>
        </div>
        <input id="batch-title" class="batch-input" placeholder="Batch title (optional)">
        <ul id="staged-list"></ul>
        <div id="upload-progress" style="display:none">
          <div class="progress-bar"><div id="progress-fill" style="width:0%"></div></div>
          <div class="muted" style="font-size:12px" id="progress-label">Uploading…</div>
        </div>
        <div class="actions">
          <button id="btn-create" class="btn btn-primary" disabled>Создать batch + Загрузить + Запустить</button>
        </div>
      </div>
    </div>
  </section>

  <!-- ============== batches view ============== -->
  <section id="view-batches" hidden>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap">
      <h2 class="section-title" style="margin:0">Все батчи (<span id="batches-count">0</span>)</h2>
      <button class="btn" id="btn-refresh-batches">↻ Обновить</button>
    </div>
    <div id="batches-grid" class="batches-grid"></div>
    <div id="batches-empty" class="empty" style="display:none">Пока нет ни одного batch'а — создайте первый через Upload.</div>
  </section>

  <!-- ============== batch detail view ============== -->
  <section id="view-detail" hidden>
    <div class="detail-head">
      <div>
        <button class="back" id="btn-back-to-batches">← Все батчи</button>
        <h2 id="detail-title" style="margin-top:12px">…</h2>
        <div id="detail-id" class="id"></div>
      </div>
      <button class="btn" id="btn-refresh-detail">↻</button>
    </div>

    <div id="detail-kpis" class="kpis"></div>

    <div class="tabs-line">
      <button class="tab-line active" data-detail-tab="events">События</button>
      <button class="tab-line" data-detail-tab="pairs">Пары</button>
      <button class="tab-line" data-detail-tab="docs">Документы</button>
      <button class="tab-line" data-detail-tab="artifacts">Артефакты</button>
      <button class="tab-line" data-detail-tab="audit">Audit</button>
      <span style="margin-left:auto;align-self:center;display:flex;gap:6px;align-items:center">
        <span class="muted" style="font-size:12px">Anchor:</span>
        <select id="anchor-select" class="batch-input" style="margin:0;width:auto;min-width:160px;font-size:12.5px;padding:4px 8px"></select>
        <button class="btn" id="btn-rerender" style="padding:5px 10px;font-size:12px">↻ Rerender</button>
      </span>
    </div>

    <div id="dtab-events" class="dtab">
      <div class="events-toolbar">
        <input id="evt-q" placeholder="Filter: text, doc_id, quote, event_id…">
        <select id="evt-sev"><option value="">severity (all)</option><option>high</option><option>medium</option><option>low</option></select>
        <select id="evt-stat"><option value="">status (all)</option><option>same</option><option>partial</option><option>modified</option><option>added</option><option>deleted</option><option>contradicts</option><option>manual_review</option></select>
        <select id="evt-pair"><option value="">pair (all)</option></select>
        <span class="count" id="evt-count"></span>
      </div>
      <table class="evt-table" id="evt-table">
        <thead><tr><th style="width:90px">event</th><th style="width:100px">status</th><th style="width:90px">severity</th><th style="width:60px">conf</th><th>LHS quote</th><th>RHS quote</th></tr></thead>
        <tbody id="evt-tbody"></tbody>
      </table>
    </div>

    <div id="dtab-pairs" class="dtab" hidden>
      <div id="pairs-list" class="pairs-list"></div>
    </div>

    <div id="dtab-docs" class="dtab" hidden>
      <div id="docs-grid" class="docs-grid"></div>
    </div>

    <div id="dtab-artifacts" class="dtab" hidden>
      <div id="arts-list" class="arts-list"></div>
    </div>

    <div id="dtab-audit" class="dtab" hidden>
      <div id="audit-list"></div>
    </div>
  </section>

</main>

<div class="toast-wrap" id="toast-wrap"></div>

<script>
const BASE = '';

// -------- view routing --------
const views = { upload: 'view-upload', batches: 'view-batches', detail: 'view-detail' };
let currentView = 'upload';
let currentBatchId = null;

function showView(name) {
  for (const [k, id] of Object.entries(views)) {
    document.getElementById(id).hidden = (k !== name);
  }
  for (const t of document.querySelectorAll('.tab')) {
    t.classList.toggle('active', t.dataset.view === name && name !== 'detail');
  }
  if (name !== 'detail') currentBatchId = null;
  currentView = name;
  // hash sync
  if (name === 'detail' && currentBatchId) location.hash = '#batch/' + currentBatchId;
  else if (name === 'batches') location.hash = '#batches';
  else location.hash = '#upload';
}

document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {
  if (b.dataset.view === 'batches') refreshBatches();
  showView(b.dataset.view);
}));

// -------- toast --------
function toast(msg, kind) {
  const el = document.createElement('div');
  el.className = 'toast' + (kind ? ' ' + kind : '');
  el.textContent = msg;
  document.getElementById('toast-wrap').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 200); }, 4000);
}

// -------- staging --------
const staged = [];
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const stagedList = document.getElementById('staged-list');

function fmtSize(n) {
  if (n < 1024) return n + ' B';
  if (n < 1024*1024) return (n/1024).toFixed(1) + ' KB';
  return (n/(1024*1024)).toFixed(1) + ' MB';
}

function renderStaged() {
  document.getElementById('staged-count').textContent = staged.length;
  stagedList.innerHTML = '';
  staged.forEach((f, i) => {
    const li = document.createElement('li');
    li.innerHTML = `<span class='name' title='${escapeHtml(f.name)}'>${escapeHtml(f.name)}</span>` +
                   `<span class='size'>${fmtSize(f.size)}</span>` +
                   `<button class='x' aria-label='remove' data-i='${i}'>×</button>`;
    li.querySelector('.x').addEventListener('click', e => {
      staged.splice(parseInt(e.target.dataset.i), 1);
      renderStaged();
    });
    stagedList.appendChild(li);
  });
  document.getElementById('btn-create').disabled = staged.length === 0;
}

function escapeHtml(s) {
  return (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function addFiles(fileList) {
  for (const f of fileList) staged.push(f);
  renderStaged();
}

dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragging'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('dragging');
  if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => addFiles(fileInput.files));
document.getElementById('clear-staged').addEventListener('click', () => { staged.length = 0; renderStaged(); });

// -------- create + upload + run --------
document.getElementById('btn-create').addEventListener('click', async () => {
  if (staged.length === 0) return;
  const btn = document.getElementById('btn-create');
  const progBox = document.getElementById('upload-progress');
  const progFill = document.getElementById('progress-fill');
  const progLabel = document.getElementById('progress-label');
  btn.disabled = true;
  progBox.style.display = 'block';

  try {
    progLabel.textContent = 'Создание batch…'; progFill.style.width = '5%';
    const title = (document.getElementById('batch-title').value || '').trim() || 'untitled';
    const created = await fetch(BASE + '/batches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    }).then(r => r.json());
    const batchId = created.batch_id;

    progLabel.textContent = `Загрузка ${staged.length} файлов…`; progFill.style.width = '15%';
    const fd = new FormData();
    for (const f of staged) fd.append('files', f, f.name);
    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', BASE + '/batches/' + batchId + '/documents');
      xhr.upload.onprogress = e => {
        if (e.lengthComputable) {
          const pct = 15 + Math.round((e.loaded / e.total) * 55);
          progFill.style.width = pct + '%';
        }
      };
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve(JSON.parse(xhr.responseText)) : reject(new Error(xhr.statusText));
      xhr.onerror = () => reject(new Error('upload network error'));
      xhr.send(fd);
    });

    progLabel.textContent = 'Запуск pipeline…'; progFill.style.width = '75%';
    const result = await fetch(BASE + '/batches/' + batchId + '/run?profile=fast&sync=true', { method: 'POST' }).then(r => r.json());
    progFill.style.width = '100%';
    progLabel.textContent = `Готово: ${result.metrics?.events ?? 0} событий за ${result.metrics?.time_to_report_sec ?? '?'}s`;
    toast(`Batch ${batchId.slice(-8)} готов: ${result.metrics?.events ?? 0} событий`, 'success');
    staged.length = 0; renderStaged();
    document.getElementById('batch-title').value = '';
    setTimeout(() => { progBox.style.display = 'none'; openBatch(batchId); }, 800);
  } catch (e) {
    toast('Ошибка: ' + e.message, 'error');
    progBox.style.display = 'none';
    btn.disabled = false;
  }
});

// -------- batch list --------
async function refreshBatches() {
  const grid = document.getElementById('batches-grid');
  grid.innerHTML = '<div class="empty"><span class="spinner"></span> Загрузка…</div>';
  try {
    const list = await fetch(BASE + '/batches').then(r => r.json());
    document.getElementById('batches-count').textContent = list.length;
    document.getElementById('batches-empty').style.display = list.length === 0 ? '' : 'none';
    grid.innerHTML = '';
    list.sort((a, b) => (b.updated_at || b.created_at || '').localeCompare(a.updated_at || a.created_at || ''));
    for (const b of list) {
      const card = document.createElement('div');
      card.className = 'batch-card';
      const total = b.diff_events_count ?? b.events ?? 0;
      const high = b.high_count ?? 0;
      card.innerHTML = `
        <div class='id'>${escapeHtml(b.batch_id || '')}</div>
        <div class='title'>${escapeHtml(b.title || '(untitled)')}</div>
        <div class='row'><span>Документы</span><span class='v'>${b.documents_count ?? '—'}</span></div>
        <div class='row'><span>Пар</span><span class='v'>${b.pair_runs_count ?? '—'}</span></div>
        <div class='row'><span>Событий</span><span class='v'>${total}</span></div>
        ${high ? `<div class='row'><span>High risk</span><span class='v' style='color:var(--red)'>${high}</span></div>` : ''}
        <div class='when'>${escapeHtml(b.updated_at || b.created_at || '')}</div>
      `;
      card.addEventListener('click', () => openBatch(b.batch_id));
      grid.appendChild(card);
    }
  } catch (e) {
    grid.innerHTML = `<div class='empty'>Ошибка загрузки: ${escapeHtml(e.message)}</div>`;
  }
}

document.getElementById('btn-refresh-batches').addEventListener('click', refreshBatches);
document.getElementById('btn-back-to-batches').addEventListener('click', () => { showView('batches'); refreshBatches(); });

// -------- batch detail --------
let detailState = null;

async function openBatch(batchId) {
  currentBatchId = batchId;
  showView('detail');
  document.getElementById('detail-title').textContent = '…';
  document.getElementById('detail-id').textContent = batchId;
  document.getElementById('detail-kpis').innerHTML = '<div class="empty"><span class="spinner"></span></div>';
  try {
    const s = await fetch(BASE + '/batches/' + batchId).then(r => r.json());
    detailState = s;
    document.getElementById('detail-title').textContent = s.title || '(untitled)';
    document.getElementById('detail-id').textContent = batchId;
    renderDetailKPIs(s);
    renderEvents(s);
    renderPairs(s);
    renderDocs(s);
    renderArtifacts(s);
    renderAnchorSelector(s);
    loadAudit(batchId);
    location.hash = '#batch/' + batchId;
  } catch (e) {
    document.getElementById('detail-kpis').innerHTML = `<div class='empty'>Ошибка: ${escapeHtml(e.message)}</div>`;
  }
}

document.getElementById('btn-refresh-detail').addEventListener('click', () => currentBatchId && openBatch(currentBatchId));

function renderDetailKPIs(s) {
  const docs = s.documents || [];
  const events = s.diff_events || [];
  const pairs = s.pair_runs || s.pairs || [];
  const high = events.filter(e => e.severity === 'high').length;
  const review = events.filter(e => e.review_required).length;
  const partial = events.filter(e => e.status === 'partial').length;
  const cacheExt = docs.filter(d => d.cache_extract_hit).length;
  const kpis = [
    { v: docs.length, l: 'Documents' },
    { v: pairs.length, l: 'Pairs' },
    { v: events.length, l: 'Events' },
    { v: high, l: 'High risk', cls: 'high' },
    { v: review, l: 'Review', cls: 'review' },
    { v: partial, l: 'Partial' },
    { v: `${cacheExt}/${docs.length}`, l: 'Cache hits' },
  ];
  document.getElementById('detail-kpis').innerHTML = kpis.map(k =>
    `<div class='kpi ${k.cls || ''}'><div class='v'>${escapeHtml(k.v)}</div><div class='l'>${escapeHtml(k.l)}</div></div>`
  ).join('');
}

// -------- detail tabs --------
document.querySelectorAll('.tab-line').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab-line').forEach(x => x.classList.toggle('active', x === t));
  document.querySelectorAll('.dtab').forEach(d => d.hidden = (d.id !== 'dtab-' + t.dataset.detailTab));
}));

// -------- events --------
let eventsCache = [];
function renderEvents(s) {
  eventsCache = s.diff_events || [];
  const pairs = s.pair_runs || s.pairs || [];
  const sel = document.getElementById('evt-pair');
  sel.innerHTML = '<option value="">pair (all)</option>' +
    pairs.map(p => `<option value="${escapeHtml(p.pair_id)}">${escapeHtml((p.pair_id||'').slice(-12))}</option>`).join('');
  applyEventsFilter();
}

function applyEventsFilter() {
  const q = document.getElementById('evt-q').value.trim().toLowerCase();
  const sev = document.getElementById('evt-sev').value;
  const stat = document.getElementById('evt-stat').value;
  const pid = document.getElementById('evt-pair').value;
  const tbody = document.getElementById('evt-tbody');
  tbody.innerHTML = '';
  let visible = 0;
  for (const e of eventsCache) {
    if (sev && (e.severity || 'low') !== sev) continue;
    if (stat && (e.status || '') !== stat) continue;
    if (pid && e.pair_id !== pid) continue;
    if (q) {
      const blob = [
        e.event_id, e.pair_id, e.lhs_doc_id, e.rhs_doc_id,
        e.lhs?.quote, e.rhs?.quote, e.explanation_short
      ].join(' ').toLowerCase();
      if (blob.indexOf(q) < 0) continue;
    }
    if (visible >= 1000) break;  // safety cap
    const tr = document.createElement('tr');
    tr.dataset.evid = e.event_id;
    const sevC = (e.severity || 'low').toLowerCase();
    const statC = (e.status || '').toLowerCase();
    tr.innerHTML = `
      <td><span class='short-id'>${escapeHtml((e.event_id||'').slice(-8))}</span></td>
      <td><span class='chip chip-${escapeHtml(statC)}'>${escapeHtml(statC)}</span></td>
      <td><span class='chip chip-${escapeHtml(sevC)}'>${escapeHtml(sevC)}</span></td>
      <td class='mono'>${e.confidence == null ? '—' : (typeof e.confidence === 'number' ? e.confidence.toFixed(2) : escapeHtml(e.confidence))}</td>
      <td class='muted' style='max-width:340px;overflow:hidden;text-overflow:ellipsis'>${highlight(e.lhs?.quote, q)}</td>
      <td class='muted' style='max-width:340px;overflow:hidden;text-overflow:ellipsis'>${highlight(e.rhs?.quote, q)}</td>
    `;
    tr.addEventListener('click', () => toggleEventRow(tr, e));
    tbody.appendChild(tr);
    visible++;
  }
  document.getElementById('evt-count').textContent = `${visible} visible / ${eventsCache.length} total`;
}

function highlight(text, q) {
  if (!text) return '';
  const t = String(text);
  if (!q) return escapeHtml(t.length > 200 ? t.slice(0, 200) + '…' : t);
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  return escapeHtml(t.length > 200 ? t.slice(0, 200) + '…' : t).replace(re, m => `<mark>${m}</mark>`);
}

function toggleEventRow(tr, e) {
  const next = tr.nextSibling;
  if (next && next.classList && next.classList.contains('evt-detail-row')) {
    next.remove(); tr.classList.remove('expanded'); return;
  }
  tr.classList.add('expanded');
  const dr = document.createElement('tr');
  dr.className = 'evt-detail-row';
  const lhs = e.lhs || {}, rhs = e.rhs || {};
  const reviewerName = localStorage.getItem('docdiff:reviewer') || '';
  dr.innerHTML = `
    <td colspan='6' class='evt-detail'><div class='inner'>
      <div style='display:grid;grid-template-columns:120px 1fr;gap:6px 14px;font-size:13px'>
        <div class='muted'>event_id</div><div class='mono'>${escapeHtml(e.event_id || '')}</div>
        <div class='muted'>pair_id</div><div class='mono'>${escapeHtml(e.pair_id || '')}</div>
        <div class='muted'>type</div><div>${escapeHtml(e.comparison_type || '—')}</div>
        <div class='muted'>score</div><div class='mono'>${e.score == null ? '—' : escapeHtml(e.score)}</div>
        <div class='muted'>review</div><div>${e.review_required ? 'required' : '—'}</div>
      </div>
      ${lhs.quote ? `<div class='quote-box lhs'><div class='label'>LHS · p.${escapeHtml(lhs.page_no || '?')} · ${escapeHtml(e.lhs_doc_id || '')}</div>${escapeHtml(lhs.quote)}</div>` : ''}
      ${rhs.quote ? `<div class='quote-box rhs'><div class='label'>RHS · p.${escapeHtml(rhs.page_no || '?')} · ${escapeHtml(e.rhs_doc_id || '')}</div>${escapeHtml(rhs.quote)}</div>` : ''}
      ${e.explanation_short ? `<div class='muted' style='margin-top:8px;font-style:italic'>${escapeHtml(e.explanation_short)}</div>` : ''}
      <div class='review-panel' data-evid='${escapeHtml(e.event_id)}' style='margin-top:14px;padding-top:12px;border-top:1px solid var(--line)'>
        <div class='muted' style='font-size:11px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px'>Review</div>
        <div style='display:grid;grid-template-columns:1fr 1fr 2fr auto;gap:8px;align-items:end'>
          <input class='review-name batch-input' placeholder='Your name' value='${escapeHtml(reviewerName)}' style='margin:0'>
          <select class='review-decision batch-input' style='margin:0'>
            <option value='confirmed'>confirmed</option>
            <option value='rejected'>rejected</option>
            <option value='needs_more_info'>needs more info</option>
            <option value='deferred'>deferred</option>
          </select>
          <input class='review-comment batch-input' placeholder='Comment (optional)' style='margin:0'>
          <button class='btn btn-primary review-submit' style='padding:8px 14px'>Save</button>
        </div>
        <div class='review-history' style='margin-top:10px'></div>
      </div>
    </div></td>`;
  tr.parentNode.insertBefore(dr, tr.nextSibling);
  // Wire review submission.
  const panel = dr.querySelector('.review-panel');
  const submitBtn = panel.querySelector('.review-submit');
  const historyDiv = panel.querySelector('.review-history');
  loadReviewHistory(e.event_id, historyDiv);
  submitBtn.addEventListener('click', async () => {
    const name = panel.querySelector('.review-name').value.trim() || 'anonymous';
    const decision = panel.querySelector('.review-decision').value;
    const comment = panel.querySelector('.review-comment').value;
    localStorage.setItem('docdiff:reviewer', name);
    submitBtn.disabled = true;
    try {
      const r = await fetch(BASE + '/events/' + e.event_id + '/review', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({reviewer_name: name, decision, comment})
      }).then(r => r.json());
      toast(`Review saved: ${decision}`, 'success');
      panel.querySelector('.review-comment').value = '';
      renderReviewHistory(historyDiv, r.history || []);
    } catch (err) {
      toast('Review failed: ' + err.message, 'error');
    } finally {
      submitBtn.disabled = false;
    }
  });
}

async function loadReviewHistory(eventId, container) {
  try {
    const r = await fetch(BASE + '/events/' + eventId + '/reviews').then(r => r.json());
    renderReviewHistory(container, r.history || []);
  } catch {}
}

function renderReviewHistory(container, history) {
  if (!history.length) { container.innerHTML = "<div class='muted' style='font-size:12px;font-style:italic'>(no reviews yet)</div>"; return; }
  container.innerHTML = history.map(h => `
    <div style='padding:6px 0;border-bottom:1px dashed var(--line);font-size:12.5px'>
      <span class='chip chip-${escapeHtml((h.decision||'').replace(/_/g,'-'))}'>${escapeHtml(h.decision||'')}</span>
      <strong style='margin-left:6px'>${escapeHtml(h.reviewer_name||'?')}</strong>
      <span class='muted' style='margin-left:6px'>${escapeHtml(h.decided_at||'')}</span>
      ${h.comment ? `<div class='muted' style='margin-top:3px'>${escapeHtml(h.comment)}</div>` : ''}
    </div>
  `).join('');
}

['evt-q', 'evt-sev', 'evt-stat', 'evt-pair'].forEach(id => {
  const el = document.getElementById(id);
  el.addEventListener(id === 'evt-q' ? 'input' : 'change', applyEventsFilter);
});

// -------- pairs --------
function renderPairs(s) {
  const docs = (s.documents || []).reduce((m, d) => (m[d.doc_id] = d, m), {});
  const list = document.getElementById('pairs-list');
  list.innerHTML = '';
  const pairs = s.pair_runs || s.pairs || [];
  if (!pairs.length) { list.innerHTML = "<div class='empty'>(пока нет пар)</div>"; return; }
  const arts = (s.artifacts || []);
  for (const p of pairs) {
    const lhs = docs[p.lhs_doc_id] || {};
    const rhs = docs[p.rhs_doc_id] || {};
    const card = document.createElement('div');
    card.className = 'pair-card';
    const ev = (s.diff_events || []).filter(e => e.pair_id === p.pair_id);
    const same = ev.filter(e => e.status === 'same').length;
    const partial = ev.filter(e => e.status === 'partial').length;
    const added = ev.filter(e => e.status === 'added').length;
    const deleted = ev.filter(e => e.status === 'deleted').length;
    const high = ev.filter(e => e.severity === 'high').length;
    const pairArts = arts.filter(a => (a.path || '').includes(p.pair_id));
    card.innerHTML = `
      <div class='head'>
        <div>
          <div class='pair-id'>${escapeHtml(p.pair_id || '')}</div>
          <div class='docs'>
            <span class='rank-${lhs.source_rank || 3}'>${escapeHtml(lhs.filename || lhs.doc_id || p.lhs_doc_id || '?')}</span>
            <span class='arrow'>↔</span>
            <span class='rank-${rhs.source_rank || 3}'>${escapeHtml(rhs.filename || rhs.doc_id || p.rhs_doc_id || '?')}</span>
          </div>
        </div>
        <div class='muted mono' style='font-size:12px'>${ev.length} events</div>
      </div>
      <div class='stats'>
        <div>same <span>${same}</span></div>
        <div>partial <span>${partial}</span></div>
        <div>+ <span>${added}</span></div>
        <div>− <span>${deleted}</span></div>
        ${high ? `<div style='color:var(--red)'>high <span style='color:var(--red)'>${high}</span></div>` : ''}
      </div>
      <div class='links'>
        ${pairArts.map(a => `<a class='pill-link' href='${BASE}/batches/${currentBatchId}/download/${escapeHtml(a.path)}' target='_blank'>${escapeHtml(a.type || 'download')} ↓</a>`).join('')}
        <button class='pill-link' data-pair='${escapeHtml(p.pair_id)}'>view events →</button>
      </div>
    `;
    card.querySelector('button[data-pair]').addEventListener('click', () => {
      document.getElementById('evt-pair').value = p.pair_id;
      document.querySelector('.tab-line[data-detail-tab="events"]').click();
      applyEventsFilter();
    });
    list.appendChild(card);
  }
}

// -------- documents --------
function renderDocs(s) {
  const grid = document.getElementById('docs-grid');
  const docs = s.documents || [];
  if (!docs.length) { grid.innerHTML = "<div class='empty'>(пока нет документов)</div>"; return; }
  grid.innerHTML = '';
  for (const d of docs) {
    const card = document.createElement('div');
    card.className = 'doc-card';
    const rankLabel = ({1: 'official_npa', 2: 'departmental', 3: 'analytics'})[d.source_rank || 3];
    card.innerHTML = `
      <div class='name'>${escapeHtml(d.filename || d.title || d.doc_id || '?')}</div>
      <div class='meta'>
        <div class='l'>doc_type</div><div class='v'>${escapeHtml(d.doc_type || '—')}</div>
        <div class='l'>rank</div><div class='v rank-${d.source_rank || 3}'>${d.source_rank || 3} (${rankLabel})</div>
        <div class='l'>blocks</div><div class='v'>${d.block_count ?? '—'}</div>
        <div class='l'>cache</div><div class='v'>${d.cache_extract_hit ? '<span style="color:var(--green)">hit</span>' : '<span class="muted">—</span>'}</div>
      </div>
      <div class='sha'>${escapeHtml((d.sha256 || '').slice(0, 32))}…</div>
      ${d.source_url ? `<div style='margin-top:6px'><a href='${escapeHtml(d.source_url)}' target='_blank' style='font-size:11.5px'>↗ source</a></div>` : ''}
    `;
    grid.appendChild(card);
  }
}

// -------- anchor selector + rerender --------
function renderAnchorSelector(s) {
  const sel = document.getElementById('anchor-select');
  if (!sel) return;
  const docs = s.documents || [];
  const current = s.anchor_doc_id || '';
  sel.innerHTML = '<option value="">(no anchor)</option>' + docs.map(d =>
    `<option value="${escapeHtml(d.doc_id)}" ${d.doc_id === current ? 'selected' : ''}>${escapeHtml(d.filename || d.doc_id)}</option>`
  ).join('');
}
document.getElementById('btn-rerender').addEventListener('click', async () => {
  if (!currentBatchId) return;
  const anchor = document.getElementById('anchor-select').value;
  const btn = document.getElementById('btn-rerender');
  btn.disabled = true; btn.textContent = '...rendering';
  try {
    const url = '/batches/' + currentBatchId + '/render' + (anchor ? '?anchor_doc_id=' + encodeURIComponent(anchor) : '');
    const r = await fetch(BASE + url, { method: 'POST' }).then(r => r.json());
    toast(`Rerendered: ${r.events ?? 0} events / ${r.pairs ?? 0} pairs`, 'success');
    openBatch(currentBatchId);
  } catch (e) {
    toast('Rerender failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = '↻ Rerender';
  }
});

// -------- audit log --------
async function loadAudit(batchId) {
  const list = document.getElementById('audit-list');
  list.innerHTML = "<div class='empty'><span class='spinner'></span></div>";
  try {
    const r = await fetch(BASE + '/batches/' + batchId + '/audit').then(r => r.json());
    const entries = r.entries || [];
    if (!entries.length) { list.innerHTML = "<div class='empty'>(audit log empty)</div>"; return; }
    list.innerHTML = '<table class="evt-table"><thead><tr><th style="width:140px">when</th><th style="width:120px">action</th><th style="width:140px">actor</th><th style="width:140px">target</th><th>payload</th></tr></thead><tbody>' +
      entries.map(en => `
        <tr>
          <td class='muted mono' style='font-size:11.5px'>${escapeHtml(en.created_at || '')}</td>
          <td><span class='chip chip-low'>${escapeHtml(en.action || '?')}</span></td>
          <td>${escapeHtml(en.actor || '—')}</td>
          <td class='muted mono' style='font-size:11.5px'>${escapeHtml((en.target_kind || '') + ' ' + (en.target_id || ''))}</td>
          <td class='mono muted' style='font-size:11.5px'>${escapeHtml(JSON.stringify(en.payload || {}))}</td>
        </tr>`).join('') + '</tbody></table>';
  } catch (e) {
    list.innerHTML = `<div class='empty'>Audit unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

// -------- artifacts --------
function renderArtifacts(s) {
  const list = document.getElementById('arts-list');
  const arts = s.artifacts || [];
  if (!arts.length) { list.innerHTML = "<div class='empty'>(нет артефактов)</div>"; return; }
  list.innerHTML = '';
  for (const a of arts) {
    const card = document.createElement('div');
    card.className = 'art-card';
    card.innerHTML = `
      <div class='info'>
        <div class='type'>${escapeHtml(a.type || '?')}</div>
        <div class='name'>${escapeHtml(a.title || a.path || '')}</div>
      </div>
      <a class='pill-link' href='${BASE}/batches/${currentBatchId}/download/${escapeHtml(a.path)}' target='_blank'>↓ download</a>
    `;
    list.appendChild(card);
  }
}

// -------- init --------
function initFromHash() {
  const h = location.hash.slice(1);
  if (h.startsWith('batch/')) {
    const id = h.slice('batch/'.length);
    if (id) { openBatch(id); return; }
  }
  if (h === 'batches') { showView('batches'); refreshBatches(); return; }
  showView('upload');
}

window.addEventListener('hashchange', initFromHash);
initFromHash();
renderStaged();
</script>
</body>
</html>
"""
