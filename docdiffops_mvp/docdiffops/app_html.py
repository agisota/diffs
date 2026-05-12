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
<script src="/static/pdfjs/pdf.min.js"></script>
<script>
  // pdf.js worker must be configured before any getDocument call.
  // Bundled locally by Dockerfile to avoid uncontrolled CDN dependency.
  if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/pdfjs/pdf.worker.min.js';
  }
</script>
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
.tab.active { color: var(--strong); background: var(--panel-2); border-color: var(--blue-dim); box-shadow: inset 0 0 0 1px var(--blue-dim); }
.tab:hover:not(.active) { color: var(--fg); background: var(--panel-2); }
.topbar .ext { display: flex; gap: 14px; color: var(--mute); font-size: 12px; align-items: center; flex-wrap: wrap; }
.topbar .ext a { color: var(--mute); }
@media (max-width: 700px) { .topbar .ext { font-size: 11px; gap: 8px; } }
.dot-online { width: 8px; height: 8px; border-radius: 50%; background: var(--green); display: inline-block; box-shadow: 0 0 8px var(--green); }
kbd { background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px; padding: 1px 6px; font-family: ui-monospace, monospace; font-size: 11.5px; }

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
.progress-bar { height: 6px; background: var(--panel-2); border-radius: 3px; overflow: hidden; margin: 10px 0; }
.progress-bar > div { height: 100%; background: var(--blue); transition: width 0.3s ease; border-radius: 3px; }
#progress-label { font-size: 13px; }

/* ------------------- batch list ------------------- */
.batches-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.batch-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad-lg); padding: 16px; cursor: pointer; transition: all 0.15s ease; }
.batch-card:hover { border-color: var(--blue-dim); transform: translateY(-1px); }
.batch-card .id { font-family: ui-monospace, monospace; font-size: 11px; color: var(--mute); }
.batch-card .title { font-size: 15px; font-weight: 600; margin: 4px 0 12px; }
.batch-card .row { display: flex; justify-content: space-between; font-size: 12px; color: var(--mute); padding: 3px 0; }
.batch-card .row .v { color: var(--fg); font-weight: 500; font-variant-numeric: tabular-nums; }
.batch-card .when { font-size: 11px; color: var(--mute); margin-top: 8px; }
.batch-card button.batch-del:hover { color: var(--red); }

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
.kpi.accepted .v { color: var(--green); }
.kpi.rejected .v { color: var(--red); }
.kpi.pending .v { color: var(--amber); }

.tabs-line { display: flex; gap: 2px; border-bottom: 1px solid var(--line); margin-bottom: 16px; }
.tab-line { background: transparent; border: 0; color: var(--mute); padding: 10px 16px; border-bottom: 2px solid transparent; font-size: 13px; }
.tab-line.active { color: var(--strong); border-color: var(--blue); }

/* ------------------- events ------------------- */
.events-toolbar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.events-toolbar input, .events-toolbar select { background: var(--panel); border: 1px solid var(--line); color: var(--fg); padding: 7px 10px; border-radius: 5px; font-size: 13px; }
.events-toolbar input { flex: 1 1 280px; }
.events-toolbar .count { color: var(--mute); font-size: 12px; align-self: center; margin-left: auto; }

.evt-table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); overflow: hidden; }
.evt-table th { background: var(--panel-2); text-align: left; padding: 10px 12px; font-size: 12px; font-weight: 600; color: var(--mute); border-bottom: 1px solid var(--line); position: sticky; top: 48px; z-index: 5; box-shadow: 0 1px 0 var(--line); }
.evt-table td { padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; font-size: 13px; }
.evt-table tr:last-child td { border-bottom: 0; }
.evt-table tr:hover td { background: rgba(76,195,255,0.04); cursor: pointer; }
.evt-table tr.expanded td { background: rgba(76,195,255,0.08); }
.quote-cell { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
.pair-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); padding: 12px 14px; transition: all 0.15s ease; }
.pair-card:hover { border-color: var(--blue-dim); transform: translateY(-1px); }
.pair-card .head { display: flex; justify-content: space-between; align-items: center; gap: 14px; }
.pair-card .pair-id { font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--mute); }
.pair-card .docs { font-size: 14px; font-weight: 500; word-break: break-word; overflow-wrap: anywhere; }
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

/* ------------------- v10 forensic bundle ------------------- */
.v10-bundle { margin-top: 20px; border: 1px solid var(--line); border-radius: var(--rad); padding: 14px 18px; background: var(--panel); }
.v10-bundle h3 { margin: 0 0 12px; font-size: 14px; font-weight: 600; letter-spacing: 0.01em; }
.v10-links { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px; margin: 0; padding: 0; list-style: none; }
.v10-links li { display: flex; align-items: center; gap: 8px; }
.v10-links .v10-pill { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 5px 12px; border-radius: 4px; font-size: 12px; text-decoration: none; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.v10-links .v10-pill:hover { border-color: var(--blue); text-decoration: none; }
.v10-stub { font-size: 11.5px; color: var(--mute); margin-top: 10px; }

/* ------------------- global progress bar ------------------- */
.global-progress { margin: 0 0 18px; padding: 10px 14px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad); }
.global-progress .gp-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 6px; }
.global-progress .gp-head .gp-title { color: var(--mute); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }
.global-progress .gp-head .gp-stats { color: var(--fg); font-variant-numeric: tabular-nums; font-family: ui-monospace, monospace; font-size: 12.5px; }
.global-progress .gp-bar { height: 7px; background: var(--panel-2); border-radius: 4px; overflow: hidden; display: flex; }
.global-progress .gp-bar > div { height: 100%; transition: width 0.4s ease; }
.global-progress .gp-bar .seg-conf { background: var(--green); }
.global-progress .gp-bar .seg-rej { background: var(--red); }
.global-progress .gp-pct { font-weight: 600; font-size: 13px; }
.global-progress.gp-done .gp-pct { color: var(--green); }
.global-progress .gp-pct.gp-low { color: var(--amber); }

/* ------------------- toast ------------------- */
.toast-wrap { position: fixed; bottom: 24px; right: 24px; display: flex; flex-direction: column; gap: 8px; z-index: 100; }
.toast { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--blue); border-radius: 5px; padding: 10px 14px 10px 14px; min-width: 240px; box-shadow: var(--shadow); animation: slide-in 0.2s ease; font-size: 13px; display: flex; align-items: flex-start; gap: 10px; }
.toast .toast-msg { flex: 1; }
.toast .toast-x { background: transparent; border: 0; color: var(--mute); font-size: 15px; line-height: 1; cursor: pointer; flex-shrink: 0; padding: 0; margin-top: 1px; }
.toast .toast-x:hover { color: var(--fg); }
.toast.error { border-left-color: var(--red); }
.toast.success { border-left-color: var(--green); }
@keyframes slide-in { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

/* ------------------- empty / loading ------------------- */
.empty { text-align: center; color: var(--mute); padding: 40px; font-style: italic; }
.empty::before { display: block; font-size: 28px; margin-bottom: 10px; font-style: normal; content: attr(data-icon); }
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

/* ------------------- inline viewer modal (M1) ------------------- */
.viewer-modal { position: fixed; inset: 0; background: var(--bg); z-index: 60; display: flex; flex-direction: column; }
.viewer-modal[hidden] { display: none; }
.viewer-modal .vm-head {
  display: flex; align-items: center; gap: 16px; padding: 10px 18px;
  background: var(--panel); border-bottom: 1px solid var(--line); flex-shrink: 0;
}
.viewer-modal .vm-head h3 { margin: 0; font-size: 14px; font-weight: 600; }
.viewer-modal .vm-head .pair-id { color: var(--mute); font-family: ui-monospace, monospace; font-size: 11.5px; }
.viewer-modal .vm-head .spacer { flex: 1; }
.viewer-modal .vm-head .vm-pager { display: flex; align-items: center; gap: 6px; color: var(--mute); font-size: 12px; }
.viewer-modal .vm-head .vm-pager button { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 3px 10px; border-radius: 4px; font-size: 12px; }
.viewer-modal .vm-head .vm-pager button:disabled { opacity: 0.4; cursor: not-allowed; }
.viewer-modal .vm-zoom { display: flex; align-items: center; gap: 6px; color: var(--mute); font-size: 12px; margin-right: 8px; }
.viewer-modal .vm-zoom button { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 3px 9px; border-radius: 4px; font-size: 13px; font-weight: 600; line-height: 1; }
.viewer-modal .vm-zoom button:hover { border-color: var(--blue); }
.viewer-modal .vm-zoom .zoom-val { font-family: ui-monospace, monospace; min-width: 42px; text-align: center; font-size: 11.5px; }
.viewer-modal .vm-close { background: transparent; border: 1px solid var(--line); color: var(--mute); padding: 5px 12px; border-radius: 5px; font-size: 13px; }
.viewer-modal .vm-close:hover { color: var(--red); border-color: var(--red); }
.viewer-modal .vm-head .vm-search { display: flex; align-items: center; gap: 4px; margin-right: 8px; }
.viewer-modal .vm-head .vm-search input { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 3px 8px; border-radius: 4px; font-size: 12px; width: 160px; }
.viewer-modal .vm-head .vm-search .results { font-size: 11px; color: var(--mute); font-family: ui-monospace, monospace; min-width: 50px; text-align: center; }
.viewer-modal .vm-head .vm-search button { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 3px 8px; border-radius: 4px; font-size: 11px; }
.pdf-page-wrap .search-hit { position: absolute; background: rgba(255,214,10,0.45); border: 1px solid rgba(255,214,10,0.8); border-radius: 2px; pointer-events: none; }
.pdf-page-wrap .search-hit.is-current { background: rgba(255,165,0,0.7); border-color: rgba(255,140,0,1); }
.viewer-modal .vm-head .vm-mode { display: flex; gap: 2px; margin-right: 8px; }
.viewer-modal .vm-head .vm-mode button { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 3px 10px; font-size: 11px; }
.viewer-modal .vm-head .vm-mode button.active { background: var(--blue); color: #04111a; border-color: var(--blue); font-weight: 600; }
.viewer-modal .vp-text { padding: 16px 20px; overflow: auto; background: var(--bg); font-family: ui-sans-serif, sans-serif; line-height: 1.6; font-size: 13.5px; }
.viewer-modal .vp-text .block { padding: 6px 10px; margin: 2px 0; border-radius: 3px; }
.viewer-modal .vp-text .block.added { background: rgba(46,194,126,0.18); border-left: 3px solid var(--green); }
.viewer-modal .vp-text .block.deleted { background: rgba(229,72,77,0.18); border-left: 3px solid var(--red); text-decoration: line-through; opacity: 0.75; }
.viewer-modal .vp-text .block.modified, .viewer-modal .vp-text .block.partial { background: rgba(255,178,36,0.14); border-left: 3px solid var(--amber); }
.viewer-modal .vp-text .block.same { background: var(--panel); border-left: 3px solid var(--line); }
.viewer-modal .vp-text .block:hover { box-shadow: 0 0 0 1px var(--blue); cursor: pointer; }
.viewer-modal .vp-text .block-meta { font-size: 10.5px; color: var(--mute); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 2px; }
.bookmark-btn { background: transparent; border: 0; color: var(--mute); cursor: pointer; font-size: 13px; padding: 0 4px; }
.bookmark-btn.is-marked { color: var(--amber); }

.viewer-modal .vm-body {
  flex: 1; min-height: 0; display: grid;
  grid-template-columns: 56px 1fr 1fr 320px; gap: 1px; background: var(--line);
}
.viewer-modal .vm-minimap { background: var(--panel); overflow-y: auto; padding: 6px 4px; display: flex; flex-direction: column; gap: 4px; align-items: center; }
.viewer-modal .vm-minimap .mp-page { width: 44px; cursor: pointer; position: relative; border: 1px solid var(--line); background: var(--panel-2); border-radius: 3px; padding: 6px 2px; text-align: center; }
.viewer-modal .vm-minimap .mp-page.active { border-color: var(--blue); box-shadow: 0 0 0 1px var(--blue); }
.viewer-modal .vm-minimap .mp-page .mp-num { font-size: 9.5px; color: var(--mute); font-family: ui-monospace, monospace; }
.viewer-modal .vm-minimap .mp-dots { display: flex; flex-wrap: wrap; gap: 2px; justify-content: center; margin-top: 3px; min-height: 6px; }
.viewer-modal .vm-minimap .mp-dot { width: 5px; height: 5px; border-radius: 50%; }
.viewer-modal .vm-minimap .mp-dot.added { background: var(--green); }
.viewer-modal .vm-minimap .mp-dot.deleted { background: var(--red); }
.viewer-modal .vm-minimap .mp-dot.modified, .viewer-modal .vm-minimap .mp-dot.partial { background: var(--amber); }
.viewer-modal .vm-pane { background: var(--panel); display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.viewer-modal .vm-pane .vp-head {
  padding: 6px 12px; border-bottom: 1px solid var(--line);
  background: var(--panel-2); font-size: 12px; font-weight: 600;
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.viewer-modal .vm-pane .vp-head .side {
  display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 10.5px; letter-spacing: 0.06em; text-transform: uppercase;
}
.viewer-modal .vm-pane .vp-head .side.lhs { background: rgba(229,72,77,0.18); color: var(--red); }
.viewer-modal .vm-pane .vp-head .side.rhs { background: rgba(46,194,126,0.18); color: var(--green); }
.viewer-modal .vm-pane .vp-head .fname { color: var(--fg); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; }
.viewer-modal .vm-pane .vp-body { flex: 1; min-height: 0; overflow: auto; padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 16px; background: #1a1d24; }
.viewer-modal .vm-pane .vp-loading { color: var(--mute); padding: 40px; font-size: 13px; font-style: italic; }
.viewer-modal .vm-pane .vp-error { color: var(--red); padding: 40px; font-size: 13px; }

.pdf-page-wrap { position: relative; box-shadow: 0 2px 12px rgba(0,0,0,0.4); }
.pdf-page-wrap canvas { display: block; }
.pdf-page-wrap .pdf-overlay { position: absolute; inset: 0; pointer-events: none; }
.pdf-page-wrap .pdf-page-num { position: absolute; top: -22px; left: 0; color: var(--mute); font-size: 11px; font-family: ui-monospace, monospace; }
.bbox-hi { position: absolute; border-radius: 2px; pointer-events: auto; cursor: pointer; transition: box-shadow 0.15s ease; }
.bbox-hi:hover, .bbox-hi.is-active { box-shadow: 0 0 0 2px var(--blue), 0 0 12px rgba(76,195,255,0.5); }
.bbox-hi-added { background: rgba(46,194,126,0.22); border: 1px solid rgba(46,194,126,0.7); }
.bbox-hi-deleted { background: rgba(229,72,77,0.22); border: 1px solid rgba(229,72,77,0.7); }
.bbox-hi-modified, .bbox-hi-partial { background: rgba(255,178,36,0.22); border: 1px solid rgba(255,178,36,0.7); }
.bbox-hi-contradicts, .bbox-hi-manual_review { background: rgba(229,72,77,0.30); border: 1px solid var(--red); }
.bbox-hi-same { background: rgba(46,194,126,0.08); border: 1px dashed rgba(46,194,126,0.5); }

.viewer-modal .vm-sidebar { background: var(--panel); display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.viewer-modal .vm-sidebar .vs-head {
  padding: 8px 12px; border-bottom: 1px solid var(--line); background: var(--panel-2);
  font-size: 11.5px; color: var(--mute); text-transform: uppercase; letter-spacing: 0.06em; flex-shrink: 0;
}
.viewer-modal .vm-sidebar .vs-filter { padding: 8px 10px; border-bottom: 1px solid var(--line); }
.viewer-modal .vm-sidebar .vs-filter input { width: 100%; background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 8px 10px; border-radius: 4px; font-size: 12.5px; }
.viewer-modal .vm-sidebar .vs-list { flex: 1; min-height: 0; overflow: auto; }
.viewer-event-row {
  padding: 8px 10px; border-bottom: 1px solid var(--line); cursor: pointer; font-size: 12.5px;
  display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; align-items: start;
}
.viewer-event-row:hover { background: var(--panel-2); }
.viewer-event-row.is-active { background: rgba(76,195,255,0.10); border-left: 3px solid var(--blue); padding-left: 7px; }
.viewer-event-row .ev-chip { grid-row: 1; grid-column: 1; }
.viewer-event-row .ev-pages { grid-row: 1; grid-column: 2; color: var(--mute); font-size: 11px; text-align: right; font-family: ui-monospace, monospace; }
.viewer-event-row .ev-quote { grid-row: 2; grid-column: 1 / -1; color: var(--mute); font-size: 12px; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.viewer-event-row .ev-id { grid-row: 3; grid-column: 1 / -1; color: var(--mute); font-family: ui-monospace, monospace; font-size: 10.5px; }

.viewer-modal .ev-popover {
  position: fixed; z-index: 70; background: var(--panel); border: 1px solid var(--blue);
  border-radius: 6px; padding: 12px 14px; box-shadow: var(--shadow);
  min-width: 280px; max-width: 380px;
}
.viewer-modal .ev-popover .pop-head {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
  font-size: 11px; color: var(--mute); text-transform: uppercase; letter-spacing: 0.05em;
}
.viewer-modal .ev-popover .pop-close { background: transparent; border: 0; color: var(--mute); cursor: pointer; font-size: 14px; }
.viewer-modal .ev-popover .pop-body { font-size: 12.5px; line-height: 1.5; }
.viewer-modal .ev-popover .pop-body .quote { background: var(--bg); border-left: 3px solid var(--gray); padding: 6px 10px; margin: 6px 0; border-radius: 3px; max-height: 5em; overflow: auto; font-size: 12px; }
.viewer-modal .ev-popover .pop-body .quote.lhs { border-left-color: var(--red); }
.viewer-modal .ev-popover .pop-body .quote.rhs { border-left-color: var(--green); }
.viewer-modal .ev-popover textarea { width: 100%; background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 6px 8px; border-radius: 4px; font-size: 12px; margin-top: 6px; resize: vertical; min-height: 50px; }
.viewer-modal .ev-popover .pop-actions { display: flex; gap: 8px; margin-top: 10px; }
.viewer-modal .ev-popover button.accept { background: rgba(46,194,126,0.2); border: 1px solid var(--green); color: var(--green); padding: 6px 14px; border-radius: 5px; font-size: 12px; font-weight: 600; flex: 1; }
.viewer-modal .ev-popover button.reject { background: rgba(229,72,77,0.18); border: 1px solid var(--red); color: var(--red); padding: 6px 14px; border-radius: 5px; font-size: 12px; font-weight: 600; flex: 1; }
.viewer-modal .ev-popover button:disabled { opacity: 0.4; cursor: wait; }
.viewer-modal .ev-popover .pop-prev { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line); font-size: 11.5px; color: var(--mute); }
.pair-card .thumbs { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; min-height: 0; }
.pair-card .thumbs .thumb { background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 4px; min-height: 60px; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; }
.pair-card .thumbs .thumb canvas { width: 100%; height: auto; display: block; max-height: 180px; object-fit: contain; }
.pair-card .thumbs .thumb .side-lbl { position: absolute; top: 3px; left: 4px; font-size: 9px; text-transform: uppercase; letter-spacing: 0.06em; padding: 1px 5px; border-radius: 2px; font-weight: 600; }
.pair-card .thumbs .thumb .side-lbl.lhs { background: rgba(229,72,77,0.7); color: white; }
.pair-card .thumbs .thumb .side-lbl.rhs { background: rgba(46,194,126,0.7); color: white; }
.pair-card .thumbs .thumb-empty { color: var(--mute); font-size: 11px; font-style: italic; }
.pair-card .review-progress { margin-top: 10px; }
.pair-card .review-progress .pbar { height: 5px; background: var(--panel-2); border-radius: 3px; overflow: hidden; display: flex; }
.pair-card .review-progress .pbar > div { height: 100%; transition: width 0.3s ease; }
.pair-card .review-progress .pbar .seg-conf { background: var(--green); }
.pair-card .review-progress .pbar .seg-rej { background: var(--red); }
.pair-card .review-progress .plabel { font-size: 11px; color: var(--mute); margin-top: 4px; display: flex; justify-content: space-between; }
.pair-card .review-progress .plabel .pct { font-variant-numeric: tabular-nums; }
.bulk-actions { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
.bulk-actions button { background: var(--panel-2); border: 1px solid var(--line); color: var(--fg); padding: 3px 10px; border-radius: 4px; font-size: 11.5px; cursor: pointer; }
.bulk-actions button:hover { border-color: var(--blue); }
.bulk-actions button.danger:hover { border-color: var(--red); color: var(--red); }

/* ------------------- welcome empty state ------------------- */
.welcome-empty { text-align: center; padding: 80px 24px; background: var(--panel); border: 1px dashed var(--line); border-radius: var(--rad-lg); }
.welcome-empty .welcome-icon { font-size: 64px; opacity: 0.7; margin-bottom: 12px; }
.welcome-empty h2 { margin: 0 0 8px; font-size: 22px; color: var(--strong); }
.welcome-empty p { margin: 0 0 20px; color: var(--mute); max-width: 480px; margin-left: auto; margin-right: auto; line-height: 1.6; }
.welcome-empty .btn-primary { padding: 12px 28px; font-size: 14px; }
.welcome-empty .welcome-formats { margin-top: 24px; font-size: 11.5px; color: var(--mute); font-family: ui-monospace, monospace; }

/* ------------------- skeleton loading ------------------- */
.skel-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--rad-lg); padding: 16px; }
.skel-card .skel-line { height: 10px; background: linear-gradient(90deg, var(--panel-2) 0%, #1d2330 50%, var(--panel-2) 100%); background-size: 200% 100%; border-radius: 3px; margin: 5px 0; animation: skel-shimmer 1.4s infinite linear; }
.skel-card .skel-line.short { width: 50%; }
.skel-card .skel-line.med { width: 80%; }
@keyframes skel-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* ------------------- status donut ------------------- */
.status-donut { display: inline-flex; align-items: center; gap: 12px; }
.status-donut svg { display: block; }
.status-donut .legend { display: flex; flex-direction: column; gap: 3px; font-size: 11.5px; }
.status-donut .legend .li { display: flex; align-items: center; gap: 6px; }
.status-donut .legend .dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }

/* ------------------- severity ribbon on pair-card ------------------- */
.pair-card { position: relative; }
.pair-card.has-high::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: linear-gradient(180deg, var(--red), rgba(229,72,77,0.4));
  border-radius: var(--rad) 0 0 var(--rad);
}
.pair-card.has-medium::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: linear-gradient(180deg, var(--amber), rgba(255,178,36,0.4));
  border-radius: var(--rad) 0 0 var(--rad);
}
.pair-card { padding-left: 16px; }

/* ------------------- viewer keyboard hint footer ------------------- */
.viewer-modal .vm-foot { background: var(--panel-2); border-top: 1px solid var(--line); padding: 6px 14px; font-size: 11px; color: var(--mute); display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; flex-shrink: 0; }
.viewer-modal .vm-foot .kb { display: inline-flex; align-items: center; gap: 4px; }
.viewer-modal .vm-foot .kb kbd { background: var(--panel); border: 1px solid var(--line); border-radius: 3px; padding: 1px 5px; font-family: ui-monospace, monospace; font-size: 10.5px; color: var(--fg); }

/* ------------------- active event pulse animation ------------------- */
@keyframes bbox-pulse {
  0% { box-shadow: 0 0 0 0 rgba(76,195,255,0.7); }
  50% { box-shadow: 0 0 0 6px rgba(76,195,255,0); }
  100% { box-shadow: 0 0 0 0 rgba(76,195,255,0); }
}
.bbox-hi.is-active { animation: bbox-pulse 1.8s infinite ease-out; }
.viewer-event-row.is-active { box-shadow: inset 4px 0 0 var(--blue); transition: box-shadow 0.2s ease; }

/* ------------------- topbar stats counter ------------------- */
.topbar-stats { color: var(--mute); font-size: 11.5px; font-family: ui-monospace, monospace; padding: 3px 8px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 4px; }
.topbar-stats strong { color: var(--fg); font-weight: 600; }
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
    <span id="topbar-stats" class="topbar-stats" title="Всего batches/events"></span>
    <a href="#" onclick="document.getElementById('help-modal').hidden=false;return false" title="Горячие клавиши">⌨️ Горячие клавиши</a>
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
    <div id="batches-empty" class="welcome-empty" style="display:none">
      <div class="welcome-icon">📋</div>
      <h2>Здесь пока пусто</h2>
      <p>Создай свой первый batch — загрузи 2 или больше документов, чтобы их сравнить.</p>
      <button class="btn btn-primary" onclick="document.querySelector('[data-view=upload]').click()">
        ↗ Перейти к загрузке
      </button>
      <div class="welcome-formats">Поддерживается: PDF, DOCX, PPTX, XLSX, HTML, TXT, MD, CSV, XML</div>
    </div>
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
    <div id="status-donut-block" style="margin-bottom:18px"></div>
    <div id="global-progress-block"></div>

    <div class="tabs-line">
      <button class="tab-line active" data-detail-tab="events">События</button>
      <button class="tab-line" data-detail-tab="pairs">Пары</button>
      <button class="tab-line" data-detail-tab="docs">Документы</button>
      <button class="tab-line" data-detail-tab="artifacts">Артефакты</button>
      <button class="tab-line" data-detail-tab="topics">Topics</button>
      <button class="tab-line" data-detail-tab="audit">Audit</button>
      <span style="margin-left:auto;align-self:center;display:flex;gap:6px;align-items:center">
        <span class="muted" style="font-size:12px">Anchor:</span>
        <select id="anchor-select" class="batch-input" style="margin:0;width:auto;min-width:160px;font-size:12.5px;padding:4px 8px"></select>
        <button class="btn" id="btn-rerender" style="padding:5px 10px;font-size:12px" title="Перерендерить отчёты по существующим событиям">↻ Rerender</button>
        <button class="btn" id="btn-rerender-compare" style="padding:5px 10px;font-size:12px;background:rgba(76,195,255,0.12);border-color:var(--blue-dim);color:var(--blue)" title="Пересчитать сравнение по существующим extract'ам (применяет последние фиксы pipeline без re-upload)">🔄 Пересчитать compare</button>
        <button class="btn" id="btn-rerender-full" style="padding:5px 10px;font-size:12px;background:rgba(255,178,36,0.12);border-color:#7a5c1a;color:var(--amber)" title="Полный rerender: re-extract + re-compare. Долго на больших батчах. Применяется когда нужно подхватить новый normalize/extract для старых документов.">🔁 Полный rerender</button>
        <a class="btn" id="btn-merged-zip" style="padding:5px 10px;font-size:12px;background:rgba(46,194,126,0.10);border-color:#1c5a3a;color:var(--green);text-decoration:none" href="#" title="Скачать все merged.docx архивом ZIP">📦 Все merged.zip</a>
        <a class="btn" id="btn-events-csv" style="padding:5px 10px;font-size:12px" href="#" title="Экспорт всех событий в CSV (UTF-8 BOM, Excel-friendly)">📊 CSV events</a>
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
        <thead><tr><th style="width:90px">event</th><th style="width:100px">status</th><th style="width:90px">severity</th><th style="width:60px">conf</th><th style="width:130px">decision</th><th>LHS quote</th><th>RHS quote</th></tr></thead>
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
      <div id="v10-bundle-block" hidden></div>
    </div>

    <div id="dtab-topics" class="dtab" hidden>
      <div id="topics-list"></div>
    </div>

    <div id="dtab-audit" class="dtab" hidden>
      <div id="audit-list"></div>
    </div>
  </section>

</main>

<div id="help-modal" hidden style="position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:80;display:flex;align-items:center;justify-content:center" onclick="if(event.target===this)this.hidden=true">
  <div style="background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:24px 28px;max-width:520px;width:90%;box-shadow:var(--shadow)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0;font-size:16px">⌨️ Горячие клавиши</h3>
      <button style="background:transparent;border:0;color:var(--mute);font-size:18px;cursor:pointer" onclick="document.getElementById('help-modal').hidden=true">✕</button>
    </div>
    <table style="width:100%;font-size:13px;border-collapse:collapse">
      <tr><td colspan="2" style="padding:6px 0 4px;color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:0.06em">В inline viewer</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>J</kbd></td><td>Следующее событие (pending → reviewed)</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>K</kbd></td><td>Предыдущее событие</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>A</kbd></td><td>Принять (Accept) активное событие</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>R</kbd></td><td>Отклонить (Reject) активное событие</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>+</kbd> / <kbd>−</kbd></td><td>Zoom in / out</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>0</kbd></td><td>Fit-to-width</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>Esc</kbd></td><td>Закрыть viewer</td></tr>
      <tr><td colspan="2" style="padding:10px 0 4px;color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:0.06em">Везде</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><kbd>?</kbd></td><td>Эта подсказка</td></tr>
    </table>
    <div style="margin-top:14px;color:var(--mute);font-size:11.5px">A/R автоматически прыгают к следующему pending событию. Принятые/отклонённые правки скрыты по умолчанию (галка «hide accepted/rejected» в sidebar).</div>
  </div>
</div>

<div id="viewer-modal" class="viewer-modal" hidden>
  <div class="vm-head">
    <h3>📖 Inline viewer</h3>
    <span class="pair-id" id="vm-pair-id"></span>
    <div class="spacer"></div>
    <div class="vm-mode">
      <button id="vm-mode-pdf" class="active" data-mode="pdf">PDF</button>
      <button id="vm-mode-text" data-mode="text">Текст</button>
    </div>
    <div class="vm-search">
      <input id="vm-search-input" placeholder="Поиск в документе…">
      <span class="results" id="vm-search-results"></span>
      <button id="vm-search-prev" title="Previous match">↑</button>
      <button id="vm-search-next" title="Next match">↓</button>
    </div>
    <div class="vm-zoom">
      <button id="vm-zoom-out" title="Уменьшить">−</button>
      <span class="zoom-val" id="vm-zoom-val">140%</span>
      <button id="vm-zoom-in" title="Увеличить">+</button>
      <button id="vm-zoom-fit" title="По ширине">⤢</button>
    </div>
    <div class="vm-pager" id="vm-pager-lhs">
      <button data-side="lhs" data-dir="-1">◀</button>
      <span><span id="vm-page-lhs">1</span> / <span id="vm-pages-lhs">?</span></span>
      <button data-side="lhs" data-dir="1">▶</button>
    </div>
    <div class="vm-pager" id="vm-pager-rhs">
      <button data-side="rhs" data-dir="-1">◀</button>
      <span><span id="vm-page-rhs">1</span> / <span id="vm-pages-rhs">?</span></span>
      <button data-side="rhs" data-dir="1">▶</button>
    </div>
    <button class="vm-close" id="vm-close">Close ✕</button>
  </div>
  <div class="vm-body">
    <div class="vm-minimap" id="vm-minimap"><div style="color:var(--mute);font-size:10px;padding:6px 0">map</div></div>
    <div class="vm-pane">
      <div class="vp-head"><span class="side lhs">LHS</span><span class="fname" id="vm-lhs-name">—</span></div>
      <div class="vp-body" id="vm-lhs-body"><div class="vp-loading">Loading…</div></div>
    </div>
    <div class="vm-pane">
      <div class="vp-head"><span class="side rhs">RHS</span><span class="fname" id="vm-rhs-name">—</span></div>
      <div class="vp-body" id="vm-rhs-body"><div class="vp-loading">Loading…</div></div>
    </div>
    <div class="vm-sidebar">
      <div class="vs-head">События <span id="vm-events-count" class="mono"></span></div>
      <div class="vs-filter">
        <input id="vm-filter" placeholder="Filter quote/status…">
        <label style="display:flex;align-items:center;gap:6px;margin-top:6px;font-size:11.5px;color:var(--mute);cursor:pointer">
          <input type="checkbox" id="vm-hide-decided" checked> hide accepted/rejected
        </label>
        <label style="display:flex;align-items:center;gap:6px;margin-top:4px;font-size:11.5px;color:var(--mute);cursor:pointer">
          <input type="checkbox" id="vm-only-bookmarks"> только ★ bookmarks
        </label>
      </div>
      <div class="vs-list" id="vm-events-list"></div>
    </div>
  </div>
  <div class="vm-foot">
    <span class="kb"><kbd>J</kbd>/<kbd>K</kbd> следующее/предыдущее</span>
    <span class="kb"><kbd>A</kbd> принять</span>
    <span class="kb"><kbd>R</kbd> отклонить</span>
    <span class="kb"><kbd>+</kbd>/<kbd>−</kbd>/<kbd>0</kbd> zoom</span>
    <span class="kb"><kbd>Esc</kbd> закрыть</span>
    <span class="kb"><kbd>?</kbd> помощь</span>
  </div>
  <div id="ev-popover" class="ev-popover" hidden></div>
</div>

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
  const msgSpan = document.createElement('span');
  msgSpan.className = 'toast-msg';
  msgSpan.textContent = msg;
  const xBtn = document.createElement('button');
  xBtn.className = 'toast-x';
  xBtn.textContent = '✕';
  xBtn.setAttribute('aria-label', 'dismiss');
  xBtn.addEventListener('click', () => { el.style.opacity = '0'; setTimeout(() => el.remove(), 200); });
  el.appendChild(msgSpan);
  el.appendChild(xBtn);
  document.getElementById('toast-wrap').appendChild(el);
  // error toasts persist until dismissed; success=4s, info=3s
  if (kind !== 'error') {
    const delay = kind === 'success' ? 4000 : 3000;
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 200); }, delay);
  }
}

// -------- browser notifications --------
function _maybeNotify(title, body, kind) {
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'granted') return;
  try {
    const n = new Notification(title, {
      body: body,
      tag: 'docdiff-' + (currentBatchId || ''),
    });
    setTimeout(() => n.close(), 8000);
  } catch (_) {}
}

// Ask for permission on first interaction (button click). Polite — not on page load.
function _askNotifyPermissionOnce() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {});
  }
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

function docIcon(d) {
  const ext = (d && d.ext || '').toLowerCase();
  const t = (d && d.doc_type || '').toUpperCase();
  if (ext === '.pdf' || t.includes('LEGAL') || t.includes('NPA')) return '📄';
  if (ext === '.docx' || ext === '.doc') return '📝';
  if (ext === '.pptx' || ext === '.ppt' || t === 'PRESENTATION') return '🎨';
  if (ext === '.xlsx' || ext === '.xls' || ext === '.csv' || t === 'TABLE') return '📊';
  if (ext === '.html' || ext === '.htm' || t === 'WEB_ARTICLE' || t === 'WEB_DIGEST') return '🌐';
  if (ext === '.txt' || ext === '.md') return '📃';
  return '📎';
}

function renderStatusDonut(events) {
  const buckets = {};
  for (const e of events || []) {
    const s = (e.status || 'other').toLowerCase();
    buckets[s] = (buckets[s] || 0) + 1;
  }
  const colors = {same: '#2ec27e', partial: '#ffb224', modified: '#ffb224',
                  added: '#4cc3ff', deleted: '#e5484d', contradicts: '#e5484d',
                  manual_review: '#e5484d', other: '#5b6473'};
  const total = Object.values(buckets).reduce((a,b)=>a+b, 0);
  if (!total) return '';
  const r = 30, cx = 35, cy = 35;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  const segs = Object.entries(buckets).filter(([_,v])=>v>0).map(([k,v]) => {
    const pct = v / total;
    const len = circ * pct;
    const s = `<circle cx='${cx}' cy='${cy}' r='${r}' fill='none' stroke='${colors[k]||colors.other}' stroke-width='10' stroke-dasharray='${len} ${circ}' stroke-dashoffset='${-offset}' transform='rotate(-90 ${cx} ${cy})'/>`;
    offset += len;
    return s;
  }).join('');
  const legend = Object.entries(buckets).filter(([_,v])=>v>0).map(([k,v]) =>
    `<div class='li'><span class='dot' style='background:${colors[k]||colors.other}'></span><span>${escapeHtml(k)} <strong>${v}</strong></span></div>`
  ).join('');
  return `<div class='status-donut'>
    <svg width='70' height='70'>${segs}<text x='35' y='40' text-anchor='middle' fill='var(--fg)' font-size='15' font-weight='600'>${total}</text></svg>
    <div class='legend'>${legend}</div>
  </div>`;
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
  _askNotifyPermissionOnce();
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

    // Async path: large corpora take 30+ minutes — sync=true would time out
    // at the reverse proxy. Kick off via Celery worker and poll /tasks/{id}.
    progLabel.textContent = 'Запуск pipeline…'; progFill.style.width = '75%';
    const kicked = await fetch(BASE + '/batches/' + batchId + '/run?profile=fast', { method: 'POST' }).then(r => r.json());
    const taskId = kicked.task_id;
    if (!taskId) throw new Error('worker did not accept task: ' + JSON.stringify(kicked));

    progLabel.textContent = 'Pipeline в работе (это может занять 5–60 минут на больших корпусах)…';
    progFill.style.width = '80%';
    let pollDelay = 2000;  // start at 2s, back off to 15s
    let result = null;
    while (true) {
      await new Promise(r => setTimeout(r, pollDelay));
      const t = await fetch(BASE + '/tasks/' + taskId).then(r => r.json());
      if (t.state === 'SUCCESS') {
        result = t.result || {};
        _maybeNotify('DocDiffOps: pipeline готов', `Batch ${batchId.slice(-8)}: ${(result.events ?? 0)} событий`);
        break;
      }
      if (t.state === 'FAILURE') throw new Error('pipeline failed: ' + (t.result || 'no detail'));
      pollDelay = Math.min(15000, pollDelay + 1000);
    }
    progFill.style.width = '100%';
    const events = result.events ?? 0;
    const dur = result.time_to_report_sec ?? '?';
    progLabel.textContent = `Готово: ${events} событий за ${dur}s`;
    toast(`Batch ${batchId.slice(-8)} готов: ${events} событий`, 'success');
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
  grid.innerHTML = Array(6).fill(0).map(() => `
    <div class='skel-card'>
      <div class='skel-line short'></div>
      <div class='skel-line med' style='height:14px;margin-top:8px'></div>
      <div class='skel-line'></div>
      <div class='skel-line short'></div>
      <div class='skel-line med'></div>
    </div>
  `).join('');
  try {
    const list = await fetch(BASE + '/batches').then(r => r.json());
    document.getElementById('batches-count').textContent = list.length;
    document.getElementById('batches-empty').style.display = list.length === 0 ? '' : 'none';
    grid.innerHTML = '';
    // Update topbar dashboard counter
    const stats = document.getElementById('topbar-stats');
    if (stats && list.length) {
      const totalEvents = list.reduce((a, b) => a + (b.diff_events_count || 0), 0);
      const totalHigh = list.reduce((a, b) => a + (b.high_count || 0), 0);
      stats.innerHTML = `📊 <strong>${list.length}</strong> batches · <strong>${totalEvents}</strong> events${totalHigh ? ` · <span style='color:var(--red)'>${totalHigh} high</span>` : ''}`;
    } else if (stats) {
      stats.textContent = '';
    }
    list.sort((a, b) => (b.updated_at || b.created_at || '').localeCompare(a.updated_at || a.created_at || ''));
    for (const b of list) {
      const card = document.createElement('div');
      card.className = 'batch-card';
      const total = b.diff_events_count ?? b.events ?? 0;
      const high = b.high_count ?? 0;
      card.innerHTML = `
        <div style='display:flex;justify-content:space-between;align-items:start;gap:8px'>
          <div class='id'>${escapeHtml(b.batch_id || '')}</div>
          <button class='batch-del' data-bid='${escapeHtml(b.batch_id)}' title='Удалить batch' style='background:transparent;border:0;color:var(--mute);cursor:pointer;font-size:13px;padding:0 4px'>🗑</button>
        </div>
        <div class='title'>${escapeHtml(b.title || '(untitled)')}</div>
        <div class='row'><span>Документы</span><span class='v'>${b.documents_count ?? '—'}</span></div>
        <div class='row'><span>Пар</span><span class='v'>${b.pair_runs_count ?? '—'}</span></div>
        <div class='row'><span>Событий</span><span class='v'>${total}</span></div>
        ${high ? `<div class='row'><span>High risk</span><span class='v' style='color:var(--red)'>${high}</span></div>` : ''}
        <div class='when'>${escapeHtml(b.updated_at || b.created_at || '')}</div>
      `;
      card.addEventListener('click', () => openBatch(b.batch_id));
      const delBtn = card.querySelector('button.batch-del');
      if (delBtn) {
        delBtn.addEventListener('click', async (ev) => {
          ev.stopPropagation();
          if (!confirm(`Удалить batch ${b.batch_id.slice(-8)} ${b.title ? '"' + b.title + '"' : ''}? Это удалит все документы, события, артефакты, review-decisions безвозвратно.`)) return;
          try {
            await fetch(BASE + '/batches/' + b.batch_id, {method: 'DELETE'}).then(r => r.json());
            toast('Batch удалён: ' + b.batch_id.slice(-8), 'success');
            refreshBatches();
          } catch (e) {
            toast('Удалить не удалось: ' + e.message, 'error');
          }
        });
      }
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
    document.getElementById('status-donut-block').innerHTML = renderStatusDonut(s.diff_events || []);
    renderGlobalProgress(s);
    renderEvents(s);
    renderPairs(s);
    renderDocs(s);
    renderArtifacts(s);
    renderAnchorSelector(s);
    loadAudit(batchId);
    loadTopics(batchId);
    // Default to the Pairs tab when the batch has pairs — that's where
    // the inline viewer lives. Events tab was the original "table of
    // parameters" the user complained about; Pairs is closer to the
    // "document-as-document" experience.
    const pairsCount = (s.pair_runs || s.pairs || []).length;
    if (pairsCount >= 1) {
      const pairsTabBtn = document.querySelector('.tab-line[data-detail-tab="pairs"]');
      if (pairsTabBtn) pairsTabBtn.click();
    }
    // M5+ polish: when the batch has exactly one pair, auto-open the
    // inline viewer for it — no extra click needed. Best UX for the
    // "compare two specific documents" workflow.
    if (pairsCount === 1) {
      const onlyPair = (s.pair_runs || s.pairs || [])[0];
      if (onlyPair && onlyPair.pair_id) {
        setTimeout(() => {
          try { openInlineViewer(onlyPair.pair_id); } catch (_) {}
        }, 300);  // small delay so detailState is fully painted
      }
    }
    location.hash = '#batch/' + batchId;
  } catch (e) {
    document.getElementById('detail-kpis').innerHTML = `<div class='empty'>Ошибка: ${escapeHtml(e.message)}</div>`;
  }
}

document.getElementById('btn-refresh-detail').addEventListener('click', () => currentBatchId && openBatch(currentBatchId));

function renderGlobalProgress(s) {
  const block = document.getElementById('global-progress-block');
  if (!block) return;
  const evs = s.diff_events || [];
  if (!evs.length) { block.innerHTML = ''; return; }
  const conf = evs.filter(e => e.last_review && e.last_review.decision === 'confirmed').length;
  const rej = evs.filter(e => e.last_review && e.last_review.decision === 'rejected').length;
  const total = evs.length;
  const decided = conf + rej;
  const pct = total > 0 ? Math.round(decided / total * 100) : 0;
  const cw = total > 0 ? (conf / total * 100) : 0;
  const rw = total > 0 ? (rej / total * 100) : 0;
  const done = pct === 100;
  const lowClass = pct < 30 ? 'gp-low' : '';
  block.innerHTML = `
    <div class='global-progress ${done ? 'gp-done' : ''}'>
      <div class='gp-head'>
        <span class='gp-title'>Прогресс review</span>
        <span class='gp-stats'>
          <span style='color:var(--green)'>✓ ${conf}</span> ·
          <span style='color:var(--red)'>✗ ${rej}</span> ·
          <span style='color:var(--amber)'>⏳ ${total - decided} pending</span> ·
          <span class='gp-pct ${lowClass}'>${pct}%</span>
        </span>
      </div>
      <div class='gp-bar'>
        <div class='seg-conf' style='width:${cw}%'></div>
        <div class='seg-rej' style='width:${rw}%'></div>
      </div>
    </div>
  `;
}

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
    { v: events.filter(e => e.last_review && (e.last_review.decision === 'confirmed')).length, l: '✓ Accepted', cls: 'accepted' },
    { v: events.filter(e => e.last_review && (e.last_review.decision === 'rejected')).length, l: '✗ Rejected', cls: 'rejected' },
    { v: events.filter(e => !e.last_review).length, l: 'Pending', cls: 'pending' },
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
      <td>${e.last_review ? `<span class='chip chip-${escapeHtml((e.last_review.decision||'').replace(/_/g,'-'))}' title='${escapeHtml((e.last_review.reviewer_name||'?') + ' · ' + (e.last_review.decided_at||''))}'>${escapeHtml(e.last_review.decision||'')}</span>` : `<span class='muted' style='font-size:11px'>—</span>`}</td>
      <td class='muted quote-cell'>${highlight(e.lhs?.quote, q)}</td>
      <td class='muted quote-cell'>${highlight(e.rhs?.quote, q)}</td>
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
    <td colspan='7' class='evt-detail'><div class='inner'>
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
      ${e.semantic ? `<div style='margin-top:10px;padding:10px 12px;background:rgba(76,195,255,0.06);border-left:3px solid var(--blue);border-radius:4px'>
        <div class='muted' style='font-size:11px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px'>LLM verdict <span class='mono' style='font-size:10.5px'>(${escapeHtml(e.semantic.model||'?')})</span></div>
        <div><span class='chip chip-${escapeHtml(e.semantic.status||'low')}'>${escapeHtml(e.semantic.status||'?')}</span> <span class='muted' style='font-size:11.5px'>conf=${escapeHtml(e.semantic.confidence||0)}</span></div>
        ${e.semantic.rationale ? `<div style='margin-top:4px;font-size:13px'>${escapeHtml(e.semantic.rationale)}</div>` : ''}
      </div>` : ''}
      <div class='review-panel' data-evid='${escapeHtml(e.event_id)}' style='margin-top:14px;padding-top:12px;border-top:1px solid var(--line)'>
        <div class='muted' style='font-size:11px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px'>Review</div>
        <div style='display:grid;grid-template-columns:1fr 1fr 2fr auto;gap:8px;align-items:end'>
          <input class='review-name batch-input' placeholder='Your name' value='${escapeHtml(reviewerName)}' style='margin:0'>
          <select class='review-decision batch-input' style='margin:0'>
            <option value='confirmed'>confirmed</option>
            <option value='rejected'>rejected</option>
            <option value='needs_more_info'>needs more info</option>
            <option value='deferred'>deferred</option>
            <option value='comment'>💬 comment only</option>
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
  if (!history.length) { container.innerHTML = "<div class='muted' style='font-size:12px;font-style:italic'>(пока никто не оставил decision/комментарий)</div>"; return; }
  // Sort oldest-first to read top-down like a chat.
  const sorted = (history || []).slice().sort((a, b) => (a.decided_at || '').localeCompare(b.decided_at || ''));
  container.innerHTML = '<div class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px">Лента действий</div>' +
    sorted.map(h => {
      const isComment = (h.decision || '').toLowerCase() === 'comment';
      const chipCls = isComment ? 'chip-low' : 'chip-' + escapeHtml((h.decision || '').replace(/_/g, '-'));
      const icon = isComment ? '💬' : (h.decision === 'confirmed' ? '✓' : (h.decision === 'rejected' ? '✗' : '•'));
      return `
        <div style='padding:8px 10px;margin:4px 0;background:var(--bg);border-left:3px solid ${isComment ? 'var(--blue)' : 'var(--line)'};border-radius:3px;font-size:12.5px'>
          <div style='display:flex;gap:8px;align-items:center'>
            <span>${icon}</span>
            <span class='chip ${chipCls}'>${escapeHtml(h.decision || '')}</span>
            <strong>${escapeHtml(h.reviewer_name || 'anonymous')}</strong>
            <span class='muted' style='font-size:11px;margin-left:auto'>${escapeHtml(h.decided_at || '')}</span>
          </div>
          ${h.comment ? `<div style='margin-top:4px;padding-left:24px'>${escapeHtml(h.comment)}</div>` : ''}
        </div>
      `;
    }).join('');
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
  // Pair summaries are stored separately as artifacts; build a quick
  // lookup so we can attach narrative text to each pair card.
  const summariesByPair = (s.pair_summaries || []).reduce((m, x) => (m[x.pair_id] = x, m), {});
  const pairs = s.pair_runs || s.pairs || [];
  if (!pairs.length) { list.innerHTML = "<div class='empty' data-icon='💤'>(пока нет пар)</div>"; return; }
  const arts = (s.artifacts || []);
  for (const p of pairs) {
    const lhs = docs[p.lhs_doc_id] || {};
    const rhs = docs[p.rhs_doc_id] || {};
    // Attach narrative from pair_summaries lookup (best-effort).
    p.narrative = p.narrative || (summariesByPair[p.pair_id] || {}).narrative;
    const card = document.createElement('div');
    const ev = (s.diff_events || []).filter(e => e.pair_id === p.pair_id);
    const same = ev.filter(e => e.status === 'same').length;
    const partial = ev.filter(e => e.status === 'partial').length;
    const added = ev.filter(e => e.status === 'added').length;
    const deleted = ev.filter(e => e.status === 'deleted').length;
    const high = ev.filter(e => e.severity === 'high').length;
    card.className = 'pair-card' + (high > 0 ? ' has-high' : (ev.some(e => e.severity === 'medium') ? ' has-medium' : ''));
    const pairArts = arts.filter(a => (a.path || '').includes(p.pair_id));
    const pairEvents = ev;
    const reviewedCount = pairEvents.filter(e => e.last_review).length;
    const confCount = pairEvents.filter(e => e.last_review && e.last_review.decision === 'confirmed').length;
    const rejCount = pairEvents.filter(e => e.last_review && e.last_review.decision === 'rejected').length;
    const totalEv = pairEvents.length;
    const progressPct = totalEv > 0 ? Math.round((confCount + rejCount) / totalEv * 100) : 0;
    const confW = totalEv > 0 ? (confCount / totalEv * 100) : 0;
    const rejW = totalEv > 0 ? (rejCount / totalEv * 100) : 0;
    card.innerHTML = `
      <div class='head'>
        <div style='flex:1;min-width:0'>
          <div class='pair-id'>${escapeHtml(p.pair_id || '')}</div>
          <div class='docs'>
            <span class='rank-${lhs.source_rank || 3}'><span style='margin-right:4px'>${docIcon(lhs)}</span>${escapeHtml(lhs.filename || lhs.doc_id || p.lhs_doc_id || '?')}</span>
            <span class='arrow'>↔</span>
            <span class='rank-${rhs.source_rank || 3}'><span style='margin-right:4px'>${docIcon(rhs)}</span>${escapeHtml(rhs.filename || rhs.doc_id || p.rhs_doc_id || '?')}</span>
          </div>
        </div>
        <div style='text-align:right'>
          ${(summariesByPair[p.pair_id] || {}).score_pct != null ? `
            <div style='font-size:24px;font-weight:600;line-height:1;color:${(summariesByPair[p.pair_id].score_pct >= 70 ? 'var(--green)' : summariesByPair[p.pair_id].score_pct >= 40 ? 'var(--amber)' : 'var(--red)')}'>${summariesByPair[p.pair_id].score_pct}</div>
            <div class='muted' style='font-size:10px;text-transform:uppercase;letter-spacing:0.06em'>${escapeHtml((summariesByPair[p.pair_id].score_band||''))}</div>
          ` : `<div class='muted mono' style='font-size:12px'>${ev.length} events</div>`}
        </div>
      </div>
      ${p.narrative ? `<div style='margin-top:8px;padding:10px 12px;background:rgba(76,195,255,0.05);border-left:3px solid var(--blue);border-radius:4px;font-size:13px;line-height:1.5'>${escapeHtml(p.narrative)}</div>` : ''}
      <div class='stats'>
        <div>same <span>${same}</span></div>
        <div>partial <span>${partial}</span></div>
        <div>+ <span>${added}</span></div>
        <div>− <span>${deleted}</span></div>
        ${high ? `<div style='color:var(--red)'>high <span style='color:var(--red)'>${high}</span></div>` : ''}
        ${reviewedCount > 0 ? `<div style='color:var(--blue)'>reviewed <span style='color:var(--blue)'>${reviewedCount}</span></div>` : ''}
      </div>
      ${totalEv > 0 ? `<div class='review-progress'>
        <div class='pbar'>
          <div class='seg-conf' style='width:${confW}%'></div>
          <div class='seg-rej' style='width:${rejW}%'></div>
        </div>
        <div class='plabel'><span>Прогресс review</span><span class='pct'>${confCount + rejCount} / ${totalEv} <span style='color:var(--mute)'>(${progressPct}%)</span></span></div>
      </div>` : ''}
      ${totalEv > 0 ? `<div class='bulk-actions'>
        <button data-bulk-pair='${escapeHtml(p.pair_id)}' data-bulk-status='same' data-bulk-decision='confirmed' title='Принять все same'>✓ same (${pairEvents.filter(e => e.status === 'same' && !e.last_review).length})</button>
        <button data-bulk-pair='${escapeHtml(p.pair_id)}' data-bulk-severity='low' data-bulk-decision='confirmed' title='Принять все low severity'>✓ low (${pairEvents.filter(e => (e.severity || 'low') === 'low' && !e.last_review).length})</button>
        <button data-bulk-pair='${escapeHtml(p.pair_id)}' data-bulk-status='added' data-bulk-decision='rejected' class='danger' title='Отклонить все added'>✗ added (${pairEvents.filter(e => e.status === 'added' && !e.last_review).length})</button>
      </div>` : ''}
      <div class='thumbs' data-pair-id='${escapeHtml(p.pair_id)}'>
        <div class='thumb' data-side='lhs' data-doc='${escapeHtml(p.lhs_doc_id || '')}'><span class='side-lbl lhs'>LHS</span><span class='thumb-empty'>…</span></div>
        <div class='thumb' data-side='rhs' data-doc='${escapeHtml(p.rhs_doc_id || '')}'><span class='side-lbl rhs'>RHS</span><span class='thumb-empty'>…</span></div>
      </div>
      <button data-viewer-pair='${escapeHtml(p.pair_id)}' style='margin-top:12px;width:100%;padding:10px 16px;background:linear-gradient(135deg, #4cc3ff, #2b95cc);color:#04111a;border:0;border-radius:6px;font-weight:600;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px'>
        📖 Открыть документы с подсветкой правок
      </button>
      <div class='links' style='margin-top:8px'>
        ${pairArts.map(a => `<a class='pill-link' href='${BASE}/batches/${currentBatchId}/download/${escapeHtml(a.path)}' target='_blank'>${escapeHtml(a.type || 'download')} ↓</a>`).join('')}
        <button class='pill-link' data-pair='${escapeHtml(p.pair_id)}'>view events →</button>
        ${reviewedCount > 0 ? `<a class='pill-link' href='${BASE}/batches/${currentBatchId}/pair/${escapeHtml(p.pair_id)}/merged.docx' target='_blank' title='Скачать итоговый DOCX с применёнными accept/reject решениями'>📥 merged</a>` : ''}
      </div>
    `;
    card.querySelector('button[data-pair]').addEventListener('click', () => {
      document.getElementById('evt-pair').value = p.pair_id;
      document.querySelector('.tab-line[data-detail-tab="events"]').click();
      applyEventsFilter();
    });
    const viewerBtn = card.querySelector('button[data-viewer-pair]');
    if (viewerBtn) viewerBtn.addEventListener('click', () => openInlineViewer(p.pair_id));
    card.querySelectorAll('button[data-bulk-pair]').forEach(bb => {
      bb.addEventListener('click', () => bulkReview(
        bb.dataset.bulkPair, bb.dataset.bulkStatus || null, bb.dataset.bulkSeverity || null, bb.dataset.bulkDecision
      ));
    });
    list.appendChild(card);
  }
  // Lazy-render thumbnails using IntersectionObserver — avoid rendering
  // every pair's PDF upfront which is expensive for 60+ pair stress batches.
  const thumbObserver = new IntersectionObserver(async (entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      const thumb = en.target;
      thumbObserver.unobserve(thumb);
      const docId = thumb.dataset.doc;
      if (!docId || !window.pdfjsLib) continue;
      try {
        const pdf = await pdfjsLib.getDocument({url: BASE + '/batches/' + currentBatchId + '/docs/' + docId + '/canonical.pdf'}).promise;
        const page = await pdf.getPage(1);
        const baseViewport = page.getViewport({scale: 1.0});
        const scale = 180 / baseViewport.width;  // target ~180px width
        const viewport = page.getViewport({scale});
        const canvas = document.createElement('canvas');
        canvas.width = viewport.width; canvas.height = viewport.height;
        await page.render({canvasContext: canvas.getContext('2d'), viewport}).promise;
        const empty = thumb.querySelector('.thumb-empty');
        if (empty) empty.remove();
        thumb.appendChild(canvas);
      } catch (_) {
        const empty = thumb.querySelector('.thumb-empty');
        if (empty) empty.textContent = '(нет PDF)';
      }
    }
  }, {rootMargin: '100px'});
  document.querySelectorAll('.pair-card .thumb').forEach(t => thumbObserver.observe(t));
}

async function bulkReview(pairId, statusFilter, severityFilter, decision) {
  const evs = (detailState?.diff_events || []).filter(e => {
    if (e.pair_id !== pairId) return false;
    if (e.last_review) return false;
    if (statusFilter && e.status !== statusFilter) return false;
    if (severityFilter && (e.severity || 'low') !== severityFilter) return false;
    return true;
  });
  if (!evs.length) { toast('Нет событий для применения', 'info'); return; }
  const label = `${decision === 'confirmed' ? 'Принять' : 'Отклонить'} ${evs.length} событий`;
  if (!confirm(label + '?')) return;
  const name = localStorage.getItem('docdiff:reviewer') || prompt('Your name:', '') || 'anonymous';
  localStorage.setItem('docdiff:reviewer', name);
  toast(label + '…', 'info');
  let ok = 0, fail = 0;
  await Promise.all(evs.map(async e => {
    try {
      await fetch(BASE + '/events/' + e.event_id + '/review', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({decision, reviewer_name: name, comment: 'bulk action'})
      });
      ok++;
    } catch (_) { fail++; }
  }));
  toast(`Готово: ${ok} обновлено${fail ? ', ' + fail + ' failed' : ''}`, fail ? 'error' : 'success');
  openBatch(currentBatchId);
}

// -------- documents --------
function renderDocs(s) {
  const grid = document.getElementById('docs-grid');
  const docs = s.documents || [];
  if (!docs.length) { grid.innerHTML = "<div class='empty' data-icon='📭'>(пока нет документов)</div>"; return; }
  grid.innerHTML = '';
  for (const d of docs) {
    const card = document.createElement('div');
    card.className = 'doc-card';
    const rankLabel = ({1: 'official_npa', 2: 'departmental', 3: 'analytics'})[d.source_rank || 3];
    card.innerHTML = `
      <div class='name'><span style='margin-right:6px;font-size:16px'>${docIcon(d)}</span>${escapeHtml(d.filename || d.title || d.doc_id || '?')}</div>
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
async function _runAsyncRerender(endpoint, label) {
  if (!currentBatchId) return;
  _askNotifyPermissionOnce();
  const confirmMsg = endpoint === 'rerender-compare'
    ? 'Запустить пересчёт compare для всех пар? Это применит последние фиксы pipeline без re-upload. Review_decisions сохранятся.'
    : 'Полный rerender: удалит кэшированные extract\'ы и пересоберёт всё заново. На больших батчах может занять минуты. Review_decisions сохранятся. Продолжить?';
  if (!confirm(confirmMsg)) return;
  const btn = document.getElementById('btn-' + endpoint);
  const orig = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳ запуск…';
  try {
    const kicked = await fetch(BASE + '/batches/' + currentBatchId + '/' + endpoint, { method: 'POST' }).then(r => r.json());
    const taskId = kicked.task_id;
    if (!taskId) {
      // sync mode fallback — already finished
      const m = kicked.metrics || {};
      toast(`${label} готов: ${m.pairs ?? 0} пар, ${m.events ?? 0} событий за ${m.time_to_report_sec ?? '?'}s`, 'success');
      openBatch(currentBatchId);
      return;
    }
    let pollDelay = 1500;
    let elapsed = 0;
    while (true) {
      await new Promise(r => setTimeout(r, pollDelay));
      elapsed += pollDelay / 1000;
      btn.textContent = '⏳ ' + Math.round(elapsed) + 's';
      const t = await fetch(BASE + '/tasks/' + taskId).then(r => r.json());
      if (t.state === 'SUCCESS') {
        const m = t.result || {};
        const msg = `${label} готов: ${m.pairs ?? 0} пар, ${m.events ?? 0} событий за ${m.time_to_report_sec ?? '?'}s`;
        toast(msg, 'success');
        _maybeNotify('DocDiffOps: ' + label + ' готов', `${m.pairs ?? 0} пар, ${m.events ?? 0} событий`, 'success');
        openBatch(currentBatchId);
        break;
      }
      if (t.state === 'FAILURE') throw new Error(label + ' failed: ' + JSON.stringify(t.result));
      pollDelay = Math.min(10000, pollDelay + 1000);
    }
  } catch (e) {
    toast(label + ' failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

document.getElementById('btn-rerender-compare').addEventListener('click', () => _runAsyncRerender('rerender-compare', 'Compare'));
document.getElementById('btn-rerender-full').addEventListener('click', () => _runAsyncRerender('rerender-full', 'Полный rerender'));
document.getElementById('btn-merged-zip').addEventListener('click', (e) => {
  e.preventDefault();
  if (!currentBatchId) return;
  const a = document.createElement('a');
  a.href = BASE + '/batches/' + currentBatchId + '/merged.zip?t=' + Date.now();
  a.download = 'merged_' + currentBatchId.slice(-8) + '.zip';
  document.body.appendChild(a); a.click(); a.remove();
  toast('Архив генерируется… скачивание начнётся через несколько секунд', 'info');
});

document.getElementById('btn-events-csv').addEventListener('click', e => {
  e.preventDefault();
  if (!currentBatchId) return;
  const a = document.createElement('a');
  a.href = BASE + '/batches/' + currentBatchId + '/events.csv';
  a.download = 'events_' + currentBatchId.slice(-8) + '.csv';
  document.body.appendChild(a); a.click(); a.remove();
});

// -------- inline viewer (M1) --------
const viewerState = {
  pairId: null,
  lhsPdf: null,
  rhsPdf: null,
  lhsPage: 1,
  rhsPage: 1,
  events: [],
  activeEventId: null,
  zoom: 1.4,  // pdf.js render scale; updated by zoom controls
  mode: 'pdf',  // 'pdf' | 'text'
  searchHits: [],
  searchActive: -1,
  searchQuery: '',
  searchIndex: null,
};

async function _viewerSetZoom(newZoom) {
  viewerState.zoom = Math.max(0.5, Math.min(3.5, newZoom));
  document.getElementById('vm-zoom-val').textContent = Math.round(viewerState.zoom * 100) + '%';
  // re-render current pages on both sides
  const promises = [];
  if (viewerState.lhsPdf) promises.push(renderPdfPage('lhs', viewerState.lhsPage));
  if (viewerState.rhsPdf) promises.push(renderPdfPage('rhs', viewerState.rhsPage));
  await Promise.all(promises);
}

async function _viewerFitToWidth() {
  const lhsPdf = viewerState.lhsPdf;
  if (!lhsPdf) return;
  try {
    const page = await lhsPdf.getPage(viewerState.lhsPage);
    const baseViewport = page.getViewport({scale: 1.0});
    const paneBody = document.getElementById('vm-lhs-body');
    const availW = paneBody.clientWidth - 40;  // 32px padding + 8px buffer
    const fit = availW / baseViewport.width;
    await _viewerSetZoom(fit);
  } catch (_) {}
}

function _pairArtifactPath(state, pairId, basename) {
  const arts = state && state.artifacts || [];
  for (const a of arts) {
    if (!a || !a.path) continue;
    if (a.path.endsWith('/' + basename) && a.path.includes(pairId)) return a.path;
  }
  return null;
}

// Try canonical_pdf endpoint first (works for DOCX/PPTX/HTML/PDF), then
// fall back to per-pair annotated PDFs (lhs_red / rhs_green) if those exist.
async function _loadPdfForSide(side, pair, pairId) {
  const docId = side === 'lhs' ? pair.lhs_doc_id : pair.rhs_doc_id;
  // 1. canonical PDF of the document (primary source for M2)
  if (docId) {
    try {
      const url = BASE + '/batches/' + currentBatchId + '/docs/' + docId + '/canonical.pdf';
      const head = await fetch(url, {method: 'HEAD'});
      if (head.ok) {
        return await pdfjsLib.getDocument({url}).promise;
      }
    } catch (_) { /* fall through */ }
  }
  // 2. fallback: per-pair annotated PDF (works only when both sources were PDF)
  const basename = side === 'lhs' ? 'lhs_red.pdf' : 'rhs_green.pdf';
  const p = _pairArtifactPath(detailState, pairId, basename);
  if (p) {
    const url = BASE + '/batches/' + currentBatchId + '/download/' + p;
    try { return await pdfjsLib.getDocument({url}).promise; } catch (_) { /* nothing */ }
  }
  return null;
}

async function openInlineViewer(pairId) {
  if (!window.pdfjsLib) { toast('pdf.js not loaded', 'error'); return; }
  const modal = document.getElementById('viewer-modal');
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  viewerState.pairId = pairId;
  localStorage.setItem('docdiff:lastPair', pairId);
  viewerState.lhsPage = 1; viewerState.rhsPage = 1;
  viewerState.activeEventId = null;
  document.getElementById('vm-pair-id').textContent = pairId;
  const pair = (detailState.pair_runs || detailState.pairs || []).find(x => x.pair_id === pairId) || {};
  const docs = (detailState.documents || []).reduce((m, d) => (m[d.doc_id] = d, m), {});
  document.getElementById('vm-lhs-name').textContent = (docs[pair.lhs_doc_id] || {}).filename || pair.lhs_doc_id || '?';
  document.getElementById('vm-rhs-name').textContent = (docs[pair.rhs_doc_id] || {}).filename || pair.rhs_doc_id || '?';
  document.getElementById('vm-lhs-body').innerHTML = "<div class='vp-loading'>Loading LHS PDF…</div>";
  document.getElementById('vm-rhs-body').innerHTML = "<div class='vp-loading'>Loading RHS PDF…</div>";
  viewerState.events = (detailState.diff_events || []).filter(e => e.pair_id === pairId);
  viewerState.searchIndex = null;
  viewerState.searchHits = []; viewerState.searchActive = -1; viewerState.searchQuery = '';
  const sri = document.getElementById('vm-search-input'); if (sri) sri.value = '';
  const srr = document.getElementById('vm-search-results'); if (srr) srr.textContent = '';
  renderViewerSidebar('');
  try {
    const [lhs, rhs] = await Promise.all([
      _loadPdfForSide('lhs', pair, pairId).catch(() => null),
      _loadPdfForSide('rhs', pair, pairId).catch(() => null),
    ]);
    viewerState.lhsPdf = lhs;
    viewerState.rhsPdf = rhs;
    if (!lhs && !rhs) {
      document.getElementById('vm-lhs-body').innerHTML = "<div class='vp-error'>PDF-артефакты для этой пары не найдены. Возможно, документы не были сконвертированы в PDF при normalize (старый батч до фикса HTML/TXT нормализации). Перезалейте файлы и повторите прогон.</div>";
      document.getElementById('vm-rhs-body').innerHTML = "";
      return;
    }
    if (lhs) {
      document.getElementById('vm-pages-lhs').textContent = lhs.numPages;
      const lhsStart = Math.min(lhs.numPages, parseInt(localStorage.getItem('docdiff:lastPage:' + pairId + ':lhs') || '1', 10) || 1);
      await renderPdfPage('lhs', lhsStart);
    } else {
      document.getElementById('vm-lhs-body').innerHTML = "<div class='vp-error'>LHS PDF недоступен. Документ не был сконвертирован в PDF при normalize (возможно старый батч до фикса HTML/TXT нормализации). Перезалейте файл и повторите прогон.</div>";
    }
    if (rhs) {
      document.getElementById('vm-pages-rhs').textContent = rhs.numPages;
      const rhsStart = Math.min(rhs.numPages, parseInt(localStorage.getItem('docdiff:lastPage:' + pairId + ':rhs') || '1', 10) || 1);
      await renderPdfPage('rhs', rhsStart);
    } else {
      document.getElementById('vm-rhs-body').innerHTML = "<div class='vp-error'>RHS PDF недоступен. Документ не был сконвертирован в PDF при normalize (возможно старый батч до фикса HTML/TXT нормализации). Перезалейте файл и повторите прогон.</div>";
    }
  } catch (e) {
    toast('Viewer error: ' + e.message, 'error');
  }
}

async function renderPdfPage(side, pageNo) {
  const pdf = side === 'lhs' ? viewerState.lhsPdf : viewerState.rhsPdf;
  if (!pdf) return;
  pageNo = Math.max(1, Math.min(pdf.numPages, pageNo));
  if (side === 'lhs') viewerState.lhsPage = pageNo; else viewerState.rhsPage = pageNo;
  document.getElementById('vm-page-' + side).textContent = pageNo;
  const body = document.getElementById('vm-' + side + '-body');
  const page = await pdf.getPage(pageNo);
  const viewport = page.getViewport({scale: viewerState.zoom});
  const wrap = document.createElement('div'); wrap.className = 'pdf-page-wrap';
  const num = document.createElement('div'); num.className = 'pdf-page-num'; num.textContent = 'p.' + pageNo + ' / ' + pdf.numPages;
  wrap.appendChild(num);
  const canvas = document.createElement('canvas');
  canvas.width = viewport.width; canvas.height = viewport.height;
  wrap.appendChild(canvas);
  const overlay = document.createElement('div'); overlay.className = 'pdf-overlay';
  overlay.style.width = viewport.width + 'px'; overlay.style.height = viewport.height + 'px';
  wrap.appendChild(overlay);
  body.innerHTML = ''; body.appendChild(wrap);
  await page.render({canvasContext: canvas.getContext('2d'), viewport}).promise;
  drawBboxOverlay(side, pageNo, overlay, viewport);
  try {
    const key = 'docdiff:lastPage:' + (viewerState.pairId || '') + ':' + side;
    localStorage.setItem(key, String(pageNo));
  } catch (_) {}
  renderMinimap();
}

function renderMinimap() {
  const mm = document.getElementById('vm-minimap');
  if (!mm) return;
  const pdf = viewerState.lhsPdf || viewerState.rhsPdf;
  if (!pdf) { mm.innerHTML = ''; return; }
  const numPages = pdf.numPages;
  const evByPage = {};
  for (const e of viewerState.events) {
    const p = (e.lhs && e.lhs.page_no) || (e.rhs && e.rhs.page_no) || (e.lhs_page) || (e.rhs_page);
    if (!p) continue;
    (evByPage[p] = evByPage[p] || []).push(e);
  }
  mm.innerHTML = '';
  for (let p = 1; p <= numPages; p++) {
    const div = document.createElement('div');
    div.className = 'mp-page' + (p === viewerState.lhsPage ? ' active' : '');
    div.innerHTML = '<div class="mp-num">' + p + '</div><div class="mp-dots"></div>';
    const dots = div.querySelector('.mp-dots');
    for (const e of (evByPage[p] || []).slice(0, 6)) {
      const dot = document.createElement('span');
      dot.className = 'mp-dot ' + (e.status || 'same');
      dot.title = (e.status || '') + ': ' + ((e.lhs && e.lhs.quote || e.rhs && e.rhs.quote || '').slice(0, 60));
      dots.appendChild(dot);
    }
    div.addEventListener('click', () => {
      if (viewerState.lhsPdf) renderPdfPage('lhs', p);
      if (viewerState.rhsPdf) renderPdfPage('rhs', p);
    });
    mm.appendChild(div);
  }
}

// -------- search-in-document (A) --------
async function _buildSearchIndex() {
  viewerState.searchIndex = {lhs: [], rhs: []};
  for (const side of ['lhs', 'rhs']) {
    const pdf = side === 'lhs' ? viewerState.lhsPdf : viewerState.rhsPdf;
    if (!pdf) continue;
    for (let p = 1; p <= pdf.numPages; p++) {
      try {
        const page = await pdf.getPage(p);
        const tc = await page.getTextContent();
        const text = tc.items.map(it => it.str).join(' ');
        viewerState.searchIndex[side].push({page: p, text: text.toLowerCase()});
      } catch (_) {}
    }
  }
}

async function _viewerSearch(q) {
  q = (q || '').toLowerCase().trim();
  viewerState.searchQuery = q;
  if (!q) { viewerState.searchHits = []; viewerState.searchActive = -1; _updateSearchUI(); return; }
  if (!viewerState.searchIndex) await _buildSearchIndex();
  const hits = [];
  for (const side of ['lhs', 'rhs']) {
    for (const p of viewerState.searchIndex[side] || []) {
      if (p.text.includes(q)) hits.push({side, page: p.page});
    }
  }
  viewerState.searchHits = hits;
  viewerState.searchActive = hits.length > 0 ? 0 : -1;
  _updateSearchUI();
  if (viewerState.searchActive >= 0) _viewerSearchJump(0);
}

function _updateSearchUI() {
  const r = document.getElementById('vm-search-results');
  if (!r) return;
  if (!viewerState.searchHits.length) {
    r.textContent = viewerState.searchQuery ? 'нет' : '';
  } else {
    r.textContent = (viewerState.searchActive + 1) + '/' + viewerState.searchHits.length;
  }
}

function _viewerSearchJump(delta) {
  if (!viewerState.searchHits.length) return;
  viewerState.searchActive = (viewerState.searchActive + delta + viewerState.searchHits.length) % viewerState.searchHits.length;
  const hit = viewerState.searchHits[viewerState.searchActive];
  renderPdfPage(hit.side, hit.page);
  _updateSearchUI();
}

document.getElementById('vm-search-input').addEventListener('input', e => _viewerSearch(e.target.value));
document.getElementById('vm-search-next').addEventListener('click', () => _viewerSearchJump(1));
document.getElementById('vm-search-prev').addEventListener('click', () => _viewerSearchJump(-1));

// -------- text-mode toggle (B) --------
function _viewerSetMode(mode) {
  viewerState.mode = mode;
  document.getElementById('vm-mode-pdf').classList.toggle('active', mode === 'pdf');
  document.getElementById('vm-mode-text').classList.toggle('active', mode === 'text');
  if (mode === 'pdf') {
    if (viewerState.lhsPdf) renderPdfPage('lhs', viewerState.lhsPage);
    if (viewerState.rhsPdf) renderPdfPage('rhs', viewerState.rhsPage);
  } else {
    _renderTextMode('lhs');
    _renderTextMode('rhs');
  }
}

function _renderTextMode(side) {
  const body = document.getElementById('vm-' + side + '-body');
  if (!body) return;
  body.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.className = 'vp-text';
  const evs = viewerState.events.slice().sort((a, b) => {
    const pa = (a.lhs?.page_no || a.lhs_page || 0), pb = (b.lhs?.page_no || b.lhs_page || 0);
    return pa - pb || (a.event_id || '').localeCompare(b.event_id || '');
  });
  for (const e of evs) {
    const text = (side === 'lhs' ? (e.lhs?.quote) : (e.rhs?.quote)) || '';
    if (!text.trim()) continue;
    const st = e.status || 'same';
    if (side === 'lhs' && st === 'added') continue;
    if (side === 'rhs' && st === 'deleted') continue;
    const block = document.createElement('div');
    block.className = 'block ' + st;
    block.innerHTML = '<div class="block-meta">' + escapeHtml(st) + ' · p.' + escapeHtml(String(e[side]?.page_no || '?')) + '</div>' + escapeHtml(text);
    block.addEventListener('click', () => jumpToEvent(e.event_id));
    wrap.appendChild(block);
  }
  body.appendChild(wrap);
}

document.getElementById('vm-mode-pdf').addEventListener('click', () => _viewerSetMode('pdf'));
document.getElementById('vm-mode-text').addEventListener('click', () => _viewerSetMode('text'));

function drawBboxOverlay(side, pageNo, overlay, viewport) {
  const evs = viewerState.events.filter(e => {
    const p = side === 'lhs' ? (e.lhs && e.lhs.page_no || e.lhs_page) : (e.rhs && e.rhs.page_no || e.rhs_page);
    return p === pageNo;
  });
  for (const e of evs) {
    const bbox = side === 'lhs' ? (e.lhs && e.lhs.bbox || e.lhs_bbox) : (e.rhs && e.rhs.bbox || e.rhs_bbox);
    if (!bbox || bbox.length < 4) continue;
    const [x0, y0, x1, y1] = bbox;
    const [vx0, vy0] = viewport.convertToViewportPoint(x0, y0);
    const [vx1, vy1] = viewport.convertToViewportPoint(x1, y1);
    const left = Math.min(vx0, vx1), top = Math.min(vy0, vy1);
    const width = Math.abs(vx1 - vx0), height = Math.abs(vy1 - vy0);
    const div = document.createElement('div');
    div.className = 'bbox-hi bbox-hi-' + (e.status || 'same');
    div.style.left = left + 'px'; div.style.top = top + 'px';
    div.style.width = width + 'px'; div.style.height = height + 'px';
    div.dataset.evid = e.event_id;
    div.title = (e.status || '?') + ' · ' + (e.severity || 'low') + (e.explanation_short ? ' — ' + e.explanation_short : '');
    if (e.event_id === viewerState.activeEventId) div.classList.add('is-active');
    div.addEventListener('click', () => jumpToEvent(e.event_id));
    overlay.appendChild(div);
  }
}

function renderViewerSidebar(filterQ) {
  const list = document.getElementById('vm-events-list');
  const cnt = document.getElementById('vm-events-count');
  const q = (filterQ || '').toLowerCase();
  const hideDecided = document.getElementById('vm-hide-decided')?.checked ?? true;
  const onlyBookmarks = document.getElementById('vm-only-bookmarks')?.checked ?? false;
  const bookmarks = JSON.parse(localStorage.getItem('docdiff:bookmarks:' + currentBatchId) || '[]');
  const sorted = viewerState.events.slice().sort((a, b) => {
    const pa = (a.lhs && a.lhs.page_no || a.lhs_page || 0), pb = (b.lhs && b.lhs.page_no || b.lhs_page || 0);
    if (pa !== pb) return pa - pb;
    return (a.event_id || '').localeCompare(b.event_id || '');
  });
  // M4: detect xlsx pair → group rows by meta.sheet.
  const docs = (detailState?.documents || []).reduce((m, d) => (m[d.doc_id] = d, m), {});
  const pair = (detailState?.pair_runs || detailState?.pairs || []).find(p => p.pair_id === viewerState.pairId) || {};
  const isXlsxPair = (docs[pair.lhs_doc_id]?.ext === '.xlsx') || (docs[pair.rhs_doc_id]?.ext === '.xlsx');
  // For xlsx, secondary-sort by sheet so groups stay together when we
  // insert sheet headers in the row loop below.
  if (isXlsxPair) {
    sorted.sort((a, b) => {
      const sa = (a.meta?.sheet || a.lhs?.meta?.sheet || '');
      const sb = (b.meta?.sheet || b.lhs?.meta?.sheet || '');
      if (sa !== sb) return sa.localeCompare(sb);
      return (a.event_id || '').localeCompare(b.event_id || '');
    });
  }
  let shown = 0;
  let lastSheet = null;
  list.innerHTML = '';
  for (const e of sorted) {
    if (hideDecided && e.last_review && (e.last_review.decision === 'confirmed' || e.last_review.decision === 'rejected')) continue;
    if (onlyBookmarks && !bookmarks.includes(e.event_id)) continue;
    if (q) {
      const blob = ((e.lhs && e.lhs.quote || '') + ' ' + (e.rhs && e.rhs.quote || '') + ' ' + (e.status || '') + ' ' + (e.event_id || '')).toLowerCase();
      if (blob.indexOf(q) < 0) continue;
    }
    if (isXlsxPair) {
      const sh = (e.meta?.sheet || e.lhs?.meta?.sheet || '(unsheeted)');
      if (sh !== lastSheet) {
        const hdr = document.createElement('div');
        hdr.style.cssText = 'padding:6px 10px;background:var(--panel-2);border-bottom:1px solid var(--line);color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:0.05em;font-weight:600';
        hdr.textContent = '📊 ' + sh;
        list.appendChild(hdr);
        lastSheet = sh;
      }
    }
    const row = document.createElement('div');
    row.className = 'viewer-event-row' + (e.event_id === viewerState.activeEventId ? ' is-active' : '');
    row.dataset.evid = e.event_id;
    const lp = (e.lhs && e.lhs.page_no || e.lhs_page || '?');
    const rp = (e.rhs && e.rhs.page_no || e.rhs_page || '?');
    const hasBbox = (e.lhs?.bbox || e.lhs_bbox || e.rhs?.bbox || e.rhs_bbox);
    const noBboxBadge = hasBbox ? '' : ' <span title="Подсветка bbox недоступна — позиция не сматчилась" style="color:var(--amber);font-size:10px">⚠ no-bbox</span>';
    const stat = (e.status || '').toLowerCase();
    const quote = (e.lhs && e.lhs.quote || e.rhs && e.rhs.quote || '').slice(0, 160);
    const lrChip = e.last_review ?
      '<span class="chip chip-' + escapeHtml((e.last_review.decision||'').replace(/_/g,'-')) + '" style="font-size:9.5px">' + escapeHtml(e.last_review.decision||'') + '</span>' :
      '<button class="pill-link review-btn" data-evid="' + escapeHtml(e.event_id) + '" style="padding:1px 6px;font-size:10px">⚡ review</button>';
    row.innerHTML = '<span class="ev-chip chip chip-' + escapeHtml(stat) + '">' + escapeHtml(stat) + '</span>' +
                    '<span class="ev-pages">L p.' + escapeHtml(String(lp)) + ' · R p.' + escapeHtml(String(rp)) + noBboxBadge + '</span>' +
                    '<div class="ev-quote">' + escapeHtml(quote) + (quote.length >= 160 ? '…' : '') + '</div>' +
                    '<div class="ev-id">' + escapeHtml((e.event_id || '').slice(-12)) + ' ' + lrChip +
                    ' <button class="bookmark-btn ' + (bookmarks.includes(e.event_id) ? 'is-marked' : '') + '" data-bm="' + escapeHtml(e.event_id) + '">★</button>' +
                    '</div>';
    row.addEventListener('click', () => jumpToEvent(e.event_id));
    const rbtn = row.querySelector('button.review-btn');
    if (rbtn) {
      rbtn.addEventListener('click', ev => { ev.stopPropagation(); showEventPopover(e.event_id, rbtn); });
    }
    const bm = row.querySelector('button.bookmark-btn');
    if (bm) bm.addEventListener('click', ev => {
      ev.stopPropagation();
      const list2 = JSON.parse(localStorage.getItem('docdiff:bookmarks:' + currentBatchId) || '[]');
      const idx = list2.indexOf(e.event_id);
      if (idx >= 0) list2.splice(idx, 1); else list2.push(e.event_id);
      localStorage.setItem('docdiff:bookmarks:' + currentBatchId, JSON.stringify(list2));
      bm.classList.toggle('is-marked');
    });
    list.appendChild(row);
    shown++;
  }
  cnt.textContent = shown + ' / ' + viewerState.events.length;
}

async function jumpToEvent(evId) {
  const e = viewerState.events.find(x => x.event_id === evId);
  if (!e) return;
  viewerState.activeEventId = evId;
  const lhsP = e.lhs && e.lhs.page_no || e.lhs_page;
  const rhsP = e.rhs && e.rhs.page_no || e.rhs_page;
  const promises = [];
  if (lhsP && lhsP !== viewerState.lhsPage) promises.push(renderPdfPage('lhs', lhsP));
  if (rhsP && rhsP !== viewerState.rhsPage) promises.push(renderPdfPage('rhs', rhsP));
  await Promise.all(promises);
  if (lhsP === viewerState.lhsPage && viewerState.lhsPdf) await renderPdfPage('lhs', viewerState.lhsPage);
  if (rhsP === viewerState.rhsPage && viewerState.rhsPdf) await renderPdfPage('rhs', viewerState.rhsPage);
  renderViewerSidebar(document.getElementById('vm-filter').value);
  for (const side of ['lhs', 'rhs']) {
    const body = document.getElementById('vm-' + side + '-body');
    const hi = body.querySelector('.bbox-hi.is-active');
    if (hi) hi.scrollIntoView({block: 'center', behavior: 'smooth'});
  }
}

function closeInlineViewer() {
  document.getElementById('viewer-modal').hidden = true;
  document.body.style.overflow = '';
  viewerState.lhsPdf = null; viewerState.rhsPdf = null;
  viewerState.events = []; viewerState.activeEventId = null;
}

function showEventPopover(evId, anchorEl) {
  const e = viewerState.events.find(x => x.event_id === evId);
  if (!e) return;
  const pop = document.getElementById('ev-popover');
  const rect = anchorEl.getBoundingClientRect();
  pop.style.left = Math.min(window.innerWidth - 400, rect.right + 8) + 'px';
  pop.style.top = Math.min(window.innerHeight - 260, rect.top) + 'px';
  const lr = e.last_review;
  pop.innerHTML = `
    <div class="pop-head">
      <span>Event · <span class="chip chip-${escapeHtml((e.status||'').toLowerCase())}">${escapeHtml(e.status||'?')}</span></span>
      <button class="pop-close" aria-label="close">✕</button>
    </div>
    <div class="pop-body">
      ${e.lhs?.quote ? `<div class="quote lhs">${escapeHtml(e.lhs.quote.slice(0,300))}${e.lhs.quote.length>300?'…':''}</div>` : ''}
      ${e.rhs?.quote ? `<div class="quote rhs">${escapeHtml(e.rhs.quote.slice(0,300))}${e.rhs.quote.length>300?'…':''}</div>` : ''}
      ${e.explanation_short ? `<div style="font-style:italic;color:var(--mute);margin:6px 0">${escapeHtml(e.explanation_short)}</div>` : ''}
      <textarea placeholder="Comment (optional)"></textarea>
      <div class="pop-actions">
        <button class="accept">✓ Accept</button>
        <button class="ai-suggest" style="flex:0;background:rgba(255,214,10,0.18);border-color:#7a5c1a;color:var(--amber);padding:6px 10px">✨ AI</button>
        <button class="reject">✗ Reject</button>
      </div>
      <div class="ai-suggest-result" style="margin-top:8px;font-size:11.5px;color:var(--mute);display:none"></div>
      ${lr ? `<div class="pop-prev">Last: <span class="chip chip-${escapeHtml((lr.decision||'').replace(/_/g,'-'))}">${escapeHtml(lr.decision||'')}</span> by ${escapeHtml(lr.reviewer_name||'?')} · ${escapeHtml(lr.decided_at||'')}</div>` : ''}
    </div>
  `;
  pop.hidden = false;
  pop.querySelector('.pop-close').addEventListener('click', () => { pop.hidden = true; });
  const submit = async (decision) => {
    const name = localStorage.getItem('docdiff:reviewer') || prompt('Your name (saved for next time):', '') || 'anonymous';
    localStorage.setItem('docdiff:reviewer', name);
    const comment = pop.querySelector('textarea').value;
    const btns = pop.querySelectorAll('button');
    btns.forEach(b => b.disabled = true);
    try {
      const r = await fetch(BASE + '/events/' + evId + '/review', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({decision, reviewer_name: name, comment})
      }).then(r => r.json());
      const latest = (r.history || [])[0] || {decision, reviewer_name: name, decided_at: new Date().toISOString(), comment};
      e.last_review = latest;
      const evCacheItem = (eventsCache || []).find(x => x.event_id === evId);
      if (evCacheItem) evCacheItem.last_review = latest;
      toast(`Review saved: ${decision}`, 'success');
      pop.hidden = true;
      renderViewerSidebar(document.getElementById('vm-filter').value);
    } catch (err) {
      toast('Review failed: ' + err.message, 'error');
      btns.forEach(b => b.disabled = false);
    }
  };
  pop.querySelector('button.accept').addEventListener('click', () => submit('confirmed'));
  pop.querySelector('button.reject').addEventListener('click', () => submit('rejected'));
  const aiBtn = pop.querySelector('button.ai-suggest');
  const aiResult = pop.querySelector('.ai-suggest-result');
  if (aiBtn) aiBtn.addEventListener('click', async () => {
    aiBtn.disabled = true; const orig = aiBtn.textContent; aiBtn.textContent = '⏳';
    try {
      const r = await fetch(BASE + '/events/' + evId + '/ai-suggest', {method: 'POST'}).then(r => r.json());
      const s = r.suggestion || {};
      aiResult.style.display = 'block';
      const conf = Math.round((s.confidence || 0) * 100);
      const cls = s.decision === 'confirmed' ? 'chip-confirmed' : 'chip-rejected';
      aiResult.innerHTML = `<strong>AI:</strong> <span class="chip ${cls}">${escapeHtml(s.decision || '?')}</span> <span style="color:var(--mute)">(${conf}%)</span><div style="margin-top:4px">${escapeHtml(s.reasoning || '')}</div>`;
    } catch (e) {
      aiResult.style.display = 'block';
      aiResult.textContent = 'AI ошибка: ' + e.message;
    } finally {
      aiBtn.disabled = false; aiBtn.textContent = orig;
    }
  });
}

document.getElementById('vm-close').addEventListener('click', closeInlineViewer);

function _setupSyncScroll() {
  const lhs = document.getElementById('vm-lhs-body');
  const rhs = document.getElementById('vm-rhs-body');
  if (!lhs || !rhs) return;
  let lock = false;
  const syncFrom = (src, dst) => () => {
    if (lock) return;
    lock = true;
    const pct = src.scrollTop / Math.max(1, src.scrollHeight - src.clientHeight);
    dst.scrollTop = pct * Math.max(1, dst.scrollHeight - dst.clientHeight);
    setTimeout(() => { lock = false; }, 20);
  };
  lhs.addEventListener('scroll', syncFrom(lhs, rhs));
  rhs.addEventListener('scroll', syncFrom(rhs, lhs));
}
// Wire on first viewer open (after panes exist):
const _origOpenInlineViewer = openInlineViewer;
window.openInlineViewer = async function(pairId) {
  await _origOpenInlineViewer(pairId);
  _setupSyncScroll();
};

document.addEventListener('keydown', e => {
  const modal = document.getElementById('viewer-modal');
  if (modal.hidden) return;
  // Don't intercept when typing in filter input or popover textarea
  const tag = (e.target && e.target.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (e.key === 'Escape') { closeInlineViewer(); return; }
  if (e.key === 'j' || e.key === 'J') { e.preventDefault(); _viewerJumpRelative(1); return; }
  if (e.key === 'k' || e.key === 'K') { e.preventDefault(); _viewerJumpRelative(-1); return; }
  if (e.key === 'a' || e.key === 'A') { e.preventDefault(); _viewerQuickDecide('confirmed'); return; }
  if (e.key === 'r' || e.key === 'R') { e.preventDefault(); _viewerQuickDecide('rejected'); return; }
  if (e.key === '+' || e.key === '=') { e.preventDefault(); _viewerSetZoom(viewerState.zoom * 1.2); return; }
  if (e.key === '-' || e.key === '_') { e.preventDefault(); _viewerSetZoom(viewerState.zoom / 1.2); return; }
  if (e.key === '0') { e.preventDefault(); _viewerFitToWidth(); return; }
});
document.addEventListener('keydown', e => {
  // Don't intercept ? when typing in inputs
  const tag = (e.target && e.target.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (e.key === '?') { e.preventDefault(); document.getElementById('help-modal').hidden = false; }
});

function _viewerJumpRelative(delta) {
  // Skip accepted/rejected when hide-decided is on, otherwise iterate all.
  const hide = document.getElementById('vm-hide-decided')?.checked ?? true;
  const visible = viewerState.events.filter(e => !(hide && e.last_review && (e.last_review.decision === 'confirmed' || e.last_review.decision === 'rejected')));
  if (!visible.length) return;
  // pending-first: events without last_review come before reviewed ones
  visible.sort((a, b) => {
    const ap = a.last_review ? 1 : 0;
    const bp = b.last_review ? 1 : 0;
    if (ap !== bp) return ap - bp;
    const pa = (a.lhs?.page_no || a.lhs_page || 0), pb = (b.lhs?.page_no || b.lhs_page || 0);
    if (pa !== pb) return pa - pb;
    return (a.event_id || '').localeCompare(b.event_id || '');
  });
  const curIdx = viewerState.activeEventId ? visible.findIndex(e => e.event_id === viewerState.activeEventId) : -1;
  const nextIdx = (curIdx < 0 ? 0 : (curIdx + delta + visible.length) % visible.length);
  const ne = visible[nextIdx];
  if (ne) jumpToEvent(ne.event_id);
}

async function _viewerQuickDecide(decision) {
  if (!viewerState.activeEventId) return;
  const evId = viewerState.activeEventId;
  const e = viewerState.events.find(x => x.event_id === evId);
  if (!e) return;
  const name = localStorage.getItem('docdiff:reviewer') || prompt('Your name (saved for next time):', '') || 'anonymous';
  localStorage.setItem('docdiff:reviewer', name);
  try {
    const r = await fetch(BASE + '/events/' + evId + '/review', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({decision, reviewer_name: name, comment: ''})
    }).then(r => r.json());
    const latest = (r.history || [])[0] || {decision, reviewer_name: name, decided_at: new Date().toISOString()};
    e.last_review = latest;
    const cached = (eventsCache || []).find(x => x.event_id === evId);
    if (cached) cached.last_review = latest;
    toast(`${decision === 'confirmed' ? '✓' : '✗'} ${decision}`, 'success');
    renderViewerSidebar(document.getElementById('vm-filter').value);
    // auto-advance to next pending
    _viewerJumpRelative(1);
  } catch (err) {
    toast('Review failed: ' + err.message, 'error');
  }
}
document.querySelectorAll('#vm-pager-lhs button, #vm-pager-rhs button').forEach(btn => {
  btn.addEventListener('click', () => {
    const side = btn.dataset.side;
    const dir = parseInt(btn.dataset.dir, 10);
    const cur = side === 'lhs' ? viewerState.lhsPage : viewerState.rhsPage;
    renderPdfPage(side, cur + dir);
  });
});
document.getElementById('vm-filter').addEventListener('input', e => renderViewerSidebar(e.target.value));
document.getElementById('vm-hide-decided').addEventListener('change', () => renderViewerSidebar(document.getElementById('vm-filter').value));
document.getElementById('vm-only-bookmarks').addEventListener('change', () => renderViewerSidebar(document.getElementById('vm-filter').value));
document.getElementById('vm-zoom-in').addEventListener('click', () => _viewerSetZoom(viewerState.zoom * 1.2));
document.getElementById('vm-zoom-out').addEventListener('click', () => _viewerSetZoom(viewerState.zoom / 1.2));
document.getElementById('vm-zoom-fit').addEventListener('click', () => _viewerFitToWidth());

// -------- topic clusters (cross-pair dedup) --------
async function loadTopics(batchId) {
  const list = document.getElementById('topics-list');
  list.innerHTML = "<div class='empty'><span class='spinner'></span></div>";
  try {
    const r = await fetch(BASE + '/batches/' + batchId + '/clusters').then(r => r.json());
    const clusters = r.clusters || [];
    if (!clusters.length) { list.innerHTML = "<div class='empty'>(нет тематических кластеров — запустите batch с LLM_PAIR_DIFF_ENABLED=true)</div>"; return; }
    list.innerHTML = '<div class="muted" style="font-size:12px;margin-bottom:12px">' +
      clusters.length + ' кластеров (один тезис который встречается в N парах = 1 кластер)</div>' +
      clusters.map(c => `
        <div class='pair-card' style='margin-bottom:10px'>
          <div class='head'>
            <div style='flex:1;min-width:0'>
              <div class='docs' style='word-break:break-word'>
                <span class='chip chip-${escapeHtml(c.status||'low')}'>${escapeHtml(c.status||'?')}</span>
                <span class='chip chip-${escapeHtml(c.severity||'low')}'>${escapeHtml(c.severity||'low')}</span>
                <span style='margin-left:6px'>${escapeHtml(c.topic||'(no topic)')}</span>
              </div>
              <div class='pair-id' style='margin-top:4px'>${escapeHtml(c.cluster_id||'')}</div>
            </div>
            <div class='muted mono' style='font-size:12px;text-align:right'>
              <div>${c.count} ev</div>
              <div>${(c.pair_ids||[]).length} pair${(c.pair_ids||[]).length===1?'':'s'}</div>
            </div>
          </div>
          ${(c.explanations||[]).length ? '<div style="margin-top:6px;font-size:13px;color:var(--mute);font-style:italic">' +
            (c.explanations||[]).map(x => '✎ '+escapeHtml(x)).join('<br>') + '</div>' : ''}
          <div style='margin-top:6px;display:flex;gap:6px;flex-wrap:wrap'>
            ${(c.pair_ids||[]).map(pid => `<button class='pill-link' data-pid='${escapeHtml(pid)}'>${escapeHtml(pid.slice(-12))}</button>`).join('')}
          </div>
        </div>
      `).join('');
    list.querySelectorAll('button[data-pid]').forEach(b => b.addEventListener('click', () => {
      document.getElementById('evt-pair').value = b.dataset.pid;
      document.querySelector('.tab-line[data-detail-tab="events"]').click();
      applyEventsFilter();
    }));
  } catch (e) {
    list.innerHTML = `<div class='empty'>Topics unavailable: ${escapeHtml(e.message)}</div>`;
  }
}

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
  if (!arts.length) { list.innerHTML = "<div class='empty' data-icon='📭'>(нет артефактов)</div>"; }
  else {
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
  renderV10Bundle(s);
}

// -------- v10 forensic bundle --------
function renderV10Bundle(s) {
  const block = document.getElementById('v10-bundle-block');
  if (!s.v10_bundle) { block.hidden = true; block.innerHTML = ''; return; }
  const V10_KINDS = [
    { kind: 'xlsx_v10',               label: '📊 14-листный XLSX (heatmap, correlations)' },
    { kind: 'note_docx',              label: '📄 Пояснительная записка (DOCX)' },
    { kind: 'note_pdf',               label: '📄 Пояснительная записка (PDF)' },
    { kind: 'integral_matrix_pdf',    label: '🗺️ Интегральная матрица (PDF, A3)' },
    { kind: 'correlation_matrix_csv', label: '📈 Correlation matrix (CSV)' },
    { kind: 'dependency_graph_csv',   label: '🔗 Dependency graph (CSV)' },
    { kind: 'claim_provenance_csv',   label: '🧾 Claim provenance (CSV)' },
    { kind: 'coverage_heatmap_csv',   label: '🌡️ Coverage heatmap (CSV)' },
  ];
  const links = V10_KINDS.map(({ kind, label }) =>
    `<li><a class='v10-pill' href='${BASE}/batches/${currentBatchId}/forensic/${escapeHtml(kind)}' target='_blank'>${escapeHtml(label)} ↓</a></li>`
  ).join('');
  block.innerHTML = `
    <div class='v10-bundle'>
      <h3>📦 v10 Forensic Bundle</h3>
      <ul class='v10-links'>${links}</ul>
      <a class='v10-pill v10-zip' href='${BASE}/batches/${currentBatchId}/forensic/v10.zip' target='_blank'>📦 Скачать всё одним архивом ↓</a>
    </div>
  `;
  block.hidden = false;
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
refreshBatches(); // warm up topbar stats
</script>
</body>
</html>
"""
