# UI Bundle 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the three deferred polish items as three atomic commits to `docdiffops_mvp/docdiffops/app_html.py`: skip-to-content link, light theme (auto + manual), responsive viewer modal.

**Architecture:** All work is inside the single-file SPA `APP_HTML` string blob (no build step). C1 is purely additive markup + CSS. C2 introduces a `:root[data-theme]` cascade and a pre-paint inline script in `<head>` to avoid FOUC. C3 absolutely positions `.vm-sidebar` inside `.vm-body` below 1024px, adds a drawer toggle button to `.vm-head`, and stacks panes below 600px by making `.vm-body` `flex-direction: column` + hiding the minimap.

**Tech Stack:** Vanilla JS, inline CSS, `pdf.js` (already bundled). No new deps.

**Spec:** `docs/superpowers/specs/2026-05-13-ui-bundle3-design.md` (commit `52f747f`).

**Verification model:** Two-layer manual smoke (already in use from Bundle 1+2):
1. Python static audit (look for new markup/CSS markers) — script written in Task 4, reused with extensions in Tasks 8 and 12.
2. Playwright + chromium runtime smoke — same throwaway stdlib server pattern used in the last verification. Skipped if env doesn't allow.

---

## File Map

| File | C1 (skip-link) | C2 (theme) | C3 (responsive viewer) |
|---|---|---|---|
| `docdiffops_mvp/docdiffops/app_html.py` | skip-link `<a>`, `id`+`tabindex` on `<main>`, `.skip-link` CSS | pre-paint `<script>` in `<head>`, split `:root` palette into 2 selectors, add `[data-theme="light"]` block + media-query block, `#settings-theme` select + handler | `position: relative` on `.vm-body`, two @media blocks (1024 + 600), `#vm-drawer-toggle` markup + CSS + JS, viewer Escape integration, drawer state reset on close |

No other files change.

---

# Commit C1 — Skip-to-content link

## Task 1: Insert skip-link markup

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — line 503 (`<body>` opener) and line 521 (`<main class="app">` opener).

- [ ] **Step 1: Add the skip-link as the first child of `<body>`**

Line 503 currently:

```html
<body>
```

Replace with:

```html
<body>
<a class="skip-link" href="#main-content">Перейти к содержимому</a>
```

- [ ] **Step 2: Add `id` and `tabindex` to `<main>`**

Line 521 currently:

```html
<main class="app">
```

Replace with:

```html
<main class="app" id="main-content" tabindex="-1">
```

`tabindex="-1"` is mandatory: without it, `<main>` cannot receive focus via URL fragment activation in any browser.

- [ ] **Step 3: Do NOT commit yet. Move to Task 2.**

---

## Task 2: Add `.skip-link` CSS

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — insert immediately after the `:root` block (currently ends at line 32).

- [ ] **Step 1: Insert the rule**

Find the closing `}` of the `:root` block. Immediately after it (and before the `@media (prefers-reduced-motion: reduce)` block added in Bundle 2), insert:

```css
.skip-link {
  position: absolute;
  left: -9999px;
  top: 0;
  z-index: 1000;
  background: var(--blue);
  color: #04111a;
  padding: 8px 14px;
  border-radius: 0 0 6px 0;
  font-weight: 600;
  text-decoration: none;
}
.skip-link:focus,
.skip-link:focus-visible {
  left: 0;
  outline: none;
}
```

The `:focus` selector covers the (rare) case of browsers without `:focus-visible` support. `text-decoration: none` overrides the global `a` style.

- [ ] **Step 2: Do NOT commit yet. Move to Task 3.**

---

## Task 3: Verify C1 manually + commit

**Files:**
- Commit: `docdiffops_mvp/docdiffops/app_html.py`

- [ ] **Step 1: Run the static audit (write inline if not already done)**

```bash
cd /home/dev/diff && python3 -c "
import re
with open('docdiffops_mvp/docdiffops/app_html.py') as f: src = f.read()
html = re.search(r'APP_HTML = r\"\"\"(.*?)\"\"\"', src, re.DOTALL).group(1)
assert 'class=\"skip-link\" href=\"#main-content\"' in html, 'skip-link markup missing'
assert 'id=\"main-content\" tabindex=\"-1\"' in html, 'main id/tabindex missing'
assert '.skip-link {' in html, '.skip-link CSS missing'
assert '.skip-link:focus' in html, '.skip-link:focus CSS missing'
print('C1 static audit OK')
"
```

Expected output: `C1 static audit OK`.

- [ ] **Step 2: Commit C1**

```bash
cd /home/dev/diff
git add docdiffops_mvp/docdiffops/app_html.py
git commit -m "$(cat <<'EOF'
feat(ui): skip-to-content link (Bundle 3 / C1)

Adds a "Перейти к содержимому" link as the first focusable element on
every page. Keyboard users can jump past the topbar in one Tab + Enter.

Visually hidden via off-screen positioning, becomes a brand-blue chip
at top-left on focus. <main> gets id="main-content" + tabindex="-1" so
it can receive programmatic focus.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Commit C2 — Light theme (auto + manual)

## Task 4: Add pre-paint script in `<head>`

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — insert in `<head>` BEFORE the pdf.js loader at line 15.

- [ ] **Step 1: Find the existing head block**

Lines 11-22 currently:

```html
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
```

- [ ] **Step 2: Insert the pre-paint theme script**

Replace the `<title>DocDiffOps</title>` line with:

```html
<title>DocDiffOps</title>
<script>
// Pre-paint theme: read user's saved preference and apply data-theme
// BEFORE the inline <style> + body render, to avoid FOUC.
(function(){
  try {
    var pref = localStorage.getItem('docdiff:theme');
    if (pref === 'light' || pref === 'dark') document.documentElement.dataset.theme = pref;
  } catch (_) {}
})();
</script>
```

The `try/catch` protects against localStorage being disabled (private mode). Storage exceptions otherwise throw and break the whole script.

- [ ] **Step 3: Do NOT commit yet. Move to Task 5.**

---

## Task 5: Split `:root` palette + add light palette

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — the `:root { ... }` block at lines 24-32.

- [ ] **Step 1: Widen the dark selector**

Lines 24-32 currently:

```css
:root {
  --bg: #0b0d12; --panel: #11141b; --panel-2: #161a22; --line: #1f2632;
  --fg: #e9eef5; --mute: #8b97aa; --strong: #ffffff;
  --blue: #4cc3ff; --blue-dim: #1d4d6b;
  --green: #2ec27e; --red: #e5484d; --amber: #ffb224; --gray: #5b6473;
  --hi: rgba(255,214,10,0.85);
  --rad: 6px; --rad-lg: 10px;
  --shadow: 0 6px 28px rgba(0,0,0,0.45);
}
```

Replace the opening line `:root {` with `:root, :root[data-theme="dark"] {` so the dark palette applies both to the no-preference default AND to users who explicitly chose dark:

```css
:root, :root[data-theme="dark"] {
  --bg: #0b0d12; --panel: #11141b; --panel-2: #161a22; --line: #1f2632;
  --fg: #e9eef5; --mute: #8b97aa; --strong: #ffffff;
  --blue: #4cc3ff; --blue-dim: #1d4d6b;
  --green: #2ec27e; --red: #e5484d; --amber: #ffb224; --gray: #5b6473;
  --hi: rgba(255,214,10,0.85);
  --rad: 6px; --rad-lg: 10px;
  --shadow: 0 6px 28px rgba(0,0,0,0.45);
}
```

- [ ] **Step 2: Add the light palette (manual override)**

Immediately after the closing `}` of that block, insert:

```css
:root[data-theme="light"] {
  --bg: #fafbfc; --panel: #ffffff; --panel-2: #f4f5f7; --line: #e1e4e8;
  --fg: #24292e; --mute: #6a737d; --strong: #000000;
  --blue: #0366d6; --blue-dim: #c8e1ff;
  --green: #1a7f37; --red: #cf222e; --amber: #9a6700; --gray: #57606a;
  --hi: rgba(255,214,10,0.85);
  --rad: 6px; --rad-lg: 10px;
  --shadow: 0 6px 28px rgba(0,0,0,0.10);
}
```

- [ ] **Step 3: Add the auto-light variant (media query)**

Immediately after the manual `[data-theme="light"]` block, insert:

```css
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]):not([data-theme="light"]) {
    --bg: #fafbfc; --panel: #ffffff; --panel-2: #f4f5f7; --line: #e1e4e8;
    --fg: #24292e; --mute: #6a737d; --strong: #000000;
    --blue: #0366d6; --blue-dim: #c8e1ff;
    --green: #1a7f37; --red: #cf222e; --amber: #9a6700; --gray: #57606a;
    --hi: rgba(255,214,10,0.85);
    --rad: 6px; --rad-lg: 10px;
    --shadow: 0 6px 28px rgba(0,0,0,0.10);
  }
}
```

The `:not([data-theme="dark"]):not([data-theme="light"])` chain ensures: if user explicitly picked light or dark in Settings, that choice wins. If they picked auto (default), the OS preference applies.

The ~13 lines of duplication between Step 2 and Step 3 is accepted (per spec C2.3); CSS custom-property indirection would obscure the actual hex values.

- [ ] **Step 4: Do NOT commit yet. Move to Task 6.**

---

## Task 6: Add theme select to Settings modal

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — the Settings modal markup (currently around lines 692-705).

- [ ] **Step 1: Insert the theme row before the clear-data row**

Find the existing settings rows around line 686-696:

```html
    <div class="settings-row">
      <label>Сортировка пар по умолчанию</label>
      <select id="settings-default-sort">
        <option value="updated">по обновлению</option>
        <option value="score-desc">по score (высокий)</option>
        <option value="events-desc">по количеству событий</option>
        <option value="high-desc">по high-risk</option>
      </select>
    </div>
    <div class="settings-row">
      <label>Очистить локальные данные</label>
```

Insert a new `.settings-row` between the existing sort row and the clear-data row. The new block goes right after the `</div>` that closes the sort row, before the next `<div class="settings-row">`:

```html
    <div class="settings-row">
      <label>Сортировка пар по умолчанию</label>
      <select id="settings-default-sort">
        <option value="updated">по обновлению</option>
        <option value="score-desc">по score (высокий)</option>
        <option value="events-desc">по количеству событий</option>
        <option value="high-desc">по high-risk</option>
      </select>
    </div>
    <div class="settings-row">
      <label>Тема оформления</label>
      <select id="settings-theme">
        <option value="auto">Авто (по системе)</option>
        <option value="light">Светлая</option>
        <option value="dark">Тёмная</option>
      </select>
    </div>
    <div class="settings-row">
      <label>Очистить локальные данные</label>
```

- [ ] **Step 2: Do NOT commit yet. Move to Task 7.**

---

## Task 7: Wire theme save/load into `_initSettingsModal`

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — `_initSettingsModal` function at line 2729 onwards, specifically the `saveBtn.addEventListener` block at line 2749 and the `updateFields` helper near the top of the function.

- [ ] **Step 1: Read the current `_initSettingsModal` function**

Lines around 2729-2770 currently look like:

```js
function _initSettingsModal() {
  const modal = document.getElementById('settings-modal');
  const inp = document.getElementById('settings-reviewer');
  const sel = document.getElementById('settings-default-sort');
  const clearBtn = document.getElementById('settings-clear');
  const saveBtn = document.getElementById('settings-save');

  function updateFields() {
    inp.value = localStorage.getItem('docdiff:reviewer') || '';
    sel.value = localStorage.getItem(SETTINGS_DEFAULT_SORT_KEY) || 'updated';
  }
  updateFields();

  // ... MutationObserver wiring ...

  saveBtn.addEventListener('click', () => {
    const name = (inp.value || '').trim();
    if (name) localStorage.setItem('docdiff:reviewer', name);
    localStorage.setItem(SETTINGS_DEFAULT_SORT_KEY, sel.value);
    toast('Настройки сохранены', 'success');
    _closeModal(modal);
    // Re-render pairs with new sort if currently on detail view
    const sortSel = document.getElementById('pairs-sort');
    if (sortSel) {
      sortSel.value = sel.value;
      if (typeof _renderPairsFiltered === 'function') _renderPairsFiltered();
    }
  });
  // ...
}
```

- [ ] **Step 2: Add `themeSel` reference and populate it in `updateFields`**

Right after the line `const saveBtn = document.getElementById('settings-save');`, insert:

```js
  const themeSel = document.getElementById('settings-theme');
```

In the `updateFields()` function body, add a line that reads the saved theme. The function should look like:

```js
  function updateFields() {
    inp.value = localStorage.getItem('docdiff:reviewer') || '';
    sel.value = localStorage.getItem(SETTINGS_DEFAULT_SORT_KEY) || 'updated';
    themeSel.value = localStorage.getItem('docdiff:theme') || 'auto';
  }
```

- [ ] **Step 3: Persist the theme on save**

In the `saveBtn.addEventListener('click', ...)` body, immediately after the line `localStorage.setItem(SETTINGS_DEFAULT_SORT_KEY, sel.value);`, add the theme write:

```js
    const themeVal = themeSel.value;
    if (themeVal === 'auto') {
      localStorage.removeItem('docdiff:theme');
      delete document.documentElement.dataset.theme;
    } else {
      localStorage.setItem('docdiff:theme', themeVal);
      document.documentElement.dataset.theme = themeVal;
    }
```

Place these lines BEFORE the `toast('Настройки сохранены', 'success');` so the theme is applied before the success toast renders (avoids the toast briefly using the old theme's colors).

- [ ] **Step 4: Clear-data also clears the theme**

In the `clearBtn.addEventListener` block (the one that removes all `docdiff:*` keys), the existing loop `keys.forEach(k => localStorage.removeItem(k));` already removes `docdiff:theme`. After that loop, also reset the `data-theme` attribute and call `updateFields()`:

Find the existing block:

```js
  clearBtn.addEventListener('click', () => {
    if (!confirm('Очистить все локальные настройки и bookmarks?')) return;
    const keys = Object.keys(localStorage).filter(k => k.startsWith('docdiff:'));
    keys.forEach(k => localStorage.removeItem(k));
    toast(`Очищено ${keys.length} ключей`, 'success');
    updateFields();
  });
```

Modify to also strip the dataset attribute:

```js
  clearBtn.addEventListener('click', () => {
    if (!confirm('Очистить все локальные настройки и bookmarks?')) return;
    const keys = Object.keys(localStorage).filter(k => k.startsWith('docdiff:'));
    keys.forEach(k => localStorage.removeItem(k));
    delete document.documentElement.dataset.theme;
    toast(`Очищено ${keys.length} ключей`, 'success');
    updateFields();
  });
```

- [ ] **Step 5: Do NOT commit yet. Move to Task 8.**

---

## Task 8: Verify C2 manually + commit

**Files:**
- Commit: `docdiffops_mvp/docdiffops/app_html.py`

- [ ] **Step 1: Run the static audit**

```bash
cd /home/dev/diff && python3 -c "
import re
with open('docdiffops_mvp/docdiffops/app_html.py') as f: src = f.read()
html = re.search(r'APP_HTML = r\"\"\"(.*?)\"\"\"', src, re.DOTALL).group(1)
checks = [
  ('pre-paint script', \"localStorage.getItem('docdiff:theme')\" in html and 'document.documentElement.dataset.theme = pref' in html),
  ('dark selector widened', ':root, :root[data-theme=\"dark\"] {' in html),
  ('light data-theme block', ':root[data-theme=\"light\"] {' in html),
  ('prefers-color-scheme: light', '@media (prefers-color-scheme: light)' in html),
  ('media-query :not() chain', ':root:not([data-theme=\"dark\"]):not([data-theme=\"light\"])' in html),
  ('settings-theme select', 'id=\"settings-theme\"' in html),
  ('theme option auto/light/dark', 'option value=\"auto\"' in html and 'option value=\"light\"' in html and 'option value=\"dark\"' in html),
  ('save handler writes theme', \"localStorage.setItem('docdiff:theme'\" in html and 'document.documentElement.dataset.theme = themeVal' in html),
  ('clear-data resets data-theme', 'delete document.documentElement.dataset.theme' in html),
]
for name, ok in checks: print(('✓' if ok else '✗') + '  ' + name)
assert all(c[1] for c in checks), 'C2 static audit FAILED'
print('C2 static audit OK')
"
```

Expected output: 9 `✓` lines + `C2 static audit OK`.

- [ ] **Step 2: Commit C2**

```bash
cd /home/dev/diff
git add docdiffops_mvp/docdiffops/app_html.py
git commit -m "$(cat <<'EOF'
feat(ui): light theme + auto/manual toggle (Bundle 3 / C2)

Three-state preference (auto / light / dark) persisted in localStorage
as docdiff:theme. Applied via <html data-theme="…">.

Cascade:
- :root, :root[data-theme="dark"] keeps the existing dark palette as
  default for users with no preference and no system light hint.
- :root[data-theme="light"] applies the GitHub-style soft-white palette.
- @media (prefers-color-scheme: light) :root:not([data-theme])
  auto-applies light when the OS asks for it AND user hasn't overridden.

A pre-paint inline <script> in <head> reads the saved preference and
sets data-theme before the inline <style> renders — avoids FOUC.

New Settings row "Тема оформления" with auto/light/dark options.
Clear-data button now also clears the data-theme attribute.

Light palette is GitHub-derived:
  bg #fafbfc, panel #ffffff, line #e1e4e8, fg #24292e, mute #6a737d,
  blue #0366d6, green #1a7f37, red #cf222e, amber #9a6700.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Commit C3 — Responsive viewer

## Task 9: Make `.vm-body` a positioning context + add drawer CSS

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — viewer-modal CSS section (after the existing `.vm-sidebar` rules around line 350-360 — locate by grepping).

- [ ] **Step 1: Locate `.vm-body` CSS**

Run:

```bash
grep -n "\.viewer-modal \.vm-body" /home/dev/diff/docdiffops_mvp/docdiffops/app_html.py | head -5
```

This gives the exact line number of the `.vm-body` rule. (Expected: a single rule like `.viewer-modal .vm-body { display: flex; flex: 1; min-height: 0; }` around line 330.)

- [ ] **Step 2: Add `position: relative` to `.vm-body`**

Append `position: relative;` to the existing `.vm-body` rule body. So if the current rule is:

```css
.viewer-modal .vm-body { display: flex; flex: 1; min-height: 0; }
```

It becomes:

```css
.viewer-modal .vm-body { display: flex; flex: 1; min-height: 0; position: relative; }
```

This makes the body a positioning ancestor so the drawer can absolutely position to it.

- [ ] **Step 3: Append the responsive media queries**

Find the end of the viewer-modal CSS section (the last rule that starts with `.viewer-modal`). Just before the next unrelated CSS section (e.g., `mark {` or `[hidden]`), insert:

```css
/* ------------------- responsive viewer (Bundle 3 / C3) ------------------- */
@media (max-width: 1024px) {
  .viewer-modal .vm-sidebar {
    position: absolute;
    top: 0; right: 0; bottom: 0;
    width: min(360px, 85vw);
    transform: translateX(100%);
    transition: transform 0.2s ease;
    z-index: 10;
    box-shadow: -4px 0 20px rgba(0,0,0,0.3);
  }
  .viewer-modal .vm-sidebar.open { transform: translateX(0); }
  .vm-drawer-toggle { display: inline-block !important; }
}
@media (min-width: 1025px) {
  .vm-drawer-toggle { display: none; }
}
@media (max-width: 600px) {
  .viewer-modal .vm-body { flex-direction: column; }
  .viewer-modal .vm-pane { width: 100% !important; height: 50%; }
  .viewer-modal .vm-minimap { display: none; }
}
.vm-drawer-toggle {
  background: var(--panel-2); border: 1px solid var(--line);
  color: var(--fg); padding: 5px 10px; border-radius: 5px;
  font-size: 14px; cursor: pointer;
  display: none;
}
```

Notes:
- The `display: inline-block !important` is required because the global `[hidden] { display: none !important }` rule from Bundle 1 would otherwise win when the button has the `hidden` attribute. The `!important` is documented inline.
- The base `.vm-drawer-toggle` rule (last block) keeps the button hidden on desktop via `display: none`.
- The `.vm-pane { width: 100% !important }` overrides any existing width: 50% on panes.

- [ ] **Step 4: Do NOT commit yet. Move to Task 10.**

---

## Task 10: Add drawer toggle button to `.vm-head`

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — `.vm-head` markup around line 711, immediately before `.vm-zoom` at line 725.

- [ ] **Step 1: Find the structure around `.vm-zoom`**

Locate the `<div class="vm-zoom">` opening tag (currently line 725). Above it is some part of the `.vm-head` content (pager, search, etc.).

- [ ] **Step 2: Insert the toggle button before `.vm-zoom`**

Find the line `<div class="vm-zoom">` and insert immediately before it:

```html
    <button id="vm-drawer-toggle" class="vm-drawer-toggle" aria-label="События" aria-expanded="false" title="События (drawer)">📑</button>
```

The button has no `hidden` attribute — its visibility is controlled by CSS media queries from Task 9.

- [ ] **Step 3: Do NOT commit yet. Move to Task 11.**

---

## Task 11: Wire drawer toggle + Escape integration + close reset

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — `closeInlineViewer` function (around line 2280), viewer-modal Escape handler in the `keydown` listener (around line 2389), and the init block where viewer events are wired (around line 2370, near `document.getElementById('vm-close').addEventListener('click', closeInlineViewer);`).

- [ ] **Step 1: Add the toggle click handler**

Locate the line `document.getElementById('vm-close').addEventListener('click', closeInlineViewer);` (around line 2370). Insert immediately after it:

```js
document.getElementById('vm-drawer-toggle').addEventListener('click', () => {
  const sidebar = document.querySelector('.viewer-modal .vm-sidebar');
  const btn = document.getElementById('vm-drawer-toggle');
  const open = sidebar.classList.toggle('open');
  btn.setAttribute('aria-expanded', String(open));
});
```

- [ ] **Step 2: Integrate Escape with the drawer**

In the existing viewer-modal keydown handler (around line 2389), find the line:

```js
  if (e.key === 'Escape') { closeInlineViewer(); return; }
```

Replace it with:

```js
  if (e.key === 'Escape') {
    const sidebar = document.querySelector('.viewer-modal .vm-sidebar');
    if (sidebar?.classList.contains('open')) {
      sidebar.classList.remove('open');
      const btn = document.getElementById('vm-drawer-toggle');
      btn?.setAttribute('aria-expanded', 'false');
      return;
    }
    closeInlineViewer();
    return;
  }
```

This way the first Escape closes the drawer if it's open, the second Escape closes the viewer.

- [ ] **Step 3: Reset drawer state on viewer close**

Find `closeInlineViewer` (around line 2280):

```js
function closeInlineViewer() {
  _closeModal(document.getElementById('viewer-modal'));
  document.body.style.overflow = '';
  viewerState.lhsPdf = null; viewerState.rhsPdf = null;
  viewerState.events = []; viewerState.activeEventId = null;
}
```

Replace with:

```js
function closeInlineViewer() {
  // Reset drawer state so the viewer always opens with sidebar closed
  // on mobile/tablet (matches desktop default — sidebar visible inline).
  const sb = document.querySelector('.viewer-modal .vm-sidebar');
  sb?.classList.remove('open');
  document.getElementById('vm-drawer-toggle')?.setAttribute('aria-expanded', 'false');
  _closeModal(document.getElementById('viewer-modal'));
  document.body.style.overflow = '';
  viewerState.lhsPdf = null; viewerState.rhsPdf = null;
  viewerState.events = []; viewerState.activeEventId = null;
}
```

Note: on desktop (≥1025px), the `.open` class is irrelevant because the sidebar isn't a drawer — but `classList.remove('open')` is a no-op when the class isn't present, so this is safe to run unconditionally.

- [ ] **Step 4: Do NOT commit yet. Move to Task 12.**

---

## Task 12: Verify C3 manually + commit

**Files:**
- Commit: `docdiffops_mvp/docdiffops/app_html.py`

- [ ] **Step 1: Run the static audit**

```bash
cd /home/dev/diff && python3 -c "
import re
with open('docdiffops_mvp/docdiffops/app_html.py') as f: src = f.read()
html = re.search(r'APP_HTML = r\"\"\"(.*?)\"\"\"', src, re.DOTALL).group(1)
checks = [
  ('vm-body position relative', 'position: relative' in html and '.viewer-modal .vm-body' in html),
  ('@media max-width 1024px', '@media (max-width: 1024px)' in html),
  ('@media max-width 600px', '@media (max-width: 600px)' in html),
  ('@media min-width 1025px', '@media (min-width: 1025px)' in html),
  ('sidebar transform translateX 100%', 'transform: translateX(100%);' in html),
  ('sidebar .open class rule', '.vm-sidebar.open { transform: translateX(0); }' in html),
  ('vm-drawer-toggle button', 'id=\"vm-drawer-toggle\"' in html),
  ('drawer toggle click handler', \"document.getElementById('vm-drawer-toggle').addEventListener('click'\" in html),
  ('Escape closes drawer first', \"sidebar?.classList.contains('open')\" in html),
  ('close resets drawer state', \"sb?.classList.remove('open')\" in html),
  ('aria-expanded on toggle', 'aria-expanded' in html),
  ('600px stacks panes', '.viewer-modal .vm-body { flex-direction: column;' in html),
  ('600px hides minimap', '.viewer-modal .vm-minimap { display: none;' in html),
]
for name, ok in checks: print(('✓' if ok else '✗') + '  ' + name)
assert all(c[1] for c in checks), 'C3 static audit FAILED'
print('C3 static audit OK')
"
```

Expected output: 13 `✓` lines + `C3 static audit OK`.

- [ ] **Step 2: Commit C3**

```bash
cd /home/dev/diff
git add docdiffops_mvp/docdiffops/app_html.py
git commit -m "$(cat <<'EOF'
feat(ui): responsive viewer — drawer below 1024px, stack below 600px (Bundle 3 / C3)

Two breakpoints, no JS-driven layout switches:

- ≥1025px: today's 3-column layout (LHS | RHS | sidebar).
- 600–1024px: sidebar becomes a slide-in drawer. New 📑 toggle button
  in vm-head opens/closes it. LHS|RHS uses freed width.
- <600px: LHS stacks above RHS (50% height each). Minimap hidden.

Implementation notes:
- .vm-body gets position: relative so the sidebar (position: absolute,
  transform: translateX(100%)) docks to it correctly.
- The drawer toggle uses !important on display: inline-block to beat
  the global [hidden]{display:none!important} guard from Bundle 1.
- Escape now closes the drawer first (if open), only then the viewer.
- closeInlineViewer() resets drawer state so reopening always starts
  with sidebar closed on narrow screens.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** Each spec section maps to tasks:
  - C1 → Tasks 1, 2, 3
  - C2.1–C2.7 → Tasks 4, 5, 6, 7, 8
  - C3.1–C3.7 → Tasks 9, 10, 11, 12
  - C3.8 risks documented in commit body of C3 but no specific tasks (they're verification concerns)
- **Type consistency:** `themeSel` / `themeVal` consistent across Task 7. `sidebar` and `sb` are local var names in Task 11 (acceptable; each is scoped to its handler). `#vm-drawer-toggle` ID consistent across Tasks 9, 10, 11, 12.
- **Placeholder scan:** No TBD/TODO. Every step has runnable code.
- **No automated tests for the SPA** — matches Bundle 1+2 precedent. Static audit (Python) is mandatory before each commit; runtime smoke (playwright + chromium) is a nice-to-have if env allows. The playwright smoke script from the previous verification can be extended to cover the new modal/theme/drawer surface — out of scope for this plan but easy follow-up.
