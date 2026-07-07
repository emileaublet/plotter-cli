import os
import shlex
import subprocess
import typer
import questionary
import importlib.resources
from pathlib import Path
from typing import Optional

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
from .surface_calibration import (
    SHAPES,
    HeightMap,
    apply_height_map_if_configured,
    apply_height_map_to_gcode_text,
    build_height_map_dict,
    generate_calibration_grid_gcode,
    grid_dimensions,
    load_height_map_json,
    save_height_map_json,
)
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
    height_map: Optional[str] = typer.Option(
        None,
        "--height-map",
        help="Bed height map JSON (overrides height_map_path in settings)",
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
            f"vpype -c {shlex.quote(temp_config_path)} "
            f"read --attr stroke {shlex.quote(str(svg_file))} "
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
            f"gwrite -p penplotte {shlex.quote(output_path)} "
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

            arc_fitting = settings["general"].get("arc_fitting", False)
            arc_tolerance = settings["general"].get("arc_tolerance", 0.05)
            parser = GCodeParser(
                long_distance_z=z_up_long,
                short_distance_z=z_up_short,
                short_distance_mm=z_up_threshold,
                z_down=z_down,
                feed_rate_draw=feed_rate_draw,
                feed_rate_z=feed_rate_z,
                arc_fitting=arc_fitting,
                arc_tolerance=arc_tolerance,
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

            full_gcode_paths = [
                os.path.join(output_folder, f) for f in gcode_files
            ]
            apply_height_map_if_configured(
                full_gcode_paths,
                settings["general"],
                height_map_path_override=height_map,
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
                f"{stats['num_segments']:,}",
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
            f"{total_segments:,}",
            "",
        )

        console.print(table)
        console.print(f"\n[dim]📁 {output_folder}[/dim]")

    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        error_detail = f"{e}"
        if stderr_output:
            error_detail += f"\n\nVpype output:\n{stderr_output}"
        console.print(
            Panel(f"[ERROR] Failed to execute vpype command: {error_detail}", style="bold red")
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
            f"vpype -c {shlex.quote(temp_config_path)} rect 0 0 {paper_width}mm {paper_height}mm "
            f"layout --landscape {area_width}mmx{area_height}mm linemerge linesort --two-opt --passes 2000 "
            f"gwrite -p penplotte {shlex.quote(gcode_path)}"
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
            f"vpype -c {shlex.quote(temp_config_path)} "
            f"{rect_commands} "
            f"layout --landscape {area_width}mmx{area_height}mm linemerge linesort --two-opt --passes 2000 "
            f"gwrite -p penplotte {shlex.quote(gcode_path)}"
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
    native: bool = typer.Option(
        True, "--native/--browser", help="Open in native window (default) or browser"
    ),
    frameless: bool = typer.Option(
        True, "--frameless/--titlebar", help="Remove title bar (frameless window, default: True)"
    ),
    vibrancy: bool = typer.Option(
        True, "--vibrancy/--no-vibrancy", help="Enable macOS vibrancy effect (macOS only, default: True)"
    ),
):
    """Launch the Plotter Studio GUI."""
    from .gui_app import run_gui

    run_gui(
        host=host,
        port=port,
        debug=debug,
        native_window=native,
        frameless=frameless,
        vibrancy=vibrancy,
    )



surface_cal_app = typer.Typer(
    no_args_is_help=True,
    help="Bed surface height calibration (grid G-code + JSON map).",
)


@surface_cal_app.command("grid")
def surface_cal_grid(
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .gcode file or directory (default: cwd)",
    ),
    spacing: float = typer.Option(30.0, "--spacing", help="Grid spacing (mm)"),
    cross_size: float = typer.Option(4.0, "--cross-size", help="Mark size (mm)"),
    shape: str = typer.Option(
        "cross",
        "--shape",
        help="Mark shape: cross, plus, circle, square, swirl",
    ),
    height_map: Optional[str] = typer.Option(
        None,
        "--height-map",
        help="JSON map: bake offsets into this grid (2nd+ pass). Omit path with --apply-settings-map.",
    ),
    apply_settings_map: bool = typer.Option(
        False,
        "--apply-settings-map",
        help="Use height_map_path from settings with generated grid (after --height-map if both set, height-map wins).",
    ),
):
    """Emit G-code with a mark at each grid point over the machine bed."""
    shape = shape.strip().lower()
    if shape not in SHAPES:
        console.print(
            Panel(
                f"[red]Unknown shape:[/red] {shape}\n"
                f"Choose from: {', '.join(SHAPES)}",
                style="bold red",
            )
        )
        raise typer.Exit(code=1)
    settings = load_settings()
    g = settings["general"]
    aw, ah = g["area_width"], g["area_height"]
    z_up = g.get("z_up_long", 12)
    z_down = g.get("z_down", 0)
    fd = float(g.get("feed_rate_draw", 3000))
    ft = float(g.get("feed_rate_travel", 6000))
    fz = float(g.get("feed_rate_z", 1500))
    body = generate_calibration_grid_gcode(
        aw,
        ah,
        grid_spacing_mm=spacing,
        cross_size_mm=cross_size,
        shape=shape,
        z_up=z_up,
        z_down=z_down,
        feed_rate_draw=fd,
        feed_rate_travel=ft,
        feed_rate_z=fz,
    )
    hm_path = height_map
    if hm_path is None and apply_settings_map:
        hm_path = g.get("height_map_path")
    if hm_path:
        hm_path = os.path.abspath(os.path.expanduser(str(hm_path).strip()))
        if not os.path.isfile(hm_path):
            console.print(
                Panel(f"[red]Height map not found:[/red] {hm_path}", style="bold red")
            )
            raise typer.Exit(code=1)
        hmap = HeightMap.from_json_file(hm_path)
        body = apply_height_map_to_gcode_text(body, hmap, z_down_base=float(z_down))
        console.print("[dim]Applied height map to calibration grid G-code[/dim]")
    if output:
        out = Path(output).expanduser()
        out = out.resolve()
        if out.is_dir() or str(output).endswith(os.sep):
            out = out / f"surface_cal_grid_{aw:.0f}x{ah:.0f}.gcode"
    else:
        out = Path(f"surface_cal_grid_{aw:.0f}x{ah:.0f}.gcode")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    console.print(
        Panel(
            f"[green]Wrote calibration grid[/green]\n{out}",
            style="bold green",
        )
    )


@surface_cal_app.command("sample")
def surface_cal_sample(
    output: str = typer.Option(
        ...,
        "--output",
        "-o",
        help="Path to write height map JSON",
    ),
    spacing: float = typer.Option(30.0, "--spacing", help="Must match grid G-code"),
    delta_z: float = typer.Option(
        0.2,
        "--delta-z",
        help="mm per step; typical 0.1–0.25 (each -1/+1 adds one step to the cell level)",
    ),
    input_json: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Existing map: add another -1/0/+1 pass on top of current levels",
    ),
):
    """Interactive: -1 / 0 / +1 per cell; levels accumulate (e.g. -1 twice => -2)."""
    settings = load_settings()
    g = settings["general"]
    aw, ah = g["area_width"], g["area_height"]
    nx, ny, xs, ys = grid_dimensions(aw, ah, spacing)
    prev = None
    if input_json:
        prev = load_height_map_json(input_json)
        if float(prev["grid_spacing"]) != spacing:
            console.print(
                Panel(
                    "[red]--spacing must match input file grid_spacing[/red]",
                    style="bold red",
                )
            )
            raise typer.Exit(code=1)
        if abs(float(prev["delta_z_mm"]) - delta_z) > 1e-9:
            console.print(
                Panel(
                    "[red]--delta-z must match input file delta_z_mm for refinement[/red]",
                    style="bold red",
                )
            )
            raise typer.Exit(code=1)
        if float(prev["area_width"]) != aw or float(prev["area_height"]) != ah:
            console.print(
                Panel(
                    "[red]Input map bed size must match current settings[/red]",
                    style="bold red",
                )
            )
            raise typer.Exit(code=1)
        points = [[int(v) for v in row] for row in prev["points"]]
        if len(points) != ny or (points and len(points[0]) != nx):
            console.print(Panel("[red]Input map grid shape mismatch[/red]", style="bold red"))
            raise typer.Exit(code=1)
        console.print("[cyan]Refining[/cyan] existing map (adding to each cell level)")
    else:
        points = [[0 for _ in range(nx)] for _ in range(ny)]

    console.print(
        f"Grid {nx}x{ny} on {aw}x{ah}mm bed, spacing {spacing}mm, delta_z={delta_z}mm/step. "
        f"Order: row 0 Y={ys[0]:.1f} .. row {ny-1} Y={ys[-1]:.1f}"
    )
    for yi in range(ny):
        for xi in range(nx):
            cur = points[yi][xi]
            off_mm = cur * delta_z
            label = (
                f"Y={ys[yi]:.0f} row {yi+1}/{ny}, X={xs[xi]:.0f} col {xi+1}/{nx} — "
                f"level {cur} (~{off_mm:+.3f}mm)"
            )
            choice = questionary.select(
                label,
                choices=[
                    "-1  deeper",
                    "0  no change",
                    "+1  higher",
                ],
            ).ask()
            if choice is None:
                raise typer.Exit(code=1)
            points[yi][xi] = cur + int(choice.split()[0])

    name_default = (prev or {}).get("name") or ""
    paper_default = (prev or {}).get("paper") or ""
    plotter_default = (prev or {}).get("plotter") or ""
    pen_default = (prev or {}).get("pen") or ""
    name = typer.prompt("Profile name (optional)", default=name_default, show_default=False)
    paper = typer.prompt("Paper note (optional)", default=paper_default, show_default=False)
    plotter = typer.prompt("Plotter note (optional)", default=plotter_default, show_default=False)
    pen = typer.prompt("Pen note (optional)", default=pen_default, show_default=False)
    data = build_height_map_dict(
        grid_spacing=spacing,
        delta_z_mm=delta_z,
        area_width=aw,
        area_height=ah,
        points=points,
        name=name,
        paper=paper,
        plotter=plotter,
        pen=pen,
    )
    outp = Path(output).expanduser().resolve()
    save_height_map_json(outp, data)
    console.print(
        Panel(
            f"[green]Saved height map[/green]\n{outp}",
            style="bold green",
        )
    )


app.add_typer(surface_cal_app, name="surface-cal")

if __name__ == "__main__":
    app(prog_name="plotter")
