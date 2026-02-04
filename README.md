# Plotter CLI

This project provides a command-line interface (CLI) and native desktop GUI (Plotter Studio) for processing SVG files for plotting, managing paper sizes, and generating calibration files. It wraps `vpype` to provide a machine-specific pipeline.

Plotter Studio features a modern, dark-themed interface that runs as a native desktop application (or in a browser). The GUI allows you to visually arrange multiple SVGs on a canvas, transform them (move, scale, rotate), and export to G-code with paper placement guides and detailed statistics.

## Installation

### Recommended: Editable Install (for Development)
Since this tool relies on local configuration (like `settings.yaml`), it is best installed in a virtual environment in editable mode. This ensures changes to the code or settings are immediately reflected.

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install the package in editable mode:
   ```bash
   pip install -e .
   ```

3. Run the plotter:
   ```bash
   plotter --help
   ```

### Global Install (pipx)
If you want to use the tool globally without activating a virtual environment, `pipx` is recommended.

**Fresh Install:**
```bash
pipx install .
```

**Apply Updates:**
If you change the code or settings, you must force a reinstall to see changes:
```bash
pipx install . --force
```

## Configuration

The tool uses a `settings.yaml` file to define machine dimensions, feed rates, and paper sizes. It looks for this file in the following order:
1. Current working directory (`./settings.yaml`)
2. Package installation directory (`plotter_cli/settings.yaml`)
3. Hardcoded defaults

### Default Machine Settings
- **Area**: 880mm x 470mm
- **Units**: Metric (mm)
- **Feed Rates**: Configurable draw, travel, and Z-axis feed rates

### Paper Sizes
- Predefined paper sizes (A4, Letter, etc.) can be managed via `plotter manage-papers`
- Custom paper sizes can be added directly in Plotter Studio GUI
- Papers can be specified in millimeters (whole numbers) or inches (decimals)

## Usage

Run the CLI with the following command:
```bash
plotter [OPTIONS] COMMAND [ARGS]
```

### Key Commands

- **`studio`**: Launch the Plotter Studio GUI for visual arrangement of multiple SVGs.
  - usage: `plotter studio [OPTIONS]`
  - options:
    - `--host` / `-h`: Host to bind the server to (default: 127.0.0.1)
    - `--port` / `-p`: Port to bind the server to (default: 5000)
    - `--debug`: Enable debug mode
    - `--native` / `--browser`: Open in native window (default) or browser
    - `--frameless` / `--titlebar`: Remove title bar for frameless window (default: frameless)
    - `--vibrancy` / `--no-vibrancy`: Enable macOS vibrancy effect (default: enabled, macOS only)
  - Opens a native desktop application (or browser) where you can:
    - Add multiple SVG files to a canvas
    - Add custom-sized papers (in mm or inches)
    - Move, scale, and rotate papers visually with precise controls
    - Arrange papers on a canvas matching your plotter area (880mm × 470mm)
    - Use pan and zoom tools for navigation
    - Export to combined SVG and G-code files
    - Generate a guide G-code file with paper boundaries for placement
    - View detailed export statistics (stats.txt) with distance, pen lifts, and time estimates
- **`process`**: Prepare an SVG for plotting.
  - usage: `plotter process my_drawing.svg`
  - options:
    - `--no-flip`: Disable path flipping optimization (useful for some pens/brushes).
    - `--imperial` / `-i`: Use inches for output prompts.
- **`check`**: Verify if an SVG fits within defined paper sizes.
- **`list`**: List all configured paper sizes.
- **`general`**: Show current machine settings (Area, Feed Rates).
- **`generate-boundary`**: Create a G-code file to draw the boundary of a specific paper size (useful for framing).
- **`calibrate`**: Generate a calibration pattern.
- **`manage-papers`**: Interactive wizard to add/edit/remove paper presets.

### Example Workflow

#### Single SVG Processing

1. **Check dimensions**:
   ```bash
   plotter check drawing.svg
   ```
2. **Process file** (Scaling, centering, and optimizing):
   ```bash
   plotter process drawing.svg
   ```
3. **Verify settings**:
   ```bash
   plotter general
   ```

#### Multiple SVG Arrangement (Studio)

1. **Launch Plotter Studio**:
   ```bash
   plotter studio
   ```
   By default, this opens a native desktop window with frameless mode and macOS vibrancy. To use a browser instead:
   ```bash
   plotter studio --browser
   ```

2. **Add Papers**: 
   - Click "Add Paper" to add a paper to the canvas
   - Choose from preset sizes or select "Custom Size..." for custom dimensions
   - Custom sizes can be specified in millimeters (whole numbers) or inches (decimals)

3. **Add SVGs**: 
   - Click "Choose SVG File" in the SVG Library section
   - Assign SVGs to papers by selecting a paper and choosing an SVG from the library

4. **Arrange Papers**:
   - **Select Tool (V)**: Click a paper to select it, then:
     - Drag to move
     - Use corner handles to scale
     - Use top handle to rotate
     - Use the Inspector panel for precise numeric control (position, scale, rotation)
   - **Pan Tool (H)**: Click and drag to pan the canvas view
   - **Zoom**: Use zoom controls or click the zoom percentage to reset view
   - **Auto-arrange**: Click "Arrange" to automatically arrange all papers

5. **Export**: 
   - Click "Export" to generate files
   - You'll be prompted to select an output folder (or leave empty for temp folder)
   - If any papers are outside the canvas boundaries, you'll receive a warning
   - Export generates:
     - **Combined SVG** with all arranged elements
     - **G-code files** (one per color layer, named with color information)
     - **Guide G-code** file with paper boundaries for placement
     - **stats.txt** file with detailed export statistics:
       - Operations summary (papers, SVGs, transformations)
       - Distance statistics by color (travel, draw, total in mm)
       - Pen operations (pen lifts, segments, average segment length)
       - Estimated time by color and total

6. **Other Features**:
   - **Clear All**: Remove all papers and SVGs (with confirmation)
   - **Delete SVG**: Remove an SVG from the library (removes associated papers with confirmation)
   - **Fullscreen**: Toggle fullscreen mode
   - **Keyboard Shortcuts**:
     - `ESC`: Return to Select tool when Pan tool is active

The guide G-code file contains rectangles marking where each paper should be placed. Print this first, place your papers, then print the color layers one by one.

## Features

### Plotter Studio GUI

- **Native Desktop App**: Runs as a native window using pywebview (or in browser)
- **Modern Dark Theme**: Midnight Precision theme with cyan accents
- **Frameless Mode**: Clean, borderless window with macOS vibrancy effect
- **Custom Title Bar**: macOS-style traffic lights (close, minimize, maximize)
- **Canvas Tools**:
  - Select tool for moving, scaling, and rotating papers
  - Pan tool for navigating large canvases
  - Zoom controls with reset functionality
  - Fullscreen mode
- **Paper Management**:
  - Add preset or custom-sized papers
  - Assign SVGs to papers
  - Visual transformation with numeric controls
  - Auto-arrange multiple papers
- **Export Features**:
  - Combined SVG generation
  - Per-color G-code files
  - Guide G-code with paper boundaries
  - Detailed statistics (stats.txt) including:
    - Distance traveled and drawn per color
    - Pen lift counts
    - Segment counts and averages
    - Estimated completion time
- **User Experience**:
  - Custom modal dialogs (no browser alerts)
  - Canvas boundary warnings
  - Export cancellation support
  - Clear all functionality
  - Lucide icons throughout

### CLI Commands

All commands support `--help` for detailed usage information.

## Requirements

- Python 3.6+
- `vpype` (installed separately)
- Dependencies listed in `pyproject.toml`:
  - typer, questionary, rich (CLI)
  - flask, pywebview (GUI)
  - pyyaml (configuration)
  - cairosvg, pillow (SVG processing)

## Troubleshooting

### Native Window Not Opening

If `plotter studio` fails to open a native window:
- Ensure `pywebview` is installed: `pip install pywebview`
- Try browser mode: `plotter studio --browser`
- Check console output for error messages

### macOS Icon Not Showing

When running via CLI (`plotter studio`), macOS may show the Python icon instead of a custom app icon. This is a macOS limitation for CLI-launched Python scripts. To get a custom icon, you would need to build a proper `.app` bundle (not currently supported).

### Export Issues

- **Papers outside canvas**: You'll receive a warning before export. Adjust paper positions to be fully within the canvas boundaries.
- **Export cancellation**: If you cancel during folder selection, the export process will abort and reset automatically.
- **Missing stats.txt**: Ensure the export completed successfully. Check the output folder for all generated files.

### Canvas Navigation

- **Pan tool stuck**: Press `ESC` to return to Select tool
- **Reset view**: Click the zoom percentage (e.g., "100%") to reset zoom and position
- **Fullscreen**: Use the fullscreen button in the header or press `F11` (browser mode)

## Contributing

Feel free to submit issues or pull requests to improve the project.
