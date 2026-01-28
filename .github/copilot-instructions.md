# Copilot Instructions for Plotter CLI

This repository contains `plotter-cli`, a Python command-line tool wrapping `vpype` for a specific pen plotter setup.

## Project Structure

- **`plotter_cli/commands.py`**: Main entry point using `typer`. Contains all CLI commands (`process`, `check`, `calibrate`, etc.).
- **`plotter_cli/utils.py`**: Shared utilities, settings loading, SVG parsing, and G-code generation logic.
- **`settings.yaml`**: configuration for machine dimensions, papers, and feed rates.
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

### 4. Code Style

- Use `typer` for new commands.
- Use `rich` for output formatting (panels, progress bars).
- Prefer modifying `utils.py` for logic reuse rather than duplicating code in `commands.py`.
