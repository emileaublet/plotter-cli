# VPype Utils

This project provides a set of utilities for managing SVG files and paper sizes using a command-line interface (CLI).

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd vpype-utils
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the CLI with the following command:
```bash
python -m plotter [OPTIONS] COMMAND [ARGS]
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
python -m plotter --file path/to/your/file.svg
```

## Contributing

Feel free to submit issues or pull requests to improve the project.
