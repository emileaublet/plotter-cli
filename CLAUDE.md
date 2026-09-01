# Plotter CLI — Claude Code Guide

## Build & Install

This project is installed globally via **pipx**. Always use this to apply code changes:

```bash
pipx install . --force
```

Do NOT use `pip install -e .` — the active install is the pipx global one.

Verify:
```bash
plotter --help
```

`vpype` must be installed separately — it is not in `pyproject.toml`.

## Project Overview

CLI + desktop GUI ("Plotter Studio") for processing SVG files for pen plotters. Wraps **vpype** for path optimization and G-code generation.

- `plotter <command>` — CLI tool
- `plotter studio` — Launch native desktop GUI (Flask + pywebview)

## Key Files

| File | Purpose |
|------|---------|
| `plotter_cli/commands.py` | CLI commands (Typer) |
| `plotter_cli/utils.py` | Settings, SVG parsing, G-code utils, stat formatting |
| `plotter_cli/gui_app.py` | Flask routes + in-memory state |
| `plotter_cli/gui_utils.py` | SVG combining, G-code export pipeline |
| `plotter_cli/gcode_parser.py` | Z-height optimization for G-code |
| `plotter_cli/surface_calibration.py` | Bed height map JSON, grid G-code, Z compensation pass |
| `plotter_cli/settings.yaml` | Machine config + paper sizes |
| `plotter_cli/.vpype.toml` | vpype G-code template |
| `plotter_cli/gui/templates/index.html` | GUI HTML |
| `plotter_cli/gui/static/app.js` | GUI JavaScript frontend |
| `plotter_cli/gui/static/style.css` | GUI styles (sketch-2-inspired paper workspace theme) |

## Architecture

- **In-memory state**: `svg_library{}` and `paper_store{}` in `gui_app.py` — no persistence between sessions
- **Coordinate systems**: GUI = top-left origin (Y down); Plotter = bottom-left origin (Y up). Conversion: `y_plotter = canvas_height - y_gui - height`
- **vpype** is called via `subprocess` — must be installed separately
- **Settings load order**: `./settings.yaml` → `plotter_cli/settings.yaml` → hardcoded defaults
- **Native window**: pywebview wraps Flask; Flask runs in a daemon thread

## GUI API Routes

All under `/api/`:
- `POST /api/add-svg` — upload SVG; generates and caches PNG preview
- `GET /api/svg-preview/<id>` — serve cached PNG preview (regenerates on cache miss)
- `POST /api/add-paper` — add paper to canvas
- `POST /api/update-paper` — move/resize/rotate/lock/assign SVG to paper
- `POST /api/auto-arrange` — auto-layout papers in a grid
- `POST /api/align-papers` — align or distribute selected papers (`action`: `align_left`, `align_right`, `align_top`, `align_bottom`, `center_h`, `center_v`, `distribute_h`, `distribute_v`)
- `POST /api/bulk-update-papers` — update multiple paper positions at once
- `POST /api/clone-paper/<id>` — duplicate paper
- `DELETE /api/remove-paper/<id>` — remove a paper
- `DELETE /api/remove-svg/<id>` — remove SVG and its associated papers
- `POST /api/export` — generate combined SVG + G-code output
- `POST /api/clear-all` — remove all papers and SVGs
- `GET|PUT /api/settings` — read/write settings

## G-code Pipeline

1. SVGs combined into one file with transforms (translate, scale, rotate)
2. Passed to vpype via subprocess with dynamic `.vpype.toml`
3. `gcode_parser.py` post-processes: Z-height optimization (short travel ≤ threshold → `z_up_short`; long travel → `z_up_long`), removes registration layer
4. Optional `surface_calibration.py`: if `height_map_path` is set (Studio settings or `plotter process --height-map`), adjusts **pen-down** `Z` on draw moves using bilinear interpolation of the sampled grid (travel / pen-up Z unchanged)
5. Output split per color; files named `file#RRGGBB_colorname.gcode`

## Settings (settings.yaml)

All distances in mm:
- `area_width` / `area_height` — plotter bed size
- `z_up_long` / `z_up_short` / `z_up_threshold` — pen height optimization
- `z_down` — pen-down position
- `feed_rate_draw` / `feed_rate_travel` / `feed_rate_z` — speeds (mm/min)
- `registration_marks_length` — corner mark size
- `height_map_path` — optional path to JSON from `plotter surface-cal sample` (bed Z map)
- `papers[]` — list of `{name, width, height}` in mm

## Dimension Units

Parser supports: `mm`, `cm`, `in`, `pt`, `pc`, `px` (unitless → px at 96dpi).

## GUI Frontend Details

- **Multi-select**: Shift-click to add papers to selection (`selectedPaperIds` Set). All selected papers move together on drag.
- **Undo/redo**: `undoStack` / `redoStack` arrays (max 50). Snapshot taken before any mutation. `Cmd+Z` / `Cmd+Shift+Z`.
- **Snap-to-grid**: `snapToGrid` boolean toggle. Grid = 10mm. Visual grid drawn on canvas when active.
- **Lock**: `paper.locked` — locked papers are unselectable and undeletable.
- **PNG caching**: `svg_data["preview_png_path"]` stores the generated path; only regenerated if file is missing.
- **Toasts**: `showToast(message, type, duration)` — non-blocking feedback. Types: `success`, `error`, `info`.
- **Modals**: `showAlert()` / `showConfirm()` — never use browser `alert()`/`confirm()`.
- **Icons**: After adding Lucide icons to DOM, call `lucide.createIcons({ nodes: [element] })`.

## Dependencies

```
typer, questionary, rich       # CLI
flask, pywebview               # GUI
pyyaml                         # Settings
cairosvg, pillow               # SVG→PNG preview
vpype                          # External, must install separately
```

## No Tests

No test framework is configured. No `tests/` directory exists.

## Common Commands

```bash
plotter studio                  # Launch GUI
plotter process drawing.svg     # Process single SVG (interactive)
plotter process drawing.svg --height-map bed.json  # Same + bed height map
plotter surface-cal grid -o .   # G-code: X grid on full bed for sampling
plotter surface-cal grid -o . --apply-settings-map  # 2nd pass: grid uses current map from settings
plotter surface-cal sample -o bed.json  # First pass: levels start at 0; each cell +/-1 step (delta_z mm)
plotter surface-cal sample -o bed.json -i bed.json  # Refine: add another step on top of saved levels
plotter check drawing.svg       # Check SVG dimensions
plotter list                    # List paper sizes
plotter general                 # Show machine settings
plotter manage-papers           # Edit paper sizes interactively
plotter generate-boundary       # Generate boundary G-code
plotter calibrate               # Legacy test spiral (vpype); prefer surface-cal for bed maps
```
