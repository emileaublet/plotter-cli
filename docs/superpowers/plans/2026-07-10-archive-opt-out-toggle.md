# Archiving Opt-Out Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visible, one-shot "opt out of archiving" toggle to Plotter Studio's header, whose value is echoed through the `/api/export` response so Claude (operating outside the app) can decide whether to run the archive step after an export.

**Architecture:** Pure client-side boolean (`archiveNextExport`, default `true`) toggled by a new header button. `export()` sends it as `archive` in the `/api/export` POST body; the Flask route passes it straight through into the `"done"` NDJSON event. The frontend resets the toggle to `true` after every export attempt (success or failure), and a page reload also resets it since there's no persistence layer involved.

**Tech Stack:** Flask (`gui_app.py`), vanilla JS (`app.js`), Lucide icons, existing CSS (`style.css`).

## Global Constraints

- No new persistence: no `settings.yaml` field, no `localStorage`, no database row. State lives only in the running JS instance and resets on export-complete or page reload.
- Toggle must default to "archiving on" (`archiveNextExport = true`).
- No test framework exists in this repo (see `CLAUDE.md`, "No Tests") — every verification step below is manual (curl / browser), not `pytest`.
- Apply changes via `pipx install . --force` before manual verification, per `CLAUDE.md` (never `pip install -e .`).

---

### Task 1: Backend — echo `archive` flag through `/api/export`

**Files:**
- Modify: `plotter_cli/gui_app.py:1165-1174` (`_build_export_response`)
- Modify: `plotter_cli/gui_app.py:1187-1188` (`export()` route body)

**Interfaces:**
- Consumes: nothing new — reads `archive` key from the existing `request.json` dict already captured as `data`.
- Produces: `_build_export_response(output_folder, pipeline_result, archive)` — third positional param, `bool`. The `"done"` NDJSON event now contains an `"archive"` key (`true`/`false`) alongside the existing `success`, `output_folder`, `combined_svg`, `gcode_files`, `guide_gcode`, `stats` keys. Later tasks (frontend) don't consume this response field directly, but any future Claude-side archive-CLI integration will.

- [ ] **Step 1: Read the `archive` flag from the request body**

In `plotter_cli/gui_app.py`, in the `export()` route, immediately after the existing `output_folder = ...` line (currently line 1188):

```python
    data = request.json
    output_folder = data.get("output_folder") or tempfile.mkdtemp(prefix="plotter_export_")
    archive = bool(data.get("archive", True))
```

- [ ] **Step 2: Pass `archive` into `_build_export_response`**

Update the call site (currently line 1259):

```python
            events.put(
                {"type": "done", **_build_export_response(output_folder, pipeline_result, archive)}
            )
```

- [ ] **Step 3: Update `_build_export_response` to accept and include `archive`**

Replace the current function (lines 1165-1174):

```python
def _build_export_response(output_folder, pipeline_result, archive=True):
    """Build the JSON response dict for a successful export."""
    return {
        "success": True,
        "output_folder": output_folder,
        "combined_svg": pipeline_result["combined_svg"],
        "gcode_files": pipeline_result["gcode_files"],
        "guide_gcode": pipeline_result["guide_gcode"],
        "stats": pipeline_result["stats"],
        "archive": archive,
    }
```

- [ ] **Step 4: Apply the change and verify manually**

Run:

```bash
pipx install . --force
plotter studio
```

With Studio running and at least one paper with an assigned SVG on the canvas, in a second terminal run:

```bash
curl -s -X POST http://127.0.0.1:5000/api/export \
  -H 'Content-Type: application/json' \
  -d '{"output_folder": "/tmp/plotter_archive_toggle_test", "archive": false}' \
  | tail -1 | python3 -m json.tool
```

(Adjust the port if Studio logs a different one on startup.)

Expected: the last NDJSON line is the `"done"` event and its parsed JSON includes `"archive": false`. Re-run without `"archive"` in the body (or with `"archive": true`) and confirm the field reads `"archive": true`.

- [ ] **Step 5: Commit**

```bash
git add plotter_cli/gui_app.py
git commit -m "feat: echo archive flag through /api/export response"
```

---

### Task 2: CSS — add `.btn-warning` style

**Files:**
- Modify: `plotter_cli/gui/static/style.css` (after `.btn-danger:hover`, currently ending at line 440)

**Interfaces:**
- Consumes: existing `.btn` base class (`plotter_cli/gui/static/style.css:392-405`) for layout/sizing; this task only adds a color variant.
- Produces: CSS classes `.btn-warning` and `.btn-warning:hover`, applied to elements alongside the base `.btn` class (e.g. `class="btn btn-warning"`) — consumed by Task 3's HTML.

- [ ] **Step 1: Add the warning button style**

In `plotter_cli/gui/static/style.css`, immediately after the `.btn-danger:hover` block (currently lines 438-440):

```css
.btn-warning {
  background: rgba(251, 191, 36, 0.15);
  color: #fef3c7;
  border: 1px solid rgba(251, 191, 36, 0.5);
}

.btn-warning:hover {
  background: rgba(251, 191, 36, 0.25);
}
```

This reuses the same amber palette already used by `.calibration-settings-banner-warning` (`plotter_cli/gui/static/style.css:385-389`), so the "opted out" state reads consistently with the app's existing warning styling.

- [ ] **Step 2: Verify visually**

No app restart needed for a static asset — reload the Studio browser tab after Task 3 wires up the markup, or temporarily add `class="btn btn-warning"` to any existing button (e.g. `#clear-all-btn` in `index.html`) and confirm it renders with an amber border/background, then revert the temporary change.

- [ ] **Step 3: Commit**

```bash
git add plotter_cli/gui/static/style.css
git commit -m "feat: add btn-warning style for archive opt-out toggle"
```

---

### Task 3: HTML — add the toggle button markup

**Files:**
- Modify: `plotter_cli/gui/templates/index.html:47-62` (`.header-actions` block)

**Interfaces:**
- Consumes: `.btn`, `.btn-secondary`, `.btn-warning` (Task 2) CSS classes; Lucide `data-lucide` icon pattern already used by sibling buttons.
- Produces: DOM elements `#archive-toggle-btn` (button), `#archive-toggle-icon` (`<i>`), `#archive-toggle-text` (`<span>`) — consumed by Task 4's JS.

- [ ] **Step 1: Insert the button between `#fullscreen-btn` and `#export-btn`**

In `plotter_cli/gui/templates/index.html`, replace the current block (lines 47-62):

```html
        <div class="header-actions">
          <button id="settings-btn" class="btn btn-secondary" title="Settings">
            <i data-lucide="settings" class="icon" style="width: 16px; height: 16px;"></i>
          </button>
          <button id="clear-all-btn" class="btn btn-secondary" title="Clear All">
            <i data-lucide="trash-2" class="icon" style="width: 16px; height: 16px;"></i>
          </button>
          <button id="fullscreen-btn" class="btn btn-secondary" title="Toggle Fullscreen">
            <i data-lucide="maximize" class="icon" style="width: 16px; height: 16px;"></i>
          </button>
          <button id="archive-toggle-btn" class="btn btn-secondary" title="Opt this next export out of archiving (resets after export)">
            <i id="archive-toggle-icon" data-lucide="save" class="icon" style="width: 16px; height: 16px;"></i>
            <span id="archive-toggle-text">ARCHIVING</span>
          </button>
          <button id="export-btn" class="btn btn-primary">
            <i data-lucide="download" class="icon" style="width: 16px; height: 16px;"></i>
            <span id="export-btn-text">Export</span>
            <span id="export-btn-spinner" class="spinner" style="display: none"></span>
          </button>
        </div>
      </header>
```

- [ ] **Step 2: Verify the markup renders**

```bash
pipx install . --force
plotter studio
```

Confirm a new button labeled "ARCHIVING" with a save icon appears in the header, left of "Export". It won't do anything yet (Task 4 wires behavior) — clicking it is a no-op at this point, which is expected.

- [ ] **Step 3: Commit**

```bash
git add plotter_cli/gui/templates/index.html
git commit -m "feat: add archive toggle button markup to header"
```

---

### Task 4: JS — wire toggle state, click handler, and export() integration

**Files:**
- Modify: `plotter_cli/gui/static/app.js` (constructor/init area where other instance flags like `this.exportAbortController` are declared — search for `this.exportAbortController = null` to find the right neighborhood)
- Modify: `plotter_cli/gui/static/app.js:616` (event listener registration block)
- Modify: `plotter_cli/gui/static/app.js:2096-2237` (`export()` method)

**Interfaces:**
- Consumes: `#archive-toggle-btn`, `#archive-toggle-icon`, `#archive-toggle-text` DOM elements (Task 3); global `lucide.createIcons()` (already used elsewhere in `app.js`, e.g. line 394 per prior exploration).
- Produces: `this.archiveNextExport` (`boolean`, default `true`); `this.updateArchiveToggleUI()` (no args, repaints the button to match `this.archiveNextExport`); both used only within this file, no other task depends on them.

- [ ] **Step 1: Find where `this.exportAbortController` is initialized**

```bash
grep -n "this.exportAbortController = null" /Users/emileaublet/Dev/plotter-cli/plotter_cli/gui/static/app.js
```

Expect one hit outside the `export()` method itself — that's the constructor/init declaration. Add the new field on the line immediately after it:

```javascript
    this.exportAbortController = null;
    this.archiveNextExport = true;
```

- [ ] **Step 2: Add the `updateArchiveToggleUI()` method**

Add this as a new method on the same class as `export()` (place it directly above `async export() {` at line 2096):

```javascript
  updateArchiveToggleUI() {
    const btn = document.getElementById('archive-toggle-btn');
    const icon = document.getElementById('archive-toggle-icon');
    const text = document.getElementById('archive-toggle-text');
    if (!btn || !icon || !text) return;

    if (this.archiveNextExport) {
      btn.classList.remove('btn-warning');
      btn.classList.add('btn-secondary');
      icon.setAttribute('data-lucide', 'save');
      text.textContent = 'ARCHIVING';
    } else {
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-warning');
      icon.setAttribute('data-lucide', 'save-off');
      text.textContent = 'NOT ARCHIVING';
    }
    lucide.createIcons({ nodes: [icon] });
  }

  async export() {
```

- [ ] **Step 3: Wire the click handler**

In `plotter_cli/gui/static/app.js`, find the existing listener registration (currently line 616):

```javascript
    document.getElementById('export-btn')?.addEventListener('click', () => this.export());
```

Add a new listener immediately above it:

```javascript
    document.getElementById('archive-toggle-btn')?.addEventListener('click', () => {
      this.archiveNextExport = !this.archiveNextExport;
      this.updateArchiveToggleUI();
    });
    document.getElementById('export-btn')?.addEventListener('click', () => this.export());
```

- [ ] **Step 4: Send `archive` in the export request body**

In `export()`, update the `/api/export` fetch call (currently lines 2179-2184):

```javascript
      // Proceed with export — response is a stream of NDJSON progress events
      const response = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_folder: outputFolder || null, archive: this.archiveNextExport }),
        signal: abortController.signal,
      });
```

- [ ] **Step 5: Reset the toggle after every export attempt**

In `export()`, update the `finally` block (currently lines 2231-2236) to also reset and repaint the toggle:

```javascript
    } finally {
      exportBtn.disabled = false;
      exportText.textContent = 'Export';
      exportSpinner.style.display = 'none';
      this.exportAbortController = null;
      this.archiveNextExport = true;
      this.updateArchiveToggleUI();
    }
  }
```

Note this `finally` block already runs on every code path out of `export()` (success, thrown error, and the early `return`s for user-cancelled folder picker/prompt do **not** go through `finally` since they're plain `return`s inside the `try` before any exception — but those early returns happen *before* the archive-carrying fetch call is ever sent, so there's nothing to reset in those cases; the toggle correctly stays as the user left it if they cancel before the export actually fires). Confirm this by re-reading the two early-return blocks at lines 2157-2163 and 2169-2175 — they return from inside the `try`, which in JS still runs the `finally` block before the function returns. So the toggle **will** reset even on folder-picker cancellation. This is acceptable per the spec (reset happens "after the next export completes" — an aborted export before submission counts as nothing having happened, but resetting to default here is harmless and simpler than special-casing it).

- [ ] **Step 6: Add `updateArchiveToggleUI()` call to initial page setup**

Find the app's init/constructor method where the UI is first rendered on load (search for where `lucide.createIcons()` is called at startup, or where other initial UI state is painted):

```bash
grep -n "lucide.createIcons()" /Users/emileaublet/Dev/plotter-cli/plotter_cli/gui/static/app.js
```

Add a call to `this.updateArchiveToggleUI();` right after the first such call in the app's init flow, so the button shows the correct default label on page load rather than relying only on the raw HTML text.

- [ ] **Step 7: Apply and verify manually**

```bash
pipx install . --force
plotter studio
```

In the browser:
1. Confirm the header button reads "ARCHIVING" with a save icon on load.
2. Click it — confirm it switches to "NOT ARCHIVING" with a warning (amber) style and a different icon.
3. Add an SVG + paper to the canvas, click Export, choose/enter an output folder, let it complete.
4. Confirm the button reverts to "ARCHIVING" (default style) immediately after the export finishes.
5. Open the browser's Network tab (or re-run the `curl` check from Task 1 Step 4) to confirm the POST body included `"archive": false` for that export.

- [ ] **Step 8: Commit**

```bash
git add plotter_cli/gui/static/app.js
git commit -m "feat: wire archive opt-out toggle into export flow"
```

---

## Plan Self-Review Notes

- **Spec coverage:** header placement (Task 3), default-on / one-shot reset (Task 4 Steps 1, 5), two-state visual (Tasks 2-4), request/response echo (Task 1, Task 4 Step 4), no persistence (no `settings.yaml`/`localStorage` touched anywhere in this plan) — all covered.
- **Type consistency:** `archive` is a `bool` end-to-end — JS `this.archiveNextExport` (boolean) → JSON `archive` → Python `bool(data.get("archive", True))` → response `"archive": archive`. Consistent naming (`archiveNextExport`, `archive`, `archive`) across all four tasks, no renamed variants.
- **No placeholders:** every step has literal code, not descriptions.
