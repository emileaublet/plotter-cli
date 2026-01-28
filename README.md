# Plotter CLI

This project provides a command-line interface (CLI) for processing SVG files for plotting, managing paper sizes, and generating calibration files. It wraps `vpype` to provide a machine-specific pipeline.

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

## Contributing

Feel free to submit issues or pull requests to improve the project.
