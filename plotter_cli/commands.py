import os
import subprocess
import typer
import questionary
import importlib.resources
from pathlib import Path
from .utils import (
    load_settings,
    get_svg_dimensions,
    generate_boundary_gcode,
    update_vpype_config_with_z_settings,
    rename_gcode_with_color_name,
    calculate_gcode_stats,
    format_distance,
    format_time,
    estimate_draw_time,
    hex_to_rich_color,
)
from .gcode_parser import GCodeParser
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)

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

    # 3% tolerance for ratio matching
    ratio_tolerance = 0.03

    matching_papers = []
    for paper in settings["papers"]:
        paper_ratio = paper["width"] / paper["height"]
        # Use relative difference for flexible matching
        relative_diff = abs(svg_ratio - paper_ratio) / max(svg_ratio, paper_ratio)
        if relative_diff < ratio_tolerance:
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
    no_flip: bool = typer.Option(
        False,
        "--no-flip",
        help="Disable path flipping during line sorting (faster but may increase travel)",
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

    # 3% tolerance for ratio matching
    ratio_tolerance = 0.03

    matching_papers = []
    for paper in settings["papers"]:
        paper_ratio = paper["width"] / paper["height"]
        # Use relative difference for flexible matching
        relative_diff = abs(svg_ratio - paper_ratio) / max(svg_ratio, paper_ratio)
        if relative_diff < ratio_tolerance:
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

    output_path = os.path.join(output_folder, f"{svg_name_without_ext}_%_color%.gcode")

    # Dynamically locate the .vpype.toml file and update it with Z settings and feed rates
    z_up = settings["general"].get("z_up_long", 20)
    z_down = settings["general"].get("z_down", 0)
    feed_rate_draw = settings["general"].get("feed_rate_draw", 3000)
    feed_rate_travel = settings["general"].get("feed_rate_travel", 6000)
    feed_rate_z = settings["general"].get("feed_rate_z", 1500)
    area_max_x = settings["general"].get("area_width", 880)
    area_max_y = settings["general"].get("area_height", 470)
    registration_marks_length = settings["general"].get("registration_marks_length", 4)
    temp_config_path = update_vpype_config_with_z_settings(
        z_up_long=z_up,
        z_down=z_down,
        feed_rate_draw=feed_rate_draw,
        feed_rate_travel=feed_rate_travel,
        feed_rate_z=feed_rate_z,
        area_max_x=area_max_x,
        area_max_y=area_max_y,
    )

    try:
        vpype_command = (
            f"vpype -c {temp_config_path} "
            f"read --attr stroke {svg_file} "
            f"rect -l 998 0 0 {svg_width}mm {svg_height}mm "
            f"scaleto {custom_width}{unit} {custom_height}{unit} "
            f"layout --landscape {area_width}mmx{area_height}mm "
            f"ldelete 998 "
            f"forlayer "
            f"lmove all 999 "
            f"linemerge linesort {'--no-flip' if no_flip else '--two-opt --passes 2000'} "
            f"rect {registration_marks_length}mm {registration_marks_length}mm {registration_marks_length}mm {registration_marks_length}mm "
            f"rect {area_width - 2 * registration_marks_length}mm {registration_marks_length}mm {registration_marks_length}mm {registration_marks_length}mm "
            f"rect {registration_marks_length}mm {area_height - 2 * registration_marks_length}mm {registration_marks_length}mm {registration_marks_length}mm "
            f"rect {area_width - 2 * registration_marks_length}mm {area_height - 2 * registration_marks_length}mm {registration_marks_length}mm {registration_marks_length}mm "
            f"lmove 1 1 "
            f"lmove 999 2 "
            f"gwrite -p penplotte {output_path} "
            f"end"
        )

        # Execute the vpype command with progress indication
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Processing SVG with vpype...", total=None)
            subprocess.run(vpype_command, shell=True, check=True, capture_output=True)
            progress.update(task, completed=True)

        console.print("[green]✓[/green] SVG processed with vpype")

        # Post-process all generated G-code files with dynamic Z adjustment
        generated_files = os.listdir(output_folder)
        gcode_files = [f for f in generated_files if f.endswith(".gcode")]

        # Rename gcode files to include color names based on hex codes
        if gcode_files:
            renamed_files = []
            for gcode_file in gcode_files:
                file_path = os.path.join(output_folder, gcode_file)
                new_filename = rename_gcode_with_color_name(file_path)
                renamed_files.append(new_filename)
            gcode_files = renamed_files
            console.print(
                f"[green]✓[/green] Renamed {len(gcode_files)} file(s) with color names"
            )

        if gcode_files:
            # Get Z settings from the settings file
            z_up_long = settings["general"].get("z_up_long", 10.0)
            z_up_short = settings["general"].get("z_up_short", 4.0)
            z_up_threshold = settings["general"].get("z_up_threshold", 1.5)
            z_down = settings["general"].get("z_down", 0.0)
            feed_rate_draw = settings["general"].get("feed_rate_draw", 4000)
            feed_rate_z = settings["general"].get("feed_rate_z", 1500)

            # Initialize the G-code parser with settings values
            parser = GCodeParser(
                long_distance_z=z_up_long,
                short_distance_z=z_up_short,
                short_distance_mm=z_up_threshold,
                z_down=z_down,
                feed_rate_draw=feed_rate_draw,
                feed_rate_z=feed_rate_z,
            )

            # Process each G-code file with progress bar
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
                transient=True,
            ) as progress:
                total_files = len(gcode_files)
                task = progress.add_task(
                    f"[cyan]Optimizing G-code...",
                    total=total_files,
                )

                for idx, gcode_file in enumerate(gcode_files, 1):
                    file_path = Path(output_folder) / gcode_file
                    progress.update(
                        task,
                        description=f"[cyan]Optimizing G-code [{idx}/{total_files}]...",
                    )
                    try:
                        parser.parse_file(file_path)
                        progress.advance(task)
                    except Exception as e:
                        console.print(
                            f"  [red]✗ Failed to process {gcode_file}: {e}[/red]"
                        )
                        progress.advance(task)

            # Show optimization summary
            console.print(
                f"[green]✓[/green] Optimized G-code: "
                f"[dim]Z={z_up_short}/{z_up_long}mm[/dim]"
            )

        # Get feed rates for time estimation
        feed_rate_draw = settings["general"].get("feed_rate_draw", 4000)
        feed_rate_travel = settings["general"].get("feed_rate_travel", 6000)
        feed_rate_z = settings["general"].get("feed_rate_z", 1500)
        z_up = settings["general"].get("z_up_long", 12)
        z_down = settings["general"].get("z_down", 0)

        # Calculate stats for all gcode files
        final_files = sorted(
            [f for f in os.listdir(output_folder) if f.endswith(".gcode")]
        )
        all_stats = []
        total_draw = 0.0
        total_travel = 0.0
        total_segments = 0
        total_pen_lifts = 0

        for f in final_files:
            stats = calculate_gcode_stats(os.path.join(output_folder, f))
            stats["filename"] = f
            # Calculate time for this file
            stats["time_minutes"] = estimate_draw_time(
                stats["draw_distance_mm"],
                stats["travel_distance_mm"],
                stats["num_pen_lifts"],
                feed_rate_draw,
                feed_rate_travel,
                feed_rate_z,
                z_up,
                z_down,
            )
            all_stats.append(stats)
            total_draw += stats["draw_distance_mm"]
            total_travel += stats["travel_distance_mm"]
            total_segments += stats["num_segments"]
            total_pen_lifts += stats["num_pen_lifts"]

        # Calculate total time
        total_time = estimate_draw_time(
            total_draw,
            total_travel,
            total_pen_lifts,
            feed_rate_draw,
            feed_rate_travel,
            feed_rate_z,
            z_up,
            z_down,
        )

        # Create a rich table for the output
        console.print()
        table = Table(
            title=f"[bold]📊 {len(final_files)} file(s) ready[/bold]",
            show_header=True,
            header_style="bold",
            border_style="dim",
            title_justify="left",
        )
        table.add_column("Color", style="bold")
        table.add_column("Draw", justify="right")
        table.add_column("Travel", justify="right", style="dim")
        table.add_column("Total", justify="right")
        table.add_column("Time", justify="right")
        table.add_column("Segments", justify="right", style="dim")
        table.add_column("File", style="dim")

        for stats in all_stats:
            color_name = stats["color_name"] or "unknown"
            hex_code = stats["hex_code"]

            # Style the color name with actual color if available
            if hex_code:
                rich_color = hex_to_rich_color(hex_code)
                color_display = f"[{rich_color}]●[/{rich_color}] {color_name}"
            else:
                color_display = color_name

            total_distance = stats["draw_distance_mm"] + stats["travel_distance_mm"]

            table.add_row(
                color_display,
                format_distance(stats["draw_distance_mm"]),
                format_distance(stats["travel_distance_mm"]),
                format_distance(total_distance),
                format_time(stats["time_minutes"]),
                str(stats["num_segments"]),
                stats["filename"],
            )

        # Add totals row
        table.add_section()
        total_distance_all = total_draw + total_travel
        table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{format_distance(total_draw)}[/bold]",
            format_distance(total_travel),
            f"[bold]{format_distance(total_distance_all)}[/bold]",
            f"[bold]{format_time(total_time)}[/bold]",
            str(total_segments),
            "",
        )

        console.print(table)
        console.print(f"\n[dim]📁 {output_folder}[/dim]")

    except subprocess.CalledProcessError as e:
        console.print(
            Panel(f"[ERROR] Failed to execute vpype command: {e}", style="bold red")
        )
        raise typer.Exit(code=1)
    finally:
        # Clean up temporary config file
        if os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


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

    # Dynamically update the .vpype.toml file with Z settings and feed rates
    z_up = settings["general"].get("z_up_long", 20)
    z_down = settings["general"].get("z_down", 0)
    feed_rate_draw = settings["general"].get("feed_rate_draw", 3000)
    feed_rate_travel = settings["general"].get("feed_rate_travel", 6000)
    feed_rate_z = settings["general"].get("feed_rate_z", 1500)
    temp_config_path = update_vpype_config_with_z_settings(
        z_up_long=z_up,
        z_down=z_down,
        feed_rate_draw=feed_rate_draw,
        feed_rate_travel=feed_rate_travel,
        feed_rate_z=feed_rate_z,
    )

    try:
        vpype_command = (
            f"vpype -c {temp_config_path} rect 0 0 {paper_width}mm {paper_height}mm "
            f"layout --landscape {area_width}mmx{area_height}mm linemerge linesort --two-opt --passes 2000 "
            f"gwrite -p penplotte {gcode_path}"
        )

        # Set a valid working directory
        os.chdir("/Users/emileaublet/Dev")

        # Execute the vpype command
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
    finally:
        # Clean up temporary config file
        if os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


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
    Generate G-code to draw a square spiral for calibration purposes.
    The spiral covers most of the paper surface, leaving a small margin from edges.
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

    gcode_filename = f"calibration_spiral_{paper_width}x{paper_height}.gcode"

    if output:
        # Expand ~ and resolve relative paths
        output = os.path.abspath(os.path.expanduser(output))

        os.makedirs(output, exist_ok=True)
        gcode_path = os.path.join(output, gcode_filename)
    else:
        gcode_path = gcode_filename

    # Create a square spiral that covers most of the surface
    # Leave some margin from edges for safety
    margin = 10  # mm margin from edges
    spiral_width = paper_width - (2 * margin)
    spiral_height = paper_height - (2 * margin)
    spiral_start_x = margin
    spiral_start_y = margin

    # Calculate number of spiral loops based on paper size
    # Each loop goes inward by 5mm
    step_size = 5  # mm between spiral lines
    max_loops = int(min(spiral_width, spiral_height) // (2 * step_size))

    # Dynamically update the .vpype.toml file with Z settings and feed rates
    z_up = settings["general"].get("z_up_long", 20)
    z_down = settings["general"].get("z_down", 0)
    feed_rate_draw = settings["general"].get("feed_rate_draw", 3000)
    feed_rate_travel = settings["general"].get("feed_rate_travel", 6000)
    feed_rate_z = settings["general"].get("feed_rate_z", 1500)
    temp_config_path = update_vpype_config_with_z_settings(
        z_up_long=z_up,
        z_down=z_down,
        feed_rate_draw=feed_rate_draw,
        feed_rate_travel=feed_rate_travel,
        feed_rate_z=feed_rate_z,
    )

    try:
        # Create the square spiral using vpype's rect command with multiple inset rectangles
        spiral_rects = []
        for i in range(max_loops):
            inset = i * step_size
            rect_x = spiral_start_x + inset
            rect_y = spiral_start_y + inset
            rect_width = spiral_width - (2 * inset)
            rect_height = spiral_height - (2 * inset)

            # Only add rectangle if it has positive dimensions
            if rect_width > 0 and rect_height > 0:
                spiral_rects.append(
                    f"rect {rect_x}mm {rect_y}mm {rect_width}mm {rect_height}mm"
                )

        # Join all rectangle commands
        rect_commands = " ".join(spiral_rects)

        vpype_command = (
            f"vpype -c {temp_config_path} "
            f"{rect_commands} "
            f"layout --landscape {area_width}mmx{area_height}mm linemerge linesort --two-opt --passes 2000 "
            f"gwrite -p penplotte {gcode_path}"
        )

        # Set a valid working directory
        os.chdir("/Users/emileaublet/Dev")

        # Execute the vpype command
        subprocess.run(vpype_command, shell=True, check=True)

        # Validate file creation
        files_created = []
        if os.path.exists(gcode_path):
            files_created.append(f"G-code file: {os.path.abspath(gcode_path)}")

        if files_created:
            console.print(
                Panel(
                    f"[SUCCESS] Calibration spiral successfully created:\n"
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
    finally:
        # Clean up temporary config file
        if os.path.exists(temp_config_path):
            os.unlink(temp_config_path)


@app.command("studio")
def studio(
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Host to bind the server to"
    ),
    port: int = typer.Option(
        5000, "--port", "-p", help="Port to bind the server to"
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Enable debug mode"
    ),
):
    """Launch the Plotter Studio GUI."""
    from .gui_app import run_gui

    run_gui(host=host, port=port, debug=debug)


if __name__ == "__main__":
    app(prog_name="plotter")
