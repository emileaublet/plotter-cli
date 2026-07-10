# Paper Export Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `POST /api/export` export only a subset of papers (by id) instead of always exporting everything in `paper_store`, so Claude can isolate one paper's SVG + G-code for archiving without touching the others.

**Architecture:** Add an optional `paper_ids` field to the request body. `_validate_export_papers()` in `gui_app.py` gains an optional parameter and filters `paper_store.items()` by id before building the export list. No other part of the pipeline changes — the guide G-code and canvas dimensions are unaffected, since this filter only scopes which papers' SVGs get combined and exported.

**Tech Stack:** Flask (`gui_app.py`), no frontend changes (this is Claude-driven via direct API calls, not a UI control).

## Global Constraints

- No new persistence.
- Unknown/nonexistent ids in `paper_ids` are silently ignored (not an error) — treat it as a subset filter over whatever currently exists.
- No test framework exists in this repo (see `CLAUDE.md`, "No Tests") — verification is manual (`curl`), not `pytest`.
- Apply via `pipx install . --force` before manual verification (never `pip install -e .`).

---

### Task 1: Add `paper_ids` filtering to `_validate_export_papers` and wire it into the export route

**Files:**
- Modify: `plotter_cli/gui_app.py:1097-1118` (`_validate_export_papers`)
- Modify: `plotter_cli/gui_app.py:1187-1206` (`export()` route — where `data` is read and `_validate_export_papers()` is called)

**Interfaces:**
- Consumes: nothing new — reads `paper_ids` from the existing `request.json` dict (`data`), same dict `archive` is read from per the archive-toggle plan.
- Produces: `_validate_export_papers(paper_ids=None)` — `paper_ids: list[str] | None`. When `None` (default), behavior is unchanged (every paper with an assigned SVG is exported). When a list, only papers whose `id` is in that list are considered.

- [ ] **Step 1: Add the `paper_ids` parameter and filter to `_validate_export_papers`**

Replace the current function (lines 1097-1118):

```python
def _validate_export_papers(paper_ids=None):
    """Build export list from papers with assigned SVGs. Returns list of export entries or raises.

    If paper_ids is given, only papers whose id is in that list are included;
    unknown ids are silently ignored. If None, every assigned paper is included.
    """
    export_svgs = []
    for paper in paper_store.values():
        if paper_ids is not None and paper.get("id") not in paper_ids:
            continue
        svg_id = paper.get("svg_id")
        if not svg_id:
            continue
        svg_data = svg_library.get(svg_id)
        if not svg_data:
            continue
        export_entry = {
            **svg_data,
            "x": paper.get("x", 0),
            "y": paper.get("y", 0),
            "paper_width": paper.get("paper_width", svg_data.get("width", 0)),
            "paper_height": paper.get("paper_height", svg_data.get("height", 0)),
            "paper_name": paper.get("paper_name"),
            "svg_scale": paper.get("svg_scale", 1.0),
            "rotation": paper.get("rotation", 0),
        }
        export_svgs.append(export_entry)
    return export_svgs
```

- [ ] **Step 2: Read `paper_ids` from the request and pass it through**

In the `export()` route, find the call site `export_svgs = _validate_export_papers()` (inside the `worker()` closure, currently line 1206) and the `data = request.json` line at the top of `export()` (currently line 1187, immediately preceding the `output_folder` line touched by the archive-toggle plan). The route needs `paper_ids` captured outside the closure (same way `output_folder` already is) so the worker thread can see it:

```python
    data = request.json
    output_folder = data.get("output_folder") or tempfile.mkdtemp(prefix="plotter_export_")
    archive = bool(data.get("archive", True))
    paper_ids = data.get("paper_ids")
```

(This assumes the archive-opt-out-toggle plan's Task 1 Step 1 has already been applied, adding the `archive` line — if executing this plan first instead, just add the `paper_ids` line directly after `output_folder` without the `archive` line.)

Then update the call site:

```python
            export_svgs = _validate_export_papers(paper_ids)
```

- [ ] **Step 3: Apply and verify manually**

```bash
pipx install . --force
plotter studio
```

With Studio running and at least two papers with assigned SVGs on the canvas, get each paper's `id` (visible via the browser's dev tools inspecting the app state, or by calling `GET /api/state` if such an endpoint exists — otherwise add two papers and note the ids Studio's own UI/network tab shows when they were created via `POST /api/add-paper`). Then run:

```bash
curl -s -X POST http://127.0.0.1:5000/api/export \
  -H 'Content-Type: application/json' \
  -d '{"output_folder": "/tmp/plotter_paper_filter_test", "paper_ids": ["<one-paper-id>"]}' \
  | tail -1 | python3 -m json.tool
```

Expected: the `"done"` event's `gcode_files` list reflects only the one filtered paper's colors (fewer/different files than a full export would produce), and `/tmp/plotter_paper_filter_test/combined.svg` contains only that paper's artwork when opened. Then re-run the same command without `"paper_ids"` and confirm the output reverts to including every paper.

- [ ] **Step 4: Commit**

```bash
git add plotter_cli/gui_app.py
git commit -m "feat: add optional paper_ids filter to /api/export"
```

## Plan Self-Review Notes

- **Spec coverage:** the spec's single requirement (optional `paper_ids` filter, silent-ignore unknown ids, no UI, no persistence) is fully covered by Task 1.
- **Type consistency:** `paper_ids` is `list[str] | None` end-to-end — JS/API caller sends a JSON array or omits the key; Python reads it via `.get("paper_ids")` (returns `None` if absent, matching the function's default).
- **No placeholders:** the full replacement function body and route diff are literal, not described.
