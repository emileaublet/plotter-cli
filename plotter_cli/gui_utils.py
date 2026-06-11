"""
Utility functions for the Plotter GUI.
Handles SVG processing, conversion, and G-code generation.
"""

import os
import copy
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional

from .utils import (
    load_settings,
    update_vpype_config_with_z_settings,
    rename_gcode_with_color_name,
)
from .gcode_parser import GCodeParser
from .surface_calibration import apply_height_map_if_configured


def svg_to_png(svg_path: str, output_path: str = None, dpi: int = 150) -> Optional[str]:
    """
    Convert SVG to PNG for preview.

    Args:
        svg_path: Path to input SVG file
        output_path: Optional output path (if None, generates temp path)
        dpi: Resolution for PNG output

    Returns:
        Path to generated PNG file, or None if conversion fails
    """
    if output_path is None:
        output_path = svg_path.rsplit(".", 1)[0] + "_preview.png"

    # Try using cairosvg first (preferred)
    try:
        import cairosvg

        cairosvg.svg2png(url=svg_path, write_to=output_path, dpi=dpi)
        return output_path
    except Exception as e:
        print(f"Warning: cairosvg failed for {svg_path}: {e}")
        # Fallback to svglib + reportlab
        try:
            from svglib.svglib import svg2rlg
            from reportlab.graphics import renderPM

            drawing = svg2rlg(svg_path)
            if drawing:
                renderPM.drawToFile(drawing, output_path, fmt="PNG", dpi=dpi)
                return output_path
        except Exception as e2:
            print(f"Warning: svglib fallback also failed for {svg_path}: {e2}")
            return None

    return None


def apply_svg_transform(
    svg_element: ET.Element,
    x: float,
    y: float,
    scale_x: float,
    scale_y: float,
    rotation: float,
) -> ET.Element:
    """
    Apply transforms to an SVG element by wrapping it in a group with transform.

    Args:
        svg_element: SVG element to transform
        x: X translation in mm
        y: Y translation in mm
        scale_x: X scale factor
        scale_y: Y scale factor
        rotation: Rotation angle in degrees

    Returns:
        New group element with transform applied
    """
    # Create a group element
    g = ET.Element("g")

    # Build transform string
    transforms = []
    if x != 0 or y != 0:
        transforms.append(f"translate({x:.6f}, {y:.6f})")
    if rotation != 0:
        # Get center of element for rotation
        width = float(svg_element.get("width", 0))
        height = float(svg_element.get("height", 0))
        center_x = width / 2
        center_y = height / 2
        transforms.append(f"rotate({rotation:.6f}, {center_x:.6f}, {center_y:.6f})")
    if scale_x != 1.0 or scale_y != 1.0:
        transforms.append(f"scale({scale_x:.6f}, {scale_y:.6f})")

    if transforms:
        g.set("transform", " ".join(transforms))

    # Copy the original element into the group
    g.append(svg_element)

    return g


def generate_combined_svg(
    svgs: List[Dict], canvas_width: float, canvas_height: float, output_path: str
):
    """
    Generate a combined SVG with all SVGs positioned and transformed.

    Args:
        svgs: List of SVG data dictionaries with filepath, x, y, scale_x, scale_y, rotation
        canvas_width: Canvas width in mm
        canvas_height: Canvas height in mm
        output_path: Path to save the combined SVG
    """
    # Create root SVG element
    # SVG uses top-left origin (standard)
    # vpype will handle Y inversion when generating G-code (invert_y = true)
    root = ET.Element("svg")
    root.set("xmlns", "http://www.w3.org/2000/svg")
    root.set("width", f"{canvas_width}mm")
    root.set("height", f"{canvas_height}mm")
    root.set("viewBox", f"0 0 {canvas_width} {canvas_height}")

    # Process each SVG
    for idx, svg_data in enumerate(svgs):
        filepath = svg_data["filepath"]
        if not os.path.exists(filepath):
            continue

        # Parse the SVG file
        try:
            tree = ET.parse(filepath)
            svg_root = tree.getroot()

            # Get dimensions from svg_data (already converted to mm by get_svg_dimensions)
            width_mm = svg_data.get("width", 0)
            height_mm = svg_data.get("height", 0)

            # Get original SVG's viewBox or dimensions to understand its coordinate system
            viewbox_str = svg_root.get("viewBox", "")
            original_width_str = svg_root.get("width", "")
            original_height_str = svg_root.get("height", "")

            # Determine the original coordinate system
            from .utils import parse_dimension

            if viewbox_str:
                # Use viewBox to determine coordinate system
                vb_parts = viewbox_str.split()
                if len(vb_parts) == 4:
                    # viewBox="min-x min-y width height"
                    original_width = float(vb_parts[2])
                    original_height = float(vb_parts[3])
                else:
                    # Fallback to width/height attributes
                    original_width = (
                        parse_dimension(original_width_str)
                        if original_width_str
                        else width_mm
                    )
                    original_height = (
                        parse_dimension(original_height_str)
                        if original_height_str
                        else height_mm
                    )
            else:
                # No viewBox, use width/height attributes
                original_width = (
                    parse_dimension(original_width_str)
                    if original_width_str
                    else width_mm
                )
                original_height = (
                    parse_dimension(original_height_str)
                    if original_height_str
                    else height_mm
                )

            # Create a group for this SVG with transforms
            g = ET.Element("g")

            # Use paper dimensions (paper size is fixed, cannot be scaled)
            paper_width = svg_data.get("paper_width", width_mm)
            paper_height = svg_data.get("paper_height", height_mm)

            # Use GUI coordinates (top-left origin) and let gwrite invert_y handle plotter conversion.
            # We store x/y as the paper's top-left in GUI coordinates.
            x = svg_data.get("x", 0)
            y_gui = svg_data.get("y", 0)  # GUI: top-left origin, y increases downward

            # SVG scale factor (auto-calculated to fit SVG inside paper)
            svg_scale = svg_data.get("svg_scale", 1.0)

            rotation = float(svg_data.get("rotation", 0))

            # Calculate scaled SVG dimensions (for centering)
            scaled_svg_width = width_mm * svg_scale
            scaled_svg_height = height_mm * svg_scale

            transforms = []
            # SVG transforms are applied right-to-left (last in list is applied first)
            # Transform order in string (right-to-left): rotate, translate(final), translate(center), scale(svg_scale), scale(unit)

            # Calculate scale factor to convert from original SVG coordinate system to mm
            unit_scale_x = width_mm / original_width if original_width > 0 else 1.0
            unit_scale_y = height_mm / original_height if original_height > 0 else 1.0

            # Calculate center of paper in GUI coordinates (top-left origin)
            paper_center_x = x + paper_width / 2
            paper_center_y = y_gui + paper_height / 2

            # Build transforms - SVG applies right-to-left, so we build in reverse order
            # Desired application order: scale(unit) -> scale(svg) -> translate(center) -> translate(paper_pos) -> rotate
            # SVG applies right-to-left, so transform string should be: rotate translate(paper_pos) translate(center) scale(svg) scale(unit)
            # This means the list should be: [rotate, translate(paper_pos), translate(center), scale(svg), scale(unit)]
            
            # Step 1: Scale from original units to mm (applied FIRST)
            # Step 2: Apply SVG scale to fit inside paper (applied SECOND)  
            # We want application order: scale(unit) THEN scale(svg)
            # SVG applies right-to-left, so in the string we need: scale(svg) scale(unit)
            # To get this, we append in reverse: scale(svg) first, then scale(unit)
            if svg_scale != 1.0:
                transforms.append(f"scale({svg_scale:.6f}, {svg_scale:.6f})")
            if unit_scale_x != 1.0 or unit_scale_y != 1.0:
                transforms.append(f"scale({unit_scale_x:.6f}, {unit_scale_y:.6f})")

            # Step 3: Translate to center the scaled SVG within the paper (applied THIRD)
            # After scaling, SVG's (0,0) is at top-left of scaled SVG
            # To center: translate by half the difference between paper and scaled SVG size
            # This translation happens in the paper's local coordinate system (before moving to canvas)
            center_offset_x = (paper_width - scaled_svg_width) / 2
            center_offset_y = (paper_height - scaled_svg_height) / 2
            
            # Step 4: Translate to paper position on canvas (applied FOURTH)
            # First, insert paper_pos translation
            transforms.insert(0, f"translate({x:.6f}, {y_gui:.6f})")
            
            # Step 5: Translate to center the scaled SVG within the paper (applied THIRD, BEFORE paper_pos)
            # Insert center_offset AFTER paper_pos in the list, so it comes BEFORE in the string
            # This ensures center_offset is applied in paper's local space, then paper is moved to canvas
            # Result: [translate(paper_pos), translate(center), ...] → "translate(paper_pos) translate(center) ..."
            # Applied right-to-left: translate(center) in paper-local space, then translate(paper_pos) to canvas ✓
            if abs(center_offset_x) > 0.001 or abs(center_offset_y) > 0.001:
                transforms.insert(1, f"translate({center_offset_x:.6f}, {center_offset_y:.6f})")

            # Step 6: Rotate about the paper center (applied LAST, so inserted at BEGINNING)
            # Rotation center must be in canvas coordinates AFTER translate(paper_pos) is applied
            # After translate(paper_pos), the paper's center in canvas coords is:
            rotation_center_x = x + paper_width / 2
            rotation_center_y = y_gui + paper_height / 2
            if rotation % 360 != 0:
                transforms.insert(0, f"rotate({rotation:.6f}, {rotation_center_x:.6f}, {rotation_center_y:.6f})")

            # Note: The root SVG transform (scale(1, -1) translate(0, canvas_height))
            # will convert our bottom-left coordinates to top-left for SVG rendering

            if transforms:
                transform_str = " ".join(transforms)
                g.set("transform", transform_str)

            # Create a wrapper SVG that preserves the original root attributes
            # (including width/height units, viewBox, transform, preserveAspectRatio)
            wrapper_svg = ET.Element(svg_root.tag, dict(svg_root.attrib))
            if not wrapper_svg.get("viewBox"):
                wrapper_svg.set(
                    "viewBox", f"0 0 {original_width:.6f} {original_height:.6f}"
                )
            # vpype resolves nested percentage viewports against the outer canvas,
            # unlike browser rendering. Use explicit local viewport dimensions.
            if wrapper_svg.get("width") == "100%":
                wrapper_svg.set("width", f"{original_width:.6f}")
            if wrapper_svg.get("height") == "100%":
                wrapper_svg.set("height", f"{original_height:.6f}")

            # Copy children from original SVG root (preserve attributes/transforms)
            for child in svg_root:
                wrapper_svg.append(copy.deepcopy(child))

            g.append(wrapper_svg)
            root.append(g)

        except Exception as e:
            print(f"Warning: Failed to process SVG {filepath}: {e}")
            continue

    # Write the combined SVG
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def generate_guide_gcode(svgs: List[Dict], output_path: str, settings: Dict):
    """
    Generate guide G-code with rectangles for each paper, accounting for transforms.

    Args:
        svgs: List of SVG data dictionaries with transforms
        output_path: Path to save the guide G-code
        settings: Settings dictionary from load_settings()
    """
    import math

    z_up = settings["general"].get("z_up_long", 20)
    z_down = settings["general"].get("z_down", 0)
    feed_rate_draw = settings["general"].get("feed_rate_draw", 3000)
    feed_rate_travel = settings["general"].get("feed_rate_travel", 6000)
    feed_rate_z = settings["general"].get("feed_rate_z", 1500)

    gcode_lines = [
        "G21 ; Set units to mm",
        "G90 ; Absolute positioning",
        f"G1 Z{z_up} F{feed_rate_z} ; Pen up",
        "",
    ]

    # Get canvas height for Y coordinate inversion
    canvas_height = settings["general"].get("area_height", 470)

    # Generate rectangle for each SVG (paper boundaries, accounting for rotation)
    for svg_data in svgs:
        x = svg_data.get("x", 0)
        y_gui = svg_data.get("y", 0)  # GUI coordinates (top-left origin)
        rotation = float(svg_data.get("rotation", 0))

        # Use paper dimensions directly (paper cannot be scaled)
        paper_width = svg_data.get("paper_width", svg_data.get("width", 0))
        paper_height = svg_data.get("paper_height", svg_data.get("height", 0))

        # Convert to plotter coordinates (bottom-left origin)
        # GUI stores top-left of the paper; subtract paper height for bottom-left.
        y = canvas_height - y_gui - paper_height

        if paper_width <= 0 or paper_height <= 0:
            continue

        # Calculate paper center in canvas coordinates (for rotation)
        paper_center_x = x + paper_width / 2
        paper_center_y_plotter = y + paper_height / 2

        # Paper corners in local coordinates (relative to paper center, before rotation)
        # These are the corners of an unrotated paper centered at origin
        half_width = paper_width / 2
        half_height = paper_height / 2
        corners_local = [
            (-half_width, -half_height),  # bottom-left (relative to center)
            (half_width, -half_height),   # bottom-right
            (half_width, half_height),     # top-right
            (-half_width, half_height),   # top-left
        ]

        # Apply rotation to corners
        rotation_rad = math.radians(rotation)
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        
        corners_world = []
        for corner_local_x, corner_local_y in corners_local:
            # Rotate around origin
            rotated_x = corner_local_x * cos_r - corner_local_y * sin_r
            rotated_y = corner_local_x * sin_r + corner_local_y * cos_r
            # Translate to paper center position
            world_x = paper_center_x + rotated_x
            world_y = paper_center_y_plotter + rotated_y
            corners_world.append((world_x, world_y))

        # Draw rectangle by moving to each corner
        gcode_lines.append(f"; Rectangle for {svg_data.get('filename', 'unknown')}")
        gcode_lines.append(
            f"G0 X{corners_world[0][0]:.2f} Y{corners_world[0][1]:.2f} F{feed_rate_travel} ; Move to corner 1"
        )
        gcode_lines.append(f"G1 Z{z_down} F{feed_rate_z} ; Pen down")

        # Draw to each corner (close the rectangle)
        for i in range(1, 4):
            gcode_lines.append(
                f"G1 X{corners_world[i][0]:.2f} Y{corners_world[i][1]:.2f} F{feed_rate_draw} ; Corner {i+1}"
            )

        # Close rectangle
        gcode_lines.append(
            f"G1 X{corners_world[0][0]:.2f} Y{corners_world[0][1]:.2f} F{feed_rate_draw} ; Close rectangle"
        )
        gcode_lines.append(f"G1 Z{z_up} F{feed_rate_z} ; Pen up")
        gcode_lines.append("")

    # End program
    gcode_lines.extend(
        [
            f"G0 X0.0000 Y0.0000 F{feed_rate_travel} ; Return to home",
            f"G1 Z{z_up} F{feed_rate_z} ; Stay pen up",
            "M2 ; End of program",
        ]
    )

    # Write G-code file
    with open(output_path, "w") as f:
        f.write("\n".join(gcode_lines))


def process_svg_to_gcode(
    svg_path: str,
    canvas_width: float,
    canvas_height: float,
    output_folder: str,
    height_map_path: Optional[str] = None,
) -> List[str]:
    """
    Process a combined SVG to G-code files (one per color).

    Args:
        svg_path: Path to combined SVG file
        canvas_width: Canvas width in mm
        canvas_height: Canvas height in mm
        output_folder: Folder to save G-code files
        height_map_path: Optional JSON height map; if None, uses general.height_map_path from settings when set.

    Returns:
        List of generated G-code file paths
    """
    settings = load_settings()
    svg_filename = os.path.basename(svg_path)
    svg_name_without_ext = os.path.splitext(svg_filename)[0]

    # Create output path pattern
    output_path = os.path.join(output_folder, f"{svg_name_without_ext}_%_color%.gcode")

    # Get settings
    z_up = settings["general"].get("z_up_long", 20)
    z_down = settings["general"].get("z_down", 0)
    feed_rate_draw = settings["general"].get("feed_rate_draw", 3000)
    feed_rate_travel = settings["general"].get("feed_rate_travel", 6000)
    feed_rate_z = settings["general"].get("feed_rate_z", 1500)
    area_max_x = settings["general"].get("area_width", 880)
    area_max_y = settings["general"].get("area_height", 470)
    registration_marks_length = settings["general"].get("registration_marks_length", 4)
    linemerge = settings["general"].get("linemerge", True)
    reloop = settings["general"].get("reloop", False)
    path_sorting = settings["general"].get("path_sorting", True)
    path_reversing = settings["general"].get("path_reversing", True)

    # Create temporary vpype config
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
        # Build vpype command (similar to process command but without layout/scaleto)
        # Since we're already positioning in the combined SVG, we just need to process it
        vpype_command = [
            "vpype",
            "-c",
            temp_config_path,
            "read",
            "--attr",
            "stroke",
            svg_path,
            "forlayer",
            "lmove",
            "all",
            "999",
        ]

        if linemerge:
            vpype_command.append("linemerge")

        if reloop:
            vpype_command.append("reloop")

        if path_sorting:
            vpype_command.append("linesort")
            if not path_reversing:
                vpype_command.append("--no-flip")
            else:
                vpype_command.extend(["--two-opt", "--passes", "2000"])

        vpype_command.extend(
            [
                "rect",
                f"{registration_marks_length}mm",
                f"{registration_marks_length}mm",
                f"{registration_marks_length}mm",
                f"{registration_marks_length}mm",
                "rect",
                f"{area_max_x - 2 * registration_marks_length}mm",
                f"{registration_marks_length}mm",
                f"{registration_marks_length}mm",
                f"{registration_marks_length}mm",
                "rect",
                f"{registration_marks_length}mm",
                f"{area_max_y - 2 * registration_marks_length}mm",
                f"{registration_marks_length}mm",
                f"{registration_marks_length}mm",
                "rect",
                f"{area_max_x - 2 * registration_marks_length}mm",
                f"{area_max_y - 2 * registration_marks_length}mm",
                f"{registration_marks_length}mm",
                f"{registration_marks_length}mm",
                "lmove",
                "1",
                "1",
                "lmove",
                "999",
                "2",
                "gwrite",
                "-p",
                "penplotte",
                output_path,
                "end",
            ]
        )

        # Execute vpype command
        subprocess.run(vpype_command, check=True, capture_output=True)

        # Find generated G-code files
        gcode_files = []
        for f in os.listdir(output_folder):
            if f.endswith(".gcode") and svg_name_without_ext in f:
                gcode_files.append(os.path.join(output_folder, f))

        # Rename G-code files to include color names
        renamed_files = []
        for gcode_file in gcode_files:
            try:
                new_filename = rename_gcode_with_color_name(gcode_file)
                renamed_files.append(os.path.join(output_folder, new_filename))
            except Exception as e:
                print(f"Warning: Failed to rename {gcode_file}: {e}")
                renamed_files.append(gcode_file)
        gcode_files = renamed_files

        # Post-process G-code files with optimization
        z_up_long = settings["general"].get("z_up_long", 10.0)
        z_up_short = settings["general"].get("z_up_short", 4.0)
        z_up_threshold = settings["general"].get("z_up_threshold", 1.5)
        z_down = settings["general"].get("z_down", 0.0)
        feed_rate_draw = settings["general"].get("feed_rate_draw", 4000)
        feed_rate_z = settings["general"].get("feed_rate_z", 1500)

        parser = GCodeParser(
            long_distance_z=z_up_long,
            short_distance_z=z_up_short,
            short_distance_mm=z_up_threshold,
            z_down=z_down,
            feed_rate_draw=feed_rate_draw,
            feed_rate_z=feed_rate_z,
        )

        for gcode_file in gcode_files:
            try:
                parser.parse_file(Path(gcode_file))
            except Exception as e:
                print(f"Warning: Failed to optimize {gcode_file}: {e}")

        apply_height_map_if_configured(
            gcode_files,
            settings["general"],
            height_map_path_override=height_map_path,
        )

        return gcode_files

    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        raise RuntimeError(
            f"Failed to execute vpype command: {e}\n{stderr_output}".strip()
        )
    finally:
        # Clean up temporary config file
        if os.path.exists(temp_config_path):
            os.unlink(temp_config_path)
