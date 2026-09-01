# Plotter CLI

A command-line tool and native desktop GUI (**Plotter Studio**) for processing SVG files for pen plotters. Wraps `vpype` for path optimization and G-code generation.

Plotter Studio is a paper-like desktop application for visually arranging multiple SVGs on a canvas, transforming them (move, scale, rotate), and exporting to G-code with paper placement guides and detailed statistics.

## Installation

This tool is installed globally via **pipx**:

```bash
pipx install .
```

To apply code changes after editing:

```bash
pipx install . --force
```

Verify:

```bash
plotter --help
```

> `vpype` must be installed separately — it is not included in `pyproject.toml`.

## Configuration

The tool uses a `settings.yaml` file to define machine dimensions, feed rates, and paper sizes. It looks for this file in the following order:

1. Current working directory (`./settings.yaml`)
2. Package installation directory (`plotter_cli/settings.yaml`)
3. Hardcoded defaults

### Machine Settings

- **Area**: 880mm × 470mm
- **Units**: Metric (mm)
- **Feed Rates**: Configurable draw, travel, and Z-axis feed rates

### Paper Sizes

- Predefined paper sizes (A4, Letter, etc.) can be managed via `plotter manage-papers`
- Custom paper sizes can be added directly in Plotter Studio
- Papers can be specified in millimeters (whole numbers) or inches (decimals)

## Usage

```bash
plotter [OPTIONS] COMMAND [ARGS]
```

### Commands

| Command | Description |
|---------|-------------|
| `studio` | Launch Plotter Studio GUI |
| `process <file.svg>` | Prepare an SVG for plotting (scale, center, optimize) |
| `check <file.svg>` | Verify if an SVG fits within a paper size |
| `list` | List all configured paper sizes |
| `general` | Show current machine settings |
| `generate-boundary` | Generate G-code to draw the boundary of a paper size |
| `calibrate` | Generate a calibration spiral pattern |
| `manage-papers` | Interactive wizard to add/edit/remove paper presets |

### `studio` options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` / `-h` | `127.0.0.1` | Host to bind the server to |
| `--port` / `-p` | `5000` | Port to bind the server to |
| `--debug` | off | Enable Flask debug mode |
| `--native` / `--browser` | native | Open in native window or browser |
| `--frameless` / `--titlebar` | frameless | Frameless or standard title bar |
| `--vibrancy` / `--no-vibrancy` | vibrancy | macOS vibrancy effect (macOS only) |

### `process` options

| Option | Description |
|--------|-------------|
| `--no-flip` | Disable path flipping optimization |
| `--imperial` / `-i` | Use inches for output prompts |

## Plotter Studio Workflow

### 1. Launch

```bash
plotter studio
```

Opens a native desktop window in frameless mode with macOS vibrancy. To use the browser instead:

```bash
plotter studio --browser
```

### 2. Add SVGs

Click **"Choose SVG File"** in the SVG Library panel to upload one or more SVG files.

### 3. Add Papers

Click **"Add Paper"** to add a paper to the canvas. Choose from preset sizes or select **"Custom Size..."** for custom dimensions (mm or inches).

### 4. Assign SVGs to Papers

Select a paper on the canvas, then pick an SVG from the library in the Inspector panel to assign it.

### 5. Arrange Papers

**Select Tool (V)**:
- Click to select a paper; Shift-click to add to selection (multi-select)
- Drag to move; drag corner handles to scale; drag top handle to rotate
- Use the Inspector panel for precise numeric control (position, scale, rotation)
- Lock a paper to prevent accidental moves

**Pan Tool (H)**: Click and drag to pan the canvas.

**Alignment Tools** (sidebar): Align or distribute multiple selected papers — left, right, top, bottom, center horizontally/vertically, distribute horizontally/vertically.

**Snap to Grid**: Toggle 10mm grid snapping from the toolbar.

**Auto-Arrange**: Click **"Arrange"** to automatically lay out all papers in a grid.

### 6. Undo / Redo

- **Undo**: `Cmd+Z` (macOS) / `Ctrl+Z`
- **Redo**: `Cmd+Shift+Z` / `Ctrl+Y`
- Up to 50 undo steps are kept.

### 7. Export

Click **"Export"** to generate output files. You'll be prompted to select an output folder (or leave empty for a temp folder).

If any papers are outside the canvas boundaries, you'll receive a warning before export.

**Export generates:**
- Combined SVG with all arranged elements
- G-code files — one per color layer, named `file#RRGGBB_colorname.gcode`
- Guide G-code with paper boundary rectangles (for paper placement)
- `stats.txt` with detailed statistics:
  - Operations summary (papers, SVGs, transformations)
  - Distance statistics by color (travel, draw, total — human-readable)
  - Pen operations (pen lifts, segments, average segment length)
  - Estimated completion time per color and total

Print the guide G-code first, place your papers, then print color layers one by one.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `V` | Select tool |
| `H` | Pan tool |
| `Space` | Toggle pan tool (hold) |
| `Esc` | Return to Select tool |
| `Delete` / `Backspace` | Delete selected paper(s) |
| `Cmd+D` / `Ctrl+D` | Duplicate selected paper |
| `Cmd+Z` / `Ctrl+Z` | Undo |
| `Cmd+Shift+Z` / `Ctrl+Y` | Redo |
| `Arrow keys` | Nudge selected paper (1mm; +Shift = 10mm) |
| `?` | Show keyboard shortcut help |

## Features

### Plotter Studio GUI

- **Native Desktop App**: Runs as a native window via pywebview (or in browser)
- **Paper-like Theme**: A light, neutral workspace with rounded glass panels inspired by sketch-2
- **Frameless Mode**: Borderless window with macOS vibrancy effect and custom traffic-light controls
- **Canvas Tools**: Select, Pan, Zoom, Fullscreen
- **Multi-select**: Shift-click to select multiple papers; move or align them together
- **Alignment Tools**: Align left/right/top/bottom, center H/V, distribute H/V
- **Snap to Grid**: 10mm grid snapping with visual grid overlay
- **Undo/Redo**: 50-step history for paper position and state changes
- **Lock/Unlock**: Lock individual papers to prevent accidental edits
- **Auto-arrange**: Automatic grid layout for all papers
- **Export**: Combined SVG, per-color G-code, guide G-code, and `stats.txt`
- **PNG Preview Caching**: SVG previews are generated once and cached for performance
- **Toast Notifications**: Non-blocking status feedback
- **Custom Modals**: No browser alerts — all dialogs are styled to match the theme
- **Lucide Icons**: Consistent icon system throughout

### CLI

- `process`: Scale, center, and optimize an SVG for plotting via vpype
- `check`: Verify SVG fits a paper size
- `generate-boundary`: G-code border trace for paper placement
- `calibrate`: Spiral calibration pattern
- `manage-papers`: Interactive paper preset editor

## Requirements

- Python 3.8+
- `vpype` (installed separately)
- Dependencies in `pyproject.toml`:
  - `typer`, `questionary`, `rich` — CLI
  - `flask`, `pywebview` — GUI
  - `pyyaml` — configuration
  - `cairosvg`, `pillow` — SVG processing

## Troubleshooting

### Native Window Not Opening

- Ensure `pywebview` is installed: `pip install pywebview`
- Try browser mode: `plotter studio --browser`
- Check console output for error messages

### macOS App Icon

When launched from the CLI, macOS shows the Python icon. This is a macOS limitation for CLI-launched scripts. Building a proper `.app` bundle is not currently supported.

### Export Issues

- **Papers outside canvas**: Adjust paper positions to be fully within the canvas before exporting.
- **Export cancelled**: If you cancel folder selection, the export aborts and resets automatically.
- **vpype errors**: The CLI will print vpype's stderr output to help diagnose failures.

### Canvas Navigation

- **Reset view**: Click the zoom percentage (e.g., "100%") to reset zoom and pan
- **Pan stuck**: Press `Esc` to return to Select tool

## Contributing

Feel free to submit issues or pull requests.
