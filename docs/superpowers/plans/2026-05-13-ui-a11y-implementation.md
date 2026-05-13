# UI A11y & Polish Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two atomic commits to `docdiffops_mvp/docdiffops/app_html.py` closing the remaining a11y/UX gaps from the recent UI polish thread.

**Architecture:** All work happens inside the single-file SPA (`app_html.py`, 2709 lines, an `APP_HTML` string blob with inline CSS + vanilla JS served at `GET /`). Bundle 1 ships defensive bugfixes and ARIA labels (~30 LOC). Bundle 2 adds proper modal dialog semantics, a focus-trap helper, focus restoration, reduced-motion compliance, focus-visible rings, and live regions for toasts (~100 LOC). No Python touched. No new files.

**Tech Stack:** Vanilla JS, inline CSS, `pdf.js` (already bundled), HTML5 `hidden`/`role`/`aria-*` attributes. No build step.

**Spec:** `docs/superpowers/specs/2026-05-13-ui-a11y-design.md` (commit `38fc917`).

**Verification model:** No automated tests exist for `app_html.py` (it's a Python string). Each task ends with manual verification steps a human (or qa-tester agent) can execute via `docker compose up` against `http://localhost:8000/`. Code steps that change JS or CSS still get committed; manual smoke happens at the end of each bundle.

---

## File Map

| File | Why it changes |
|---|---|
| `docdiffops_mvp/docdiffops/app_html.py` | Only file modified across all tasks. CSS block extended, HTML markup tweaked, JS handlers added/extended. |

---

# Bundle 1 — Defensive fixes

Single commit at the end of Bundle 1.

## Task 1: Extend global keydown guards (SELECT, contenteditable)

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` lines 2372-2373 (viewer handler) and 2384-2385 (help handler)

- [ ] **Step 1: Read the current viewer-modal keydown handler**

The current code at lines 2368-2382 is:

```js
document.addEventListener('keydown', e => {
  const modal = document.getElementById('viewer-modal');
  if (modal.hidden) return;
  // Don't intercept when typing in filter input or popover textarea
  const tag = (e.target && e.target.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (e.key === 'Escape') { closeInlineViewer(); return; }
  ...
```

- [ ] **Step 2: Extend the viewer-modal handler guard**

Replace the two-line guard (lines 2371-2373) with:

```js
  // Don't intercept when typing in filter input, popover textarea, an
  // open <select> (j/k would otherwise hijack dropdown nav), or any
  // contenteditable surface (defends future rich-text inputs).
  const t = e.target;
  const tag = (t && t.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) return;
```

- [ ] **Step 3: Extend the help/global handler guard**

At lines 2383-2385 the current code is:

```js
document.addEventListener('keydown', e => {
  const tag = (e.target && e.target.tagName || '').toUpperCase();
  const inInput = tag === 'INPUT' || tag === 'TEXTAREA';
```

Replace with:

```js
document.addEventListener('keydown', e => {
  const t = e.target;
  const tag = (t && t.tagName || '').toUpperCase();
  const inInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable);
```

The `inInput` variable is reused later at line 2405 (`if (inInput) return;`) which is what gates the `h`/`?` shortcut — this expansion automatically protects it too. The Escape paths above the `inInput` check (lines 2388 and 2396) are intentionally left to fire from inside inputs because Escape-from-input is desirable behaviour (closes help modal / dismisses toasts).

- [ ] **Step 4: Do NOT commit yet**

Hold the commit for the end of Bundle 1. Move to Task 2.

---

## Task 2: Anchor → button for topbar Settings + Help triggers

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` lines 489-490 (HTML), add CSS rule near line 58 (after `.tab` rule), add JS wiring in the init block.

- [ ] **Step 1: Add the `.topbar-btn` CSS class**

Locate the existing `.tab` rule at line 58. Immediately after the `.tab:hover:not(.active)` rule at line 60, insert a new rule:

```css
.topbar-btn {
  background: transparent; border: 0; padding: 0;
  color: var(--mute); font: inherit; font-size: 12px;
  cursor: pointer;
}
.topbar-btn:hover { color: var(--fg); text-decoration: underline; }
```

The `font: inherit` is important — without it, `<button>` ships its own font-family and the topbar text would shift.

- [ ] **Step 2: Replace the two `<a href="#">` openers**

Lines 489-490 currently:

```html
    <a href="#" onclick="document.getElementById('settings-modal').hidden=false;return false" title="Настройки">⚙ Настройки</a>
    <a href="#" onclick="document.getElementById('help-modal').hidden=false;return false" title="Горячие клавиши">⌨️ Горячие клавиши</a>
```

Replace with:

```html
    <button type="button" class="topbar-btn" id="topbar-settings-btn" title="Настройки">⚙ Настройки</button>
    <button type="button" class="topbar-btn" id="topbar-help-btn" title="Горячие клавиши">⌨️ Горячие клавиши</button>
```

- [ ] **Step 3: Wire the click handlers in JS**

Find `_initSettingsModal()` at line ~2638. Immediately after the existing `_initSettingsModal();` call at line ~2689, append a new wiring block:

```js
// Topbar openers (replaced <a href="#" onclick=…> with <button> for a11y).
document.getElementById('topbar-settings-btn').addEventListener('click', () => {
  document.getElementById('settings-modal').hidden = false;
});
document.getElementById('topbar-help-btn').addEventListener('click', () => {
  document.getElementById('help-modal').hidden = false;
});
```

Note: do NOT put `e.preventDefault()` here — `<button type="button">` doesn't submit a form, so there's nothing to prevent. The `type="button"` attribute on the markup makes that explicit.

- [ ] **Step 4: Do NOT commit yet**

Move to Task 3.

---

## Task 3: Aria-label audit on emoji-only buttons

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` lines 637, 659, 1075

- [ ] **Step 1: Add `aria-label` to the help-modal close button**

Line 637 currently:

```html
      <button style="background:transparent;border:0;color:var(--mute);font-size:18px;cursor:pointer" onclick="document.getElementById('help-modal').hidden=true">✕</button>
```

Replace with:

```html
      <button aria-label="Закрыть подсказку" style="background:transparent;border:0;color:var(--mute);font-size:18px;cursor:pointer" onclick="document.getElementById('help-modal').hidden=true">✕</button>
```

- [ ] **Step 2: Add `aria-label` to the settings-modal close button**

Line 659 currently:

```html
      <button style="background:transparent;border:0;color:var(--mute);font-size:18px;cursor:pointer" onclick="document.getElementById('settings-modal').hidden=true">✕</button>
```

Replace with:

```html
      <button aria-label="Закрыть настройки" style="background:transparent;border:0;color:var(--mute);font-size:18px;cursor:pointer" onclick="document.getElementById('settings-modal').hidden=true">✕</button>
```

- [ ] **Step 3: Add `aria-label` to the batch-delete button**

Line 1075 currently:

```js
        <button class='batch-del' data-bid='${escapeHtml(b.batch_id)}' title='Удалить batch' style='background:transparent;border:0;color:var(--mute);cursor:pointer;font-size:13px;padding:0 4px'>🗑</button>
```

Replace with:

```js
        <button class='batch-del' data-bid='${escapeHtml(b.batch_id)}' aria-label='Удалить batch' title='Удалить batch' style='background:transparent;border:0;color:var(--mute);cursor:pointer;font-size:13px;padding:0 4px'>🗑</button>
```

`title` is unreliable for screen readers on touch devices — `aria-label` is the canonical fix. Keep `title` too for desktop tooltip hover.

- [ ] **Step 4: Verify no other emoji-only buttons need labels**

Other emoji-only `<button>` elements already covered (do NOT change):
- Line 828 toast dismiss `×` — `xBtn.setAttribute('aria-label', 'dismiss')` set in JS
- Line 880 staged-file `×` — `aria-label='remove'` in template literal
- Line 2281 pop-close `✕` — has `aria-label="close"`
- Line 676 settings-clear 🗑 — visible Russian text supplies the accessible name; the emoji is decorative

The viewer-modal close button (line ~289) has visible text "Закрыть"; no aria-label needed.

- [ ] **Step 5: Do NOT commit yet**

Move to Task 4 to verify the whole bundle and commit.

---

## Task 4: Verify Bundle 1 manually and commit

**Files:**
- Commit: `docdiffops_mvp/docdiffops/app_html.py`

- [ ] **Step 1: Bring up the stack**

```bash
cd /home/dev/diff/docdiffops_mvp
docker compose up -d --build api
```

Wait until `http://localhost:8000/` returns 200.

If `docker compose` is unavailable (CI, sandbox), skip manual verification and rely on diff review only — note this in the commit message.

- [ ] **Step 2: Verify keydown guards**

Open `http://localhost:8000/`. Open an existing batch (or upload three small docs and run with `?profile=fast`). Inside the batch detail:

- Click the pairs tab. Open the pairs-sort `<select>`. Press `j` and `k` while the dropdown is open — the dropdown should navigate options, NOT trigger viewer jumps (which would be a no-op here anyway since viewer is closed).
- Open the inline viewer on any pair. Open the sort dropdown again. Press `j` — dropdown navigates; viewer does NOT advance.
- Open the Settings modal (top-bar ⚙ button). Click into "Имя reviewer'а", type "Henry" — no help-modal popup. Open the dropdown, press `k` — dropdown navigates; help-modal does NOT pop.

- [ ] **Step 3: Verify topbar buttons are keyboard-reachable**

Reload the page. Press `Tab` repeatedly from the address bar. Confirm the ⚙ and ⌨️ buttons receive focus in source order, and pressing `Enter` on each opens the corresponding modal. Pressing `Space` should also work (default `<button>` behaviour).

- [ ] **Step 4: Verify aria-labels with the DevTools accessibility panel**

In Chrome/Firefox DevTools → Accessibility → Inspect each modified element. Confirm the accessible name reads "Закрыть подсказку", "Закрыть настройки", "Удалить batch" respectively. The topbar buttons should read "Настройки" / "Горячие клавиши" (from `title`, which becomes the accessible name when `aria-label` is absent — adequate here since visible text is also present).

- [ ] **Step 5: Commit Bundle 1**

```bash
cd /home/dev/diff
git add docdiffops_mvp/docdiffops/app_html.py
git commit -m "$(cat <<'EOF'
feat(ui): a11y bugfix sweep — keydown guards + button semantics + aria-labels

Bundle 1 from docs/superpowers/specs/2026-05-13-ui-a11y-design.md:

1. Extend global keydown guards to SELECT and [contenteditable]. j/k while
   pairs-sort dropdown is open no longer hijacks viewer jumps. h while
   typing in settings reviewer name no longer pops the help modal.

2. Topbar Settings (⚙) and Help (⌨️) anchors → <button> with proper click
   wiring. Adds .topbar-btn CSS class. Fixes screen-reader semantics and
   drops the `return false` href="#" hack.

3. aria-label on emoji-only buttons: help-modal ✕, settings-modal ✕,
   batch-del 🗑. Other emoji buttons already had labels (toast dismiss,
   staged-file ×, pop-close ✕).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Bundle 2 — A11y + motion

Single commit at the end of Bundle 2.

## Task 5: Add dialog role + aria-modal + aria-labelledby to four modals

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` lines 633, 636 (help-modal); 655, 658 (settings-modal); viewer-modal `<h3>` in `.vm-head`; rename overlay in `_renameBatchInline`.

- [ ] **Step 1: Help modal**

Line 633 currently:

```html
<div id="help-modal" hidden onclick="if(event.target===this)this.hidden=true">
```

Replace with:

```html
<div id="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-modal-title" hidden onclick="if(event.target===this)this.hidden=true">
```

Line 636 currently:

```html
      <h3 style="margin:0;font-size:16px">⌨️ Горячие клавиши</h3>
```

Replace with:

```html
      <h3 id="help-modal-title" style="margin:0;font-size:16px">⌨️ Горячие клавиши</h3>
```

- [ ] **Step 2: Settings modal**

Line 655 currently:

```html
<div id="settings-modal" hidden onclick="if(event.target===this)this.hidden=true">
```

Replace with:

```html
<div id="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-modal-title" hidden onclick="if(event.target===this)this.hidden=true">
```

Line 658 currently:

```html
      <h3 style="margin:0;font-size:16px">⚙ Настройки</h3>
```

Replace with:

```html
      <h3 id="settings-modal-title" style="margin:0;font-size:16px">⚙ Настройки</h3>
```

- [ ] **Step 3: Viewer modal**

Find the viewer-modal `<div id="viewer-modal">` opener (search for `class="viewer-modal"` markup). The first `<h3>` inside `.vm-head` is `<h3>📖 Inline viewer</h3>`.

Change the modal root from:

```html
<div id="viewer-modal" class="viewer-modal" hidden>
```

to:

```html
<div id="viewer-modal" class="viewer-modal" role="dialog" aria-modal="true" aria-labelledby="viewer-modal-title" hidden>
```

Change the heading from:

```html
    <h3>📖 Inline viewer</h3>
```

to:

```html
    <h3 id="viewer-modal-title">📖 Inline viewer</h3>
```

- [ ] **Step 4: Inline rename overlay**

The overlay is constructed dynamically inside `_renameBatchInline` near line 810. Find the overlay creation block. The overlay's outer `<div>` gets `role="dialog" aria-modal="true" aria-labelledby="rn-title"`, and the existing label text gets `id="rn-title"`.

Concretely, search the function body for the line that creates the overlay markup (a `document.createElement('div')` + `innerHTML = ...`). Add `role="dialog" aria-modal="true" aria-labelledby="rn-title"` to the overlay's outermost element via `setAttribute`. Find the existing heading/title inside the overlay markup and add `id="rn-title"` to it.

If the overlay has no heading element, wrap the visible prompt text (e.g., "Переименовать batch") in a `<label id="rn-title">` element and reference it.

- [ ] **Step 5: Do NOT commit yet**

Move to Task 6.

---

## Task 6: Implement the `_trapFocus` helper

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — add helper near other modal helpers, before `_initSettingsModal()` at line ~2638.

- [ ] **Step 1: Add the helper function**

Locate the line `// -------- settings modal --------` at line 2635. Immediately before it, insert:

```js
// -------- focus management --------
function _trapFocus(modalEl) {
  if (!modalEl) return () => {};
  const handler = (e) => {
    if (e.key !== 'Tab' || modalEl.hidden) return;
    const focusable = modalEl.querySelectorAll(
      'a[href]:not([disabled]), button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };
  modalEl.addEventListener('keydown', handler);
  return () => modalEl.removeEventListener('keydown', handler);
}

// Map<modalEl, {teardown, lastFocus}> for active focus traps.
const _activeTraps = new WeakMap();

function _openModal(modalEl, focusTarget) {
  if (!modalEl || _activeTraps.has(modalEl)) return;
  const lastFocus = document.activeElement;
  modalEl.hidden = false;
  const teardown = _trapFocus(modalEl);
  _activeTraps.set(modalEl, { teardown, lastFocus });
  // Defer focus to next frame so the modal is laid out before focusing.
  requestAnimationFrame(() => {
    const target = focusTarget || modalEl.querySelector(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    target?.focus?.();
  });
}

function _closeModal(modalEl) {
  if (!modalEl) return;
  const entry = _activeTraps.get(modalEl);
  modalEl.hidden = true;
  if (entry) {
    entry.teardown();
    _activeTraps.delete(modalEl);
    // Restore focus to the opener so Esc doesn't dump the user back to body.
    entry.lastFocus?.focus?.();
  }
}
```

The `WeakMap` keyed by element avoids leaking listener references when a modal element is later removed from the DOM (e.g., the dynamic rename overlay).

- [ ] **Step 2: Do NOT commit yet**

Move to Task 7.

---

## Task 7: Wire `_openModal` / `_closeModal` into existing open/close sites

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — multiple inline `onclick` handlers and JS functions.

Five modal open/close pairs need wiring. Migrate one pair at a time.

- [ ] **Step 1: Help modal — open paths**

Find the topbar Help wiring inserted in Task 2 step 3:

```js
document.getElementById('topbar-help-btn').addEventListener('click', () => {
  document.getElementById('help-modal').hidden = false;
});
```

Replace with:

```js
document.getElementById('topbar-help-btn').addEventListener('click', () => {
  _openModal(document.getElementById('help-modal'));
});
```

Find the global `H` / `?` shortcut at line 2410:

```js
    helpModal.hidden = false;
```

Replace with:

```js
    _openModal(helpModal);
```

- [ ] **Step 2: Help modal — close paths**

Line 637 (close `✕` button) currently:

```html
      <button aria-label="Закрыть подсказку" style="..." onclick="document.getElementById('help-modal').hidden=true">✕</button>
```

Replace the `onclick` with:

```html
onclick="_closeModal(document.getElementById('help-modal'))"
```

Line 633 (backdrop click) currently:

```html
<div id="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-modal-title" hidden onclick="if(event.target===this)this.hidden=true">
```

Replace the `onclick` with:

```html
onclick="if(event.target===this)_closeModal(this)"
```

The Escape handler at line 2388-2392 currently:

```js
  if (e.key === 'Escape' && helpModal && !helpModal.hidden) {
    helpModal.hidden = true;
    e.preventDefault();
    e.stopPropagation();
    return;
  }
```

Replace `helpModal.hidden = true;` with `_closeModal(helpModal);`.

- [ ] **Step 3: Settings modal — open path**

The topbar wiring (from Task 2) becomes:

```js
document.getElementById('topbar-settings-btn').addEventListener('click', () => {
  _openModal(document.getElementById('settings-modal'));
});
```

- [ ] **Step 4: Settings modal — close paths**

Line 659 close `✕` — replace `onclick="document.getElementById('settings-modal').hidden=true"` with `onclick="_closeModal(document.getElementById('settings-modal'))"`.

Line 655 backdrop — replace `onclick="if(event.target===this)this.hidden=true"` with `onclick="if(event.target===this)_closeModal(this)"`.

Line 679 (Cancel button inside settings) currently:

```html
      <button onclick="document.getElementById('settings-modal').hidden=true" style="...">Отмена</button>
```

Replace `onclick` with:

```html
onclick="_closeModal(document.getElementById('settings-modal'))"
```

In `_initSettingsModal` at line 2638, find any `modal.hidden = true;` after a save succeeds — replace with `_closeModal(modal)`. The Escape handler at line 2681-2683 currently:

```js
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !modal.hidden) {
      modal.hidden = true;
```

Replace `modal.hidden = true;` with `_closeModal(modal);`.

- [ ] **Step 5: Viewer modal — open/close paths**

Find `openInlineViewer` (search for `function openInlineViewer` or `async function openInlineViewer`). Inside the function body, find the line that sets `modal.hidden = false` (or similar) and replace with `_openModal(modal)`.

Find `closeInlineViewer`. Inside, find `modal.hidden = true` and replace with `_closeModal(modal)`.

If `openInlineViewer` does substantial layout work AFTER opening the modal (loading PDFs, populating sidebar), keep that work AFTER the `_openModal` call — `_openModal` only sets `hidden = false`, traps focus, and queues an initial focus via `requestAnimationFrame`. The `requestAnimationFrame` fires after layout, so it'll focus on whatever's first by then.

- [ ] **Step 6: Rename overlay — open/close paths**

In `_renameBatchInline` near line 810, after the overlay is appended to the DOM (`document.body.appendChild(overlay)` or similar), call:

```js
_openModal(overlay);
```

The internal `done(value)` function (or equivalent) which currently runs `overlay.remove()` — wrap that:

```js
function done(value) {
  _closeModal(overlay);
  overlay.remove();
  resolve(value);
}
```

The `_closeModal` call restores focus to the original trigger BEFORE the overlay is removed; `overlay.remove()` then removes it from the DOM.

- [ ] **Step 7: Do NOT commit yet**

Move to Task 8.

---

## Task 8: `prefers-reduced-motion` CSS block

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — add CSS block immediately after `:root` block at line 32.

- [ ] **Step 1: Insert the media query**

Immediately after the closing `}` of `:root` at line 32, insert:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
  }
  .dropzone.dragging { transform: none; }
  .batch-card:hover, .pair-card:hover { transform: none; }
}
```

The `0.01ms` (not `0`) ensures JS `transitionend`/`animationend` events still fire — none exist in this file today, but it's a defensive default.

- [ ] **Step 2: Do NOT commit yet**

Move to Task 9.

---

## Task 9: `:focus-visible` rings

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` — add CSS rule after the `button` reset at line 42.

- [ ] **Step 1: Insert the focus-visible rule**

After line 42 (`button { font: inherit; cursor: pointer; }`), insert:

```css
button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[tabindex]:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}
```

Using `:focus-visible` (not `:focus`) means the ring only shows for keyboard focus, not mouse clicks — matches modern browser default behaviour against the existing dark palette.

- [ ] **Step 2: Do NOT commit yet**

Move to Task 10.

---

## Task 10: `aria-live="polite"` on the toast wrap

**Files:**
- Modify: `docdiffops_mvp/docdiffops/app_html.py` line 753.

- [ ] **Step 1: Add `aria-live` and `aria-atomic` attributes**

Line 753 currently:

```html
<div class="toast-wrap" id="toast-wrap"></div>
```

Replace with:

```html
<div class="toast-wrap" id="toast-wrap" aria-live="polite" aria-atomic="false"></div>
```

`aria-atomic="false"` (the default) means screen readers announce only the newly-added toast, not the whole stack on each insertion.

- [ ] **Step 2: Do NOT commit yet**

Move to Task 11.

---

## Task 11: Verify Bundle 2 manually and commit

**Files:**
- Commit: `docdiffops_mvp/docdiffops/app_html.py`

- [ ] **Step 1: Bring up the stack (if not already)**

```bash
cd /home/dev/diff/docdiffops_mvp
docker compose up -d --build api
```

- [ ] **Step 2: Verify dialog roles**

Open `http://localhost:8000/` in Chrome/Firefox. Open the Settings modal. In DevTools → Accessibility (or `F12` → "Accessibility" tab), select the `#settings-modal` element. Confirm:

- Role: "dialog"
- `aria-modal`: true
- Accessible name: "⚙ Настройки" (from `aria-labelledby` pointing at `#settings-modal-title`)

Repeat for help modal, viewer modal, and a triggered rename overlay.

- [ ] **Step 3: Verify focus trap**

Open Settings modal. Press Tab repeatedly — focus cycles among (reviewer input, sort select, clear button, Cancel, Save, close ✕). Shift+Tab cycles in reverse. Focus never escapes to the page behind.

Same loop for Help modal (only the ✕ button is focusable in there since the body is a `<table>` of `<kbd>`s — that's acceptable; Tab stays on `✕`). For viewer modal: many focusable elements; verify cycling.

- [ ] **Step 4: Verify focus restoration**

Click the topbar ⚙ button. Settings opens. Press Escape. Confirm the ⚙ button regains focus (visible focus ring from Task 9). Click the ⌨️ button. Help opens. Click backdrop. Confirm ⌨️ regains focus.

For viewer: open viewer from a pair's 📖 button, close with Escape — focus should return to that 📖 button.

- [ ] **Step 5: Verify reduced-motion**

In DevTools: ⋮ → More tools → Rendering → "Emulate CSS media feature `prefers-reduced-motion`" → `reduce`. Hover a batch card and a pair card — no `translateY(-1px)` lift. Drag a file over the dropzone — no `scale(1.005)` effect.

- [ ] **Step 6: Verify focus-visible rings**

With keyboard only (no mouse): Tab through the page. Each focused control should have a 2px blue outline with 2px offset. Click a button with the mouse — it should NOT show the outline (because `:focus-visible` distinguishes mouse focus).

- [ ] **Step 7: Verify aria-live toasts**

If you have a screen reader (VoiceOver `Cmd+F5`, Orca `Super+Alt+S`, NVDA): trigger a toast (e.g., click delete on a non-existent batch — the error toast appears). The toast text should be announced.

Without a screen reader, verify via DevTools: select `#toast-wrap`, confirm `aria-live="polite"` is present and the live region is registered (Accessibility panel shows it as a live region).

- [ ] **Step 8: Smoke-test no regressions**

End-to-end smoke: upload 2 docs, run a batch, open the viewer, press `j`/`k` to navigate events, press `A` to accept, press Escape to close. All shortcuts still work. Settings save/clear still work. Batch rename works.

- [ ] **Step 9: Commit Bundle 2**

```bash
cd /home/dev/diff
git add docdiffops_mvp/docdiffops/app_html.py
git commit -m "$(cat <<'EOF'
feat(ui): a11y pass — focus trap + dialog roles + reduced-motion + focus-visible

Bundle 2 from docs/superpowers/specs/2026-05-13-ui-a11y-design.md:

1. role=dialog + aria-modal=true + aria-labelledby on 4 modals
   (help, settings, viewer, inline rename overlay).

2. _trapFocus helper + _openModal/_closeModal wrappers. Tab cycles
   stay inside modal. Escape restores focus to the opener.

3. @media (prefers-reduced-motion: reduce) disables transforms and
   shortens transitions site-wide for users who prefer it.

4. :focus-visible outline rings (2px var(--blue)) — keyboard-only
   focus is now visible against the dark palette.

5. aria-live=polite on #toast-wrap. Screen readers announce toast
   text without needing to navigate to the corner.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** All 9 sub-items (B1.1–B1.3, B2.1–B2.6) map to tasks 1–11 with no gaps.
- **Type consistency:** `_openModal` / `_closeModal` / `_trapFocus` / `_activeTraps` names used consistently across tasks 6–7. `topbar-settings-btn` / `topbar-help-btn` IDs used in tasks 2 and 7.
- **Placeholder scan:** No "TBD" / "TODO". All code blocks contain runnable code.
- **Risk note (deferred to verification):** if the focus ring at `:focus-visible` outline-offset 2 px clips badly inside the events table (which is `overflow:hidden`), set `outline-offset: 0` on `.evt-table button:focus-visible`. Re-check during Task 11 step 6; defer the override unless visible clipping occurs.
