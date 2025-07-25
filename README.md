# Plotter CLI

This project provides a set of utilities for managing SVG files and paper sizes using a command-line interface (CLI).

## Installation

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install the CLI tool:
   ```bash
   pip install .
   ```

## Usage

Run the CLI with the following command:
```bash
plotter [OPTIONS] COMMAND [ARGS]
```

### Commands

- `list`: List available paper sizes.
- `general`: Show general settings.
- `check`: Check SVG dimensions against paper sizes.
- `process`: Process an SVG file for plotting.
- `manage-papers`: Add, edit, or remove paper sizes.

### Default Behavior

If no command is specified, the `check` command is executed by default. You can provide an SVG file using the `--file` or `-f` option:
```bash
plotter --file path/to/your/file.svg
```

## Contributing

Feel free to submit issues or pull requests to improve the project.
