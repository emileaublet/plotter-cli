# Copilot Instructions for Plotter CLI

This repository contains `plotter-cli`, a Python command-line tool wrapping `vpype` for a specific pen plotter setup, with a native desktop GUI (Plotter Studio) for visual arrangement of multiple SVGs.

## Project Structure

- **`plotter_cli/commands.py`**: Main entry point using `typer`. Contains all CLI commands (`process`, `check`, `calibrate`, `studio`, etc.).
- **`plotter_cli/utils.py`**: Shared utilities, settings loading, SVG parsing, G-code generation logic, and statistics calculation.
- **`plotter_cli/gui_app.py`**: Flask backend API for Plotter Studio GUI. Handles SVG/paper management, export, and window control API.
- **`plotter_cli/gui_utils.py`**: GUI-specific utilities: SVG to PNG conversion, combined SVG generation, G-code processing, guide G-code generation.
- **`plotter_cli/gcode_parser.py`**: G-code parsing and optimization (Z-axis movement optimization).
- **`plotter_cli/gui/templates/index.html`**: Main HTML template for the GUI.
- **`plotter_cli/gui/static/app.js`**: Frontend JavaScript for canvas rendering, interactions, and API calls.
- **`plotter_cli/gui/static/style.css`**: Stylesheet with dark theme (Midnight Precision).
- **`settings.yaml`**: Configuration for machine dimensions, papers, and feed rates.
- **`.vpype.toml`**: `vpype` configuration template (dynamically updated during `process`).

## Development Guidelines

### 1. Installation & Execution

- **Avoid Global Install**: Do not rely on `pip install .` or a global `plotter` command for testing.
- **Use Venv**: When running commands or verifying fixes, always use the virtual environment executable:
  ```bash
  ./.venv/bin/plotter [command]
  ```
- **Editable Mode**: Ensure changes are tested on an editable install (`pip install -e .`).

### 2. Machine Configuration

- **Hardcoded Defaults**: The `settings.yaml` is the primary source of truth, BUT `utils.py` and `commands.py` contain fallback dicts/values.
  - **Critical**: When updating machine dimensions (e.g., Area Width/Height), update **ALL** locations:
    1. `plotter_cli/settings.yaml`
    2. `plotter_cli/utils.py` (Default dict in `load_settings`)
    3. `plotter_cli/utils.py` (Default kwargs in `update_vpype_config_with_z_settings`)
    4. `plotter_cli/commands.py` (Default `get` values in `process`)

### 3. Vpype Integration

- **Layout Orientation**: The plotter often runs in landscape (Width > Height). `vpype layout` defaults to portrait.
  - **Rule**: Always include `--landscape` in `vpype layout` commands if the machine area is landscape (currently 880x470mm).
- **Units**: `vpype` commands (like `rect`) default to pixels if no unit is specified. Always append `mm` to dimensions (e.g., `rect ... {w}mm {h}mm`).
- **Centering**: To center artwork correctly on the bed:
  1. `scaleto` (resize art)
  2. `layout --landscape ...` (center paper on bed)

### 4. GUI Development (Plotter Studio)

- **Backend API**: All GUI interactions go through Flask routes in `gui_app.py`
- **Frontend**: Uses vanilla JavaScript (no frameworks) with Lucide icons
- **State Management**: In-memory stores (`svg_library`, `paper_store`) - consider database for production
- **Window Control**: For frameless windows, use `WindowControlAPI` class exposed via `js_api`
- **Modals**: Use `showAlert()` and `showConfirm()` helper functions instead of browser `alert()`/`confirm()`
- **Icons**: All icons use Lucide - call `lucide.createIcons()` after DOM updates
- **Styling**: Follow the Midnight Precision theme (dark mode, cyan accents)

### 5. Code Style

- Use `typer` for new CLI commands.
- Use `rich` for CLI output formatting (panels, progress bars).
- Prefer modifying `utils.py` or `gui_utils.py` for logic reuse rather than duplicating code.
- For GUI: Use modern JavaScript (async/await, Promises), maintain consistent naming conventions.
