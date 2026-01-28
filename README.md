# Plotter CLI

This project provides a command-line interface (CLI) and web-based GUI (Plotter Studio) for processing SVG files for plotting, managing paper sizes, and generating calibration files. It wraps `vpype` to provide a machine-specific pipeline.

The GUI allows you to visually arrange multiple SVGs on a canvas, transform them (move, scale, rotate), and export to G-code with paper placement guides.

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

## Usage

Run the CLI with the following command:
```bash
plotter [OPTIONS] COMMAND [ARGS]
```

### Key Commands

- **`studio`**: Launch the Plotter Studio GUI for visual arrangement of multiple SVGs.
  - usage: `plotter studio`
  - options:
    - `--host` / `-h`: Host to bind the server to (default: 127.0.0.1)
    - `--port` / `-p`: Port to bind the server to (default: 5000)
    - `--debug`: Enable debug mode
  - Opens a web-based interface where you can:
    - Add multiple SVG files to a canvas
    - Move, scale, and rotate SVGs visually
    - Arrange SVGs on a canvas matching your plotter area (880mm × 470mm)
    - Export to combined SVG and G-code files
    - Generate a guide G-code file with paper boundaries for placement
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
2. **Open in browser**: Navigate to `http://127.0.0.1:5000`
3. **Add SVGs**: Click "Choose SVG File" to add SVG files to the canvas
4. **Arrange SVGs**:
   - Click an SVG to select it
   - Drag to move, use corner handles to scale, use top handle to rotate
   - Use the transform panel for precise numeric control
5. **Export**: Click "Export" to generate:
   - Combined SVG with all arranged elements
   - G-code files (one per color layer)
   - Guide G-code file with paper boundaries for placement

The guide G-code file contains rectangles marking where each paper should be placed. Print this first, place your papers, then print the color layers one by one.

## Contributing

Feel free to submit issues or pull requests to improve the project.
