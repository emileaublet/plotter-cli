# Plotter CLI

This project provides a set of utilities for managing SVG files and paper sizes using a command-line interface (CLI).

## Installation

### Option 1: Development Installation (Recommended for development)
Install in editable mode so changes to your code are immediately reflected:
```bash
cd /path/to/plotter-cli
pip install -e .
```

### Option 2: Standard Installation
Install the package globally in your Python environment:
```bash
cd /path/to/plotter-cli
pip install .
```

### Option 3: Install with Dependencies
Install dependencies first, then the package:
```bash
cd /path/to/plotter-cli
pip install -r requirements.txt
pip install .
```

### Option 4: Build and Install as Package
Create distribution packages and install from wheel:
```bash
cd /path/to/plotter-cli
python -m build
pip install dist/plotter-1.0.0-py3-none-any.whl
```

### Verification
To verify the installation worked:
```bash
which plotter
plotter --help
```

After installation, you can use the CLI globally from anywhere:
```bash
plotter list
plotter check your_file.svg
plotter process your_file.svg
plotter generate-boundary -o ~/Desktop
plotter calibrate -o ~/Desktop
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
