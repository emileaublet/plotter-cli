import os
import subprocess
import typer
import questionary
import importlib.resources
from .utils import load_settings, get_svg_dimensions, generate_boundary_gcode
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("list")
def list_paper_sizes(
    imperial: bool = typer.Option(
        False, "--imperial", "-i", help="Use imperial units (in) instead of metric (mm)"
    )
):
    """List available paper sizes."""
    settings = load_settings()
    conversion_factor = 25.4 if imperial else 1
    unit = "in" if imperial else "mm"

    print("\nAvailable paper sizes:\n")
    for paper in settings["papers"]:
        print(
            f"- {paper['name']} ({paper['width'] / conversion_factor:.2f}{unit} x {paper['height'] / conversion_factor:.2f}{unit})"
        )
    print()


@app.command("general")
def show_general_settings(
    imperial: bool = typer.Option(
        False, "--imperial", "-i", help="Use imperial units (in) instead of metric (mm)"
    )
):
    """Show general settings."""
    settings = load_settings()
    conversion_factor = 25.4 if imperial else 1
    unit = "in" if imperial else "mm"

    general = settings["general"]
    print("\nGeneral settings:\n")
    print(f"- Area width: {general['area_width'] / conversion_factor:.2f}{unit}")
    print(f"- Area height: {general['area_height'] / conversion_factor:.2f}{unit}\n")


@app.command()
def check(
    svg_file: str = typer.Argument(..., help="Path to the SVG file"),
    imperial: bool = typer.Option(
        False, "--imperial", "-i", help="Use imperial units (in) instead of metric (mm)"
    ),
):
    """Check SVG dimensions against paper sizes."""
    check_svg(svg_file, imperial)


def check_svg(
    svg_file: str,
    imperial: bool = typer.Option(
        False, "--imperial", "-i", help="Use imperial units (in) instead of metric (mm)"
    ),
):
    """Check SVG dimensions against paper sizes."""
    settings = load_settings()
    svg_width, svg_height = get_svg_dimensions(svg_file)
    svg_ratio = svg_width / svg_height

    # Conversion factor for mm to inches
    conversion_factor = 25.4 if imperial else 1
    unit = "in" if imperial else "mm"

    matching_papers = []
    for paper in settings["papers"]:
        paper_ratio = paper["width"] / paper["height"]
        if abs(svg_ratio - paper_ratio) < 1e-6:  # Allow for floating-point precision
            matching_papers.append(paper)

    if matching_papers:
        options = [
            f"{paper['name']} ({paper['width'] / conversion_factor:.2f}{unit} x {paper['height'] / conversion_factor:.2f}{unit})"
            for paper in matching_papers
        ]
        options.append("Custom")

        choice = questionary.select("\nSelect a paper size:", choices=options).ask()

        if choice == "Custom":
            custom_width = (
                typer.prompt(
                    f"Enter custom width in {unit} (default {svg_width / conversion_factor:.2f}{unit})",
                    default=svg_width / conversion_factor,
                    type=float,
                )
                * conversion_factor
            )
            calculated_height = custom_width / svg_ratio
            custom_height = (
                typer.prompt(
                    f"Enter custom height in {unit} (default {calculated_height / conversion_factor:.2f}{unit})",
                    default=calculated_height / conversion_factor,
                    type=float,
                )
                * conversion_factor
            )
        else:
            selected_paper = matching_papers[options.index(choice)]
            custom_width = selected_paper["width"]
            custom_height = selected_paper["height"]
    else:
        print("\nNo matching paper sizes found. Using custom dimensions.\n")
        custom_width = (
            typer.prompt(
                f"Enter custom width in {unit} (default {svg_width / conversion_factor:.2f}{unit})",
                default=svg_width / conversion_factor,
                type=float,
            )
            * conversion_factor
        )
        custom_height = (
            typer.prompt(
                f"Enter custom height in {unit} (default {svg_height / conversion_factor:.2f}{unit})",
                default=svg_height / conversion_factor,
                type=float,
            )
            * conversion_factor
        )

    area_width = settings["general"]["area_width"]
    area_height = settings["general"]["area_height"]

    while custom_width > area_width or custom_height > area_height:
        error_message = (
            f"[ERROR] Selected dimensions exceed the allowed area dimensions!\n\n"
            f"Allowed area dimensions: {area_width / conversion_factor:.2f}{unit} x {area_height / conversion_factor:.2f}{unit}\n"
            f"Your dimensions: {custom_width / conversion_factor:.2f}{unit} x {custom_height / conversion_factor:.2f}{unit}"
        )
        console.print(Panel(error_message, title="Dimension Error", style="bold red"))

        custom_width = (
            typer.prompt(
                f"Enter custom width in {unit} (default {svg_width / conversion_factor:.2f}{unit}):",
                default=svg_width / conversion_factor,
                type=float,
            )
            * conversion_factor
        )
        custom_height = (
            typer.prompt(
                f"Enter custom height in {unit} (default {svg_height / conversion_factor:.2f}{unit}):",
                default=svg_height / conversion_factor,
                type=float,
            )
            * conversion_factor
        )

    print(
        f"\nFinal dimensions: {custom_width / conversion_factor:.2f}{unit} x {custom_height / conversion_factor:.2f}{unit}\n"
    )


@app.command("process")
def process(
    svg_file: str = typer.Argument(..., help="Path to the SVG file"),
    imperial: bool = typer.Option(
        False, "--imperial", "-i", help="Use imperial units (in) instead of metric (mm)"
    ),
):
    """Process an SVG file for plotting."""
    # Validate file extension
    if not svg_file.lower().endswith(".svg"):
        console.print(Panel("[ERROR] The file must be an SVG.", style="bold red"))
        raise typer.Exit(code=1)

    # Run the check command to get paper size
    settings = load_settings()
    svg_width, svg_height = get_svg_dimensions(svg_file)
    svg_ratio = svg_width / svg_height

    conversion_factor = 25.4 if imperial else 1
    unit = "in" if imperial else "mm"

    matching_papers = []
    for paper in settings["papers"]:
        paper_ratio = paper["width"] / paper["height"]
        if abs(svg_ratio - paper_ratio) < 1e-6:
            matching_papers.append(paper)

    if matching_papers:
        options = [
            f"{paper['name']} ({paper['width'] / conversion_factor:.2f}{unit} x {paper['height'] / conversion_factor:.2f}{unit})"
            for paper in matching_papers
        ]
        options.append("Custom")

        choice = questionary.select("\nSelect a paper size:", choices=options).ask()

        if choice == "Custom":
            custom_width = (
                typer.prompt(
                    f"Enter custom width in {unit} (default {svg_width / conversion_factor:.2f}{unit})",
                    default=svg_width / conversion_factor,
                    type=float,
                )
                * conversion_factor
            )
            calculated_height = custom_width / svg_ratio
            custom_height = (
                typer.prompt(
                    f"Enter custom height in {unit} (default {calculated_height / conversion_factor:.2f}{unit})",
                    default=calculated_height / conversion_factor,
                    type=float,
                )
                * conversion_factor
            )
        else:
            selected_paper = matching_papers[options.index(choice)]
            custom_width = selected_paper["width"]
            custom_height = selected_paper["height"]
    else:
        console.print(
            Panel(
                "[ERROR] No matching paper sizes found. Please specify dimensions manually.",
                style="bold red",
            )
        )

        custom_width = (
            typer.prompt(
                f"Enter custom width in {unit} (default {svg_width / conversion_factor:.2f}{unit})",
                default=svg_width / conversion_factor,
                type=float,
            )
            * conversion_factor
        )
        calculated_height = custom_width / svg_ratio
        custom_height = (
            typer.prompt(
                f"Enter custom height in {unit} (default {calculated_height / conversion_factor:.2f}{unit})",
                default=calculated_height / conversion_factor,
                type=float,
            )
            * conversion_factor
        )

    area_width = settings["general"]["area_width"]
    area_height = settings["general"]["area_height"]

    # Construct the vpype command
    svg_filename = os.path.basename(svg_file)
    svg_name_without_ext = os.path.splitext(svg_filename)[0]

    # Create a folder for the output files
    output_folder = os.path.join(os.path.dirname(svg_file), svg_name_without_ext)
    os.makedirs(output_folder, exist_ok=True)

    output_path = os.path.join(
        output_folder, f"{svg_name_without_ext}_%_color or _lid%.gcode"
    )

    # Dynamically locate the .vpype.toml file
    with importlib.resources.path("plotter_cli", ".vpype.toml") as toml_path:
        vpype_command = (
            f"vpype -c {toml_path} read --attr stroke {svg_file} rect -l 999 0 0 {svg_width} {svg_height} "
            f"scaleto {custom_width}{unit} {custom_height}{unit} layout {area_width}{unit}x{area_height}{unit} "
            f"ldelete 999 forlayer linemerge linesort --two-opt --passes 2000 "
            f'gwrite -p penplotte "{output_path}" end'
        )

    # Execute the vpype command
    try:
        subprocess.run(vpype_command, shell=True, check=True)

        # List all generated files in the output folder
        generated_files = os.listdir(output_folder)
        file_list = "\n".join([f"- {file}" for file in generated_files])

        console.print(
            Panel(
                f"[SUCCESS] Files processed and saved to: \n{file_list}",
                style="bold green",
            )
        )
    except subprocess.CalledProcessError as e:
        console.print(
            Panel(f"[ERROR] Failed to execute vpype command: {e}", style="bold red")
        )
        raise typer.Exit(code=1)


@app.command("manage-papers")
def manage_papers(
    imperial: bool = typer.Option(
        False, "--imperial", "-i", help="Use imperial units (in) instead of metric (mm)"
    ),
):
    """Add, edit, or remove paper sizes."""
    settings = load_settings()
    conversion_factor = 25.4 if imperial else 1
    unit = "in" if imperial else "mm"

    action = questionary.select(
        "What would you like to do?",
        choices=["Add Paper", "Edit Paper", "Remove Paper", "Cancel"],
    ).ask()

    if action == "Add Paper":
        name = typer.prompt("Enter the name of the new paper size")
        width = (
            typer.prompt(f"Enter the width (in {unit})", type=float) * conversion_factor
        )
        height = (
            typer.prompt(f"Enter the height (in {unit})", type=float)
            * conversion_factor
        )
        settings["papers"].append({"name": name, "width": width, "height": height})
        console.print(
            Panel(f"[SUCCESS] Paper size '{name}' added.", style="bold green")
        )

    elif action == "Edit Paper":
        paper_names = [paper["name"] for paper in settings["papers"]]
        selected_paper = questionary.select(
            "Select a paper to edit:", choices=paper_names
        ).ask()
        if selected_paper:
            paper = next(p for p in settings["papers"] if p["name"] == selected_paper)
            paper["width"] = (
                typer.prompt(
                    f"Enter the new width for '{selected_paper}' (current: {paper['width'] / conversion_factor:.2f}{unit})",
                    default=paper["width"] / conversion_factor,
                    type=float,
                )
                * conversion_factor
            )
            paper["height"] = (
                typer.prompt(
                    f"Enter the new height for '{selected_paper}' (current: {paper['height'] / conversion_factor:.2f}{unit})",
                    default=paper["height"] / conversion_factor,
                    type=float,
                )
                * conversion_factor
            )
            console.print(
                Panel(
                    f"[SUCCESS] Paper size '{selected_paper}' updated.",
                    style="bold green",
                )
            )

    elif action == "Remove Paper":
        paper_names = [paper["name"] for paper in settings["papers"]]
        selected_paper = questionary.select(
            "Select a paper to remove:", choices=paper_names
        ).ask()
        if selected_paper:
            settings["papers"] = [
                p for p in settings["papers"] if p["name"] != selected_paper
            ]
            console.print(
                Panel(
                    f"[SUCCESS] Paper size '{selected_paper}' removed.",
                    style="bold green",
                )
            )

    # Save the updated settings
    with open("settings.yaml", "w") as f:
        import yaml

        yaml.dump(settings, f)

    console.print(Panel("[INFO] Changes saved to settings.yaml.", style="bold blue"))


@app.command("generate-boundary")
def generate_boundary(
    output: str = typer.Option(
        None, "--output", "-o", help="Destination folder to save the G-code file"
    )
):
    """
    Generate G-code to draw boundaries for a selected paper size or custom dimensions.
    """
    settings = load_settings()

    # Get area dimensions from settings
    area_width = settings["general"]["area_width"]
    area_height = settings["general"]["area_height"]

    # Prompt user to select paper size or custom dimensions
    options = [
        f"{paper['name']} ({paper['width']}mm x {paper['height']}mm)"
        for paper in settings["papers"]
    ]
    options.append("Custom")

    choice = questionary.select("Select a paper size:", choices=options).ask()

    if choice == "Custom":
        paper_width = typer.prompt("Enter custom width in mm", type=float)
        paper_height = typer.prompt("Enter custom height in mm", type=float)
    else:
        selected_paper = next(
            paper
            for paper in settings["papers"]
            if f"{paper['name']} ({paper['width']}mm x {paper['height']}mm)" == choice
        )
        paper_width = selected_paper["width"]
        paper_height = selected_paper["height"]

    gcode_filename = f"boundary_{paper_width}x{paper_height}.gcode"

    if output:
        # Expand ~ and resolve relative paths
        output = os.path.abspath(os.path.expanduser(output))

        os.makedirs(output, exist_ok=True)
        gcode_path = os.path.join(output, gcode_filename)
    else:
        gcode_path = gcode_filename

    # Dynamically locate the .vpype.toml file
    with importlib.resources.path("plotter_cli", ".vpype.toml") as toml_path:
        vpype_command = (
            f"vpype -c {toml_path} rect 0 0 {paper_width}mm {paper_height}mm "
            f"layout {area_width}mmx{area_height}mm linemerge linesort --two-opt --passes 2000 "
            f"gwrite -p penplotte {gcode_path}"
        )

    # Set a valid working directory
    os.chdir("/Users/emileaublet/Dev")

    # Execute the vpype command
    try:
        subprocess.run(vpype_command, shell=True, check=True)

        # Validate file creation
        files_created = []
        if os.path.exists(gcode_path):
            files_created.append(f"G-code file: {os.path.abspath(gcode_path)}")

        if files_created:
            console.print(
                Panel(
                    f"[SUCCESS] Files successfully created:\n"
                    + "\n".join(files_created),
                    style="bold green",
                )
            )
        else:
            console.print(
                Panel(
                    "[ERROR] No files were created. Please check the command execution.",
                    style="bold red",
                )
            )
    except subprocess.CalledProcessError as e:
        console.print(
            Panel(f"[ERROR] Failed to execute vpype command: {e}", style="bold red")
        )
        raise typer.Exit(code=1)


@app.command("calibrate")
def calibrate(
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Destination folder to save the calibration G-code file",
    )
):
    """
    Generate G-code to draw a grid of spaced crosses for calibration purposes.
    """
    settings = load_settings()

    # Get area dimensions from settings
    area_width = settings["general"]["area_width"]
    area_height = settings["general"]["area_height"]

    # Prompt user to select paper size or custom dimensions
    options = [
        f"{paper['name']} ({paper['width']}mm x {paper['height']}mm)"
        for paper in settings["papers"]
    ]
    options.append("Custom")

    choice = questionary.select("Select a paper size:", choices=options).ask()

    if choice == "Custom":
        paper_width = typer.prompt("Enter custom width in mm", type=float)
        paper_height = typer.prompt("Enter custom height in mm", type=float)
    else:
        selected_paper = next(
            paper
            for paper in settings["papers"]
            if f"{paper['name']} ({paper['width']}mm x {paper['height']}mm)" == choice
        )
        paper_width = selected_paper["width"]
        paper_height = selected_paper["height"]

    gcode_filename = f"calibration_grid_{paper_width}x{paper_height}.gcode"

    if output:
        # Expand ~ and resolve relative paths
        output = os.path.abspath(os.path.expanduser(output))

        os.makedirs(output, exist_ok=True)
        gcode_path = os.path.join(output, gcode_filename)
    else:
        gcode_path = gcode_filename

    cellsize = 40
    columns = int(paper_width // cellsize)
    rows = int(paper_height // cellsize)
    column_width = paper_width / columns
    row_height = paper_height / rows

    line_length = cellsize / 2
    horizontal_start = (column_width - line_length) / 2
    vertical_start = (row_height - line_length) / 2
    horizontal_end = horizontal_start + line_length
    vertical_end = vertical_start + line_length
    # Dynamically locate the .vpype.toml file
    with importlib.resources.path("plotter_cli", ".vpype.toml") as toml_path:
        vpype_command = (
            f"vpype -c {toml_path} "
            f"grid -o {column_width}mm {row_height}mm {columns} {rows} line {horizontal_start}mm {column_width/2}mm {horizontal_end}mm {column_width/2}mm end "
            f"grid -o {column_width}mm {row_height}mm {columns} {rows} line {row_height/2}mm {vertical_start}mm {row_height/2}mm {vertical_end}mm end "
            f"layout {area_width}mmx{area_height}mm linemerge linesort --two-opt --passes 2000 "
            f"gwrite -p penplotte {gcode_path}"
        )

    # Set a valid working directory
    os.chdir("/Users/emileaublet/Dev")

    # Execute the vpype command
    try:
        subprocess.run(vpype_command, shell=True, check=True)

        # Validate file creation
        files_created = []
        if os.path.exists(gcode_path):
            files_created.append(f"G-code file: {os.path.abspath(gcode_path)}")

        if files_created:
            console.print(
                Panel(
                    f"[SUCCESS] Calibration grid successfully created:\n"
                    + "\n".join(files_created),
                    style="bold green",
                )
            )
        else:
            console.print(
                Panel(
                    "[ERROR] No files were created. Please check the command execution.",
                    style="bold red",
                )
            )
    except subprocess.CalledProcessError as e:
        console.print(
            Panel(f"[ERROR] Failed to execute vpype command: {e}", style="bold red")
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app(prog_name="plotter")
