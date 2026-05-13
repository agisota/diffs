# UI Polish — Bundle 3 Design Spec

**Date:** 2026-05-13
**Branch:** `main`
**Scope:** `docdiffops_mvp/docdiffops/app_html.py` only
**Output:** three atomic commits (C1 skip-link, C2 light theme, C3 responsive viewer)

## Context

Bundle 1 + 2 (commits `d267e69`, `bf8c888`) shipped the a11y core: keydown
guards, button semantics, aria-labels, dialog roles, focus trap, focus
restoration, `prefers-reduced-motion`, `:focus-visible`, and `aria-live`
toasts. The spec at `docs/superpowers/specs/2026-05-13-ui-a11y-design.md`
deferred three follow-on items to this bundle:

1. **Skip-to-content link** — keyboard-user shortcut past the topbar.
2. **Light theme** — `prefers-color-scheme: light` + manual toggle in
   Settings.
3. **Responsive viewer** — viewer-modal usable on tablets/phones.

This spec covers all three as three atomic commits in dependency-free
order. Each commit is independently revertable.

## Non-goals

- Filter input debouncing on `#pairs-filter` / `#evt-q` — separate
  performance pass.
- Events-table virtualization for >500 row batches — separate
  performance pass.
- Automated test coverage for `app_html.py` — still no infrastructure
  for this. Verification stays manual + playwright smoke.
- `prefers-contrast` media query — Bundle 4 candidate.
- Light-theme refinement after user testing — defer until user
  feedback exists.
- Mobile-specific gestures (swipe-to-close drawer, pinch-zoom on PDFs)
  — out of scope; tap interactions only.

## C1 — Skip-link (~20 LOC)

One commit. Risk: near-zero (purely additive).

### C1.1 — Markup

Insert at the start of `<body>`, before the topbar `<header>`:

```html
<a class="skip-link" href="#main-content">Перейти к содержимому</a>
```

Add `id="main-content" tabindex="-1"` to the existing `<main class="app">`
element. `tabindex="-1"` lets the URL-fragment activation move focus to
the `<main>` region without making it part of the normal Tab sequence.

### C1.2 — CSS

Insert immediately after the `:root` block:

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

The `:focus` selector covers browsers that don't implement
`:focus-visible` (rare today). `text-decoration: none` overrides the
global `a:hover { text-decoration: underline }`.

### C1.3 — Verification

- Reload page. Press Tab once from the address bar. Skip-link appears
  top-left with brand-blue background.
- Press Enter. Browser jumps to `#main-content`; `<main>` receives focus
  (verifiable via `document.activeElement.tagName === 'MAIN'`).

## C2 — Light theme (~100 LOC)

One commit. Risk: low–medium (palette correctness + cascade ordering).

### C2.1 — Three-state preference

User-visible preference is `auto` (default) | `light` | `dark`. Persisted
in `localStorage` as `docdiff:theme`. Applied via
`document.documentElement.dataset.theme` (i.e., `<html data-theme="…">`).

`auto` means: no `data-theme` attribute → CSS falls back to
`prefers-color-scheme`. `light`/`dark` explicitly override.

### C2.2 — Cascade

Three CSS blocks, in this order:

1. **Default (dark)** — move the existing `:root` palette unchanged.
   Selector: `:root, :root[data-theme="dark"]`. This preserves current
   behaviour for any user without a `data-theme` attribute AND no system
   light preference.
2. **Manual light** — `:root[data-theme="light"]` overrides with the
   light palette below.
3. **Auto light** —
   `@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]):not([data-theme="light"]) { … } }`.
   The `:not()` selectors ensure that an explicit user choice in
   Settings beats the OS preference (which beats the dark default).

### C2.3 — Light palette (GitHub-style soft white)

```css
:root[data-theme="light"] {
  --bg: #fafbfc; --panel: #ffffff; --panel-2: #f4f5f7; --line: #e1e4e8;
  --fg: #24292e; --mute: #6a737d; --strong: #000000;
  --blue: #0366d6; --blue-dim: #c8e1ff;
  --green: #1a7f37; --red: #cf222e; --amber: #9a6700; --gray: #57606a;
  --hi: rgba(255,214,10,0.85);
  --shadow: 0 6px 28px rgba(0,0,0,0.10);
}
```

The auto-light variant uses the same body. Since you can't combine
a top-level selector with a `@media`-nested selector in one rule,
we emit two rule blocks with identical bodies — one for the manual
override, one inside the media query. The ~15 lines of duplication
is acceptable; the alternative (CSS custom-property indirection)
hurts readability.

```css
:root[data-theme="light"] { /* palette */ }
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]):not([data-theme="light"]) {
    /* same palette */
  }
}
```

### C2.4 — Pre-paint script (FOUC guard)

Add as the **first** `<script>` inside `<head>`, before the pdf.js loader
and before any `<style>` block. The pdf.js script can stay where it is
(line ~15) but this one needs to run before paint:

```html
<script>
(function(){
  try {
    var pref = localStorage.getItem('docdiff:theme');
    if (pref === 'light' || pref === 'dark') document.documentElement.dataset.theme = pref;
  } catch (_) {}
})();
</script>
```

The `try/catch` handles localStorage access being disabled (private
mode). Without this script, the page would flash dark for ~100ms before
JS later applies the user's saved light preference.

### C2.5 — Settings UI

Insert a new `.settings-row` block in the Settings modal (after the
existing default-sort row, before the clear-data row):

```html
<div class="settings-row">
  <label>Тема оформления</label>
  <select id="settings-theme">
    <option value="auto">Авто (по системе)</option>
    <option value="light">Светлая</option>
    <option value="dark">Тёмная</option>
  </select>
</div>
```

`_initSettingsModal` populates the dropdown from
`localStorage.getItem('docdiff:theme') || 'auto'`. Save handler:

```js
const themeVal = document.getElementById('settings-theme').value;
if (themeVal === 'auto') {
  localStorage.removeItem('docdiff:theme');
  delete document.documentElement.dataset.theme;
} else {
  localStorage.setItem('docdiff:theme', themeVal);
  document.documentElement.dataset.theme = themeVal;
}
```

### C2.6 — Tested surfaces

After the palette swap, manually verify:

- Status colors keep semantic meaning: red/green/amber visible on both
  bg/panel. (Spot-check: `.kpi.high`, `.kpi.review`, `.evt-table` rows.)
- The brand-dot gradient `(#ff5470, #4cc3ff)` works on light bg (it
  should — it's saturated enough).
- `--hi` highlight (yellow at 0.85 alpha) is visible on white. Yellow
  on white is borderline; if illegible during verification, switch to
  `rgba(255, 196, 0, 0.85)` (darker yellow).
- Donut chart in the detail KPIs uses the same status palette — should
  auto-theme.
- Toast colors (success green, error red): existing CSS uses
  `var(--green)` / `var(--red)` — auto-themes.
- Help-modal `<kbd>` background uses `--panel-2` — auto-themes.

### C2.7 — Risk: shadow regression in light mode

`--shadow: 0 6px 28px rgba(0,0,0,0.10)` is a much lighter shadow than
dark's `0 6px 28px rgba(0,0,0,0.45)`. Any element using `var(--shadow)`
(modals, dropzone hover) will look noticeably flatter in light mode.
This is the intended trade-off; light themes typically use weaker
shadows.

## C3 — Responsive viewer (~130 LOC)

One commit, lands last. Risk: medium–high (viewer is the most complex
modal; sync-scroll, zoom, search, bbox overlay all interact).

### C3.1 — Two breakpoints

| Width | Layout |
|---|---|
| ≥1024 px | Unchanged. Today's `LHS | RHS | sidebar` 3-column. |
| 600–1024 px | Sidebar collapses to a slide-in drawer. LHS|RHS stays side-by-side, uses freed width. New `📑 События` toggle in `.vm-head`. |
| <600 px | LHS stacks above RHS (50% height each). Drawer unchanged. |

### C3.2 — Drawer CSS (≤1024 px)

```css
@media (max-width: 1024px) {
  .viewer-modal .vm-sidebar {
    position: absolute;
    right: 0;
    top: 56px; /* below vm-head */
    bottom: 0;
    width: min(360px, 85vw);
    transform: translateX(100%);
    transition: transform 0.2s ease;
    z-index: 10;
    box-shadow: -4px 0 20px rgba(0,0,0,0.3);
  }
  .viewer-modal .vm-sidebar.open { transform: translateX(0); }
  .viewer-modal .vm-panes { width: 100%; }
}
```

The `top: 56px` matches the existing `.vm-head` height (assumed; verify
during implementation).

### C3.3 — Stack panes CSS (<600 px)

```css
@media (max-width: 600px) {
  .viewer-modal .vm-panes { flex-direction: column; }
  .viewer-modal .vm-pane { width: 100%; height: 50%; }
}
```

### C3.4 — Drawer toggle button

In `.vm-head`, insert a new button **before** `.vm-zoom`:

```html
<button id="vm-drawer-toggle" class="vm-drawer-toggle" aria-label="События" aria-expanded="false" hidden>📑</button>
```

Show via media query:

```css
.vm-drawer-toggle {
  background: var(--panel-2); border: 1px solid var(--line);
  color: var(--fg); padding: 5px 10px; border-radius: 5px;
  font-size: 14px; cursor: pointer;
}
@media (max-width: 1024px) { .vm-drawer-toggle { display: inline-block; } .vm-drawer-toggle[hidden] { display: inline-block; } }
@media (min-width: 1025px) { .vm-drawer-toggle[hidden] { display: none; } }
```

The `[hidden]` attribute on the button is the desktop default. The
`@media (max-width: 1024px)` rule overrides it to display.

NOTE: this fights the existing global `[hidden] { display: none !important }`
rule. We need a higher-specificity workaround:

```css
@media (max-width: 1024px) {
  .vm-drawer-toggle { display: inline-block !important; }
}
```

The `!important` is necessary here because the global `[hidden]`
guard uses `!important`. This is an exception, documented inline.

### C3.5 — Toggle JS

In the init block (after viewer modal wiring):

```js
document.getElementById('vm-drawer-toggle').addEventListener('click', () => {
  const sidebar = document.querySelector('.viewer-modal .vm-sidebar');
  const btn = document.getElementById('vm-drawer-toggle');
  const open = sidebar.classList.toggle('open');
  btn.setAttribute('aria-expanded', String(open));
});
```

### C3.6 — Escape handler integration

`closeInlineViewer` Escape path (line ~2389): before closing the
viewer, check if the drawer is open. If yes, close the drawer first.

```js
// Inside the existing viewer-modal keydown handler:
if (e.key === 'Escape') {
  const sidebar = document.querySelector('.viewer-modal .vm-sidebar');
  if (sidebar?.classList.contains('open')) {
    sidebar.classList.remove('open');
    document.getElementById('vm-drawer-toggle').setAttribute('aria-expanded', 'false');
    return;
  }
  closeInlineViewer();
  return;
}
```

### C3.7 — Drawer state reset

On viewer close (`closeInlineViewer`), reset the drawer:

```js
const sb = document.querySelector('.viewer-modal .vm-sidebar');
sb?.classList.remove('open');
document.getElementById('vm-drawer-toggle')?.setAttribute('aria-expanded', 'false');
```

So reopening the viewer always starts with the drawer closed.

### C3.8 — Risks

1. **Sync-scroll conflict at <600 px** — LHS/RHS stacked vertically.
   The existing sync-scroll wires horizontal-pair scrolling. Stacked
   layout may produce weird coupling. Mitigation: disable sync-scroll
   below 600 px (a `window.innerWidth < 600` guard in the sync handler).
2. **Bbox overlay positioning** — bbox uses absolute positioning
   relative to the PDF pane. Should auto-adapt to pane resize via the
   existing zoom/resize code. Verify during implementation.
3. **Focus trap inside drawer** — when drawer is open, the focus trap
   (from Bundle 2) still includes the (off-screen) LHS/RHS elements
   technically reachable via Tab. Acceptable for now; advanced
   solution would temporarily set `tabindex="-1"` on the off-screen
   panes when drawer is open.
4. **Search input inside drawer** — sidebar contains the search input;
   when drawer is closed, the input is off-screen but still focusable.
   Same acceptable-for-now answer as risk 3.

## File-by-file change summary

| File | C1 | C2 | C3 |
|---|---|---|---|
| `docdiffops_mvp/docdiffops/app_html.py` | skip-link markup + CSS, `id`+`tabindex` on `<main>` | dark-keep + light palette CSS, pre-paint script in `<head>`, settings-theme `<select>` row + handler in `_initSettingsModal` | drawer media queries, vm-drawer-toggle button + CSS + JS, viewer Escape integration, drawer state reset on close |

No other files change. No Python touched.

## Verification plan

### Static audit (Python script)

Following Bundle 1+2 precedent, write a Python audit checking:

- `class="skip-link"` and `id="main-content" tabindex="-1"` exist
- `:root[data-theme="light"]` block present with all expected vars
- `@media (prefers-color-scheme: light)` block present
- Pre-paint script reads `docdiff:theme` key
- `#settings-theme` select present with 3 options
- `@media (max-width: 1024px)` block targets `.vm-sidebar`
- `@media (max-width: 600px)` block stacks `.vm-panes`
- `#vm-drawer-toggle` button markup + click handler in source

### Runtime smoke (playwright + chromium)

- Skip-link: Tab from address bar → focus on skip-link, Enter → `<main>` focused.
- Theme toggle: change Settings → `<select>` value, save, reload → `<html>` has `data-theme="light"`. Pre-paint script confirmed via no FOUC (verify with `getComputedStyle(document.body).backgroundColor` after navigation).
- Drawer: resize viewport to 800px, open viewer → sidebar offscreen, click 📑 → sidebar slides in (verify `classList.contains('open')`). Click 📑 again → closes.
- Esc-from-drawer: with drawer open, press Esc → drawer closes, viewer stays. Esc again → viewer closes.
- Pane stacking: resize to 500px, open viewer → `.vm-panes` flex-direction is `column`.

## Definition of done

C1 commit (`feat(ui): skip-to-content link`), C2 commit (`feat(ui): light theme + auto/manual toggle`), C3 commit (`feat(ui): responsive viewer — drawer below 1024px, stack below 600px`). Each commit independently verified per the relevant audit + smoke. Total LOC ≤300, in line with the spec's ~250 estimate.
