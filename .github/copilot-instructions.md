# Copilot Instructions for Plotter CLI

This repository contains `plotter-cli`, a Python CLI and native desktop GUI (**Plotter Studio**) for processing SVG files for a specific pen plotter setup. It wraps `vpype` for path optimization and G-code generation.

## Project Structure

| File | Purpose |
|------|---------|
| `plotter_cli/commands.py` | CLI entry point (Typer). All CLI commands: `process`, `check`, `calibrate`, `studio`, etc. |
| `plotter_cli/utils.py` | Shared utilities: settings loading, SVG parsing, G-code generation, statistics, unit formatting |
| `plotter_cli/gui_app.py` | Flask backend API for Plotter Studio. In-memory state, all API routes, export pipeline |
| `plotter_cli/gui_utils.py` | GUI-specific utilities: SVG→PNG preview, combined SVG generation, G-code processing, guide G-code |
| `plotter_cli/gcode_parser.py` | G-code parsing and Z-axis movement optimization |
| `plotter_cli/gui/templates/index.html` | Main HTML template for Plotter Studio |
| `plotter_cli/gui/static/app.js` | Frontend JavaScript (vanilla, no frameworks): canvas rendering, interactions, API calls |
| `plotter_cli/gui/static/style.css` | Dark theme stylesheet (Midnight Precision — dark mode, cyan accents) |
| `plotter_cli/settings.yaml` | Machine config: dimensions, feed rates, paper sizes |
| `plotter_cli/.vpype.toml` | vpype G-code template (dynamically updated during `process`) |

## Installation & Execution

This tool is installed globally via **pipx**. Always use this to apply code changes:

```bash
pipx install . --force
```

Do **not** use `pip install -e .` — the active binary is the pipx global install.

Verify:

```bash
plotter --help
```

`vpype` must be installed separately — it is not in `pyproject.toml`.

## Architecture

- **In-memory state**: `svg_library{}` and `paper_store{}` dicts in `gui_app.py` — no persistence between sessions
- **Coordinate system**: GUI uses top-left origin (Y down); plotter uses bottom-left origin (Y up). Conversion: `y_plotter = canvas_height - y_gui - height`
- **Native window**: pywebview wraps Flask; Flask runs in a daemon thread
- **Settings load order**: `./settings.yaml` → `plotter_cli/settings.yaml` → hardcoded defaults

## GUI API Routes

All under `/api/`:

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/settings` | Read current settings |
| PUT | `/api/settings` | Update settings |
| GET | `/api/papers` | List all papers (alias) |
| GET | `/api/list-papers` | List papers with full state |
| GET | `/api/list-svgs` | List SVG library |
| POST | `/api/add-svg` | Upload SVG file |
| GET | `/api/svg-preview/<id>` | Serve cached PNG preview |
| POST | `/api/add-paper` | Add paper to canvas |
| POST | `/api/update-paper` | Move/resize/rotate/lock/assign SVG to paper |
| POST | `/api/clone-paper/<id>` | Duplicate a paper |
| DELETE | `/api/remove-paper/<id>` | Remove a paper |
| DELETE | `/api/remove-svg/<id>` | Remove an SVG and its papers |
| POST | `/api/auto-arrange` | Auto-layout papers in a grid |
| POST | `/api/align-papers` | Align or distribute selected papers |
| POST | `/api/bulk-update-papers` | Update multiple paper positions at once |
| POST | `/api/select-output-folder` | Open native folder picker |
| POST | `/api/export` | Generate combined SVG + G-code output |
| POST | `/api/clear-all` | Remove all papers and SVGs |

## Key utils.py Functions

| Function | Description |
|----------|-------------|
| `load_settings()` | Load settings from file or defaults |
| `save_settings(settings)` | Persist settings to yaml |
| `get_svg_dimensions(file)` | Parse SVG width/height in mm |
| `validate_svg_dimensions(w, h)` | Raise ValueError if dimensions are invalid |
| `format_distance(mm)` | Human-readable distance (e.g. "1.23 m", "456 mm") |
| `format_time(minutes)` | Human-readable duration |
| `calculate_gcode_stats(file)` | Parse G-code file for distance/pen-lift stats |
| `estimate_draw_time(stats, settings)` | Estimate plot time from stats + feed rates |
| `hex_to_color_name(hex)` | Map hex color to human-readable name |

## Development Guidelines

### Machine Configuration

`settings.yaml` is the primary source of truth, but `utils.py` and `commands.py` have fallback defaults. When changing machine dimensions, update **all** locations:

1. `plotter_cli/settings.yaml`
2. `load_settings()` default dict in `utils.py`
3. `update_vpype_config_with_z_settings()` default kwargs in `utils.py`
4. Default `.get()` values in `process` command in `commands.py`

### vpype Integration

- **Orientation**: Always include `--landscape` in `vpype layout` if the machine area is landscape (currently 880×470mm)
- **Units**: `vpype` commands default to pixels without units — always append `mm` (e.g., `rect ... {w}mm {h}mm`)
- **Centering**: `scaleto` to resize, then `layout --landscape ...` to center on bed

### GUI Development

- **Backend**: All GUI interactions go through Flask routes in `gui_app.py`
- **Frontend**: Vanilla JavaScript (no frameworks), Lucide icons
- **State**: In-memory `svg_library` and `paper_store` dicts
- **Multi-select**: `selectedPaperIds` (Set) + `selectedPaperId` for single; Shift-click to add
- **Undo/redo**: `undoStack` / `redoStack` arrays, max 50 steps, snapshotted before mutations
- **Snap-to-grid**: `snapToGrid` boolean; grid = 10mm; applied during drag in `onMouseMove`
- **Alignment**: `POST /api/align-papers` with `action` = `align_left | align_right | align_top | align_bottom | center_h | center_v | distribute_h | distribute_v`
- **Lock**: `paper.locked` boolean — locked papers cannot be moved or deleted
- **PNG previews**: Generated once on upload, path cached in `svg_data["preview_png_path"]`; regenerated on cache miss
- **Modals**: Use `showAlert()` and `showConfirm()` — never browser `alert()`/`confirm()`
- **Toasts**: Use `showToast(message, type, duration)` for non-blocking feedback
- **Icons**: After any DOM update that adds Lucide icons, call `lucide.createIcons({ nodes: [element] })`
- **Styling**: Follow Midnight Precision theme — dark backgrounds, cyan (`var(--accent)`) highlights

### Code Style

- Use `typer` for new CLI commands
- Use `rich` for CLI output (panels, progress bars)
- Prefer extending `utils.py` or `gui_utils.py` for shared logic
- Frontend: use `async/await`, consistent camelCase naming
- Do not add test files — no test framework is configured
