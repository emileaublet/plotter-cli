import yaml
import xml.etree.ElementTree as ET
import importlib.resources


# Load settings from the YAML file
def load_settings():
    with importlib.resources.open_text("plotter_cli", "settings.yaml") as file:
        return yaml.safe_load(file)


# Extract width and height from an SVG file
def get_svg_dimensions(svg_file):
    tree = ET.parse(svg_file)
    root = tree.getroot()
    width = float(root.attrib.get("width", 0))
    height = float(root.attrib.get("height", 0))
    return width, height


def generate_boundary_gcode(
    paper_width, paper_height, area_width, area_height, z_up_long=20, z_down=0
):
    """
    Generate G-code to draw boundaries for a selected paper size.

    Parameters:
        paper_width (float): Width of the paper in mm.
        paper_height (float): Height of the paper in mm.
        area_width (float): Width of the area in mm.
        area_height (float): Height of the area in mm.
        z_up_long (float): Z position when pen is up in mm.
        z_down (float): Z position when pen is down in mm.

    Returns:
        str: G-code commands to draw boundaries.
    """
    # Calculate the corners of the paper, perfectly aligned with the boundary
    top_left = (0, 0)
    top_right = (paper_width, 0)
    bottom_left = (0, paper_height)
    bottom_right = (paper_width, paper_height)

    # Generate G-code for 90-degree corners at each corner
    gcode = f"""
G21 ; Set units to mm
G90 ; Absolute positioning
G1 Z{z_up_long} F3500 ; Pen up

; Top-left corner
G0 X{top_left[0]:.2f} Y{top_left[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{top_left[0]:.2f} Y{top_left[1]:.2f}
G1 Z{z_up_long} F3500 ; Pen up

; Top-right corner
G0 X{top_right[0]:.2f} Y{top_right[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{top_right[0]:.2f} Y{top_right[1]:.2f}
G1 Z{z_up_long} F3500 ; Pen up

; Bottom-left corner
G0 X{bottom_left[0]:.2f} Y{bottom_left[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{bottom_left[0]:.2f} Y{bottom_left[1]:.2f}
G1 Z{z_up_long} F3500 ; Pen up

; Bottom-right corner
G0 X{bottom_right[0]:.2f} Y{bottom_right[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{bottom_right[0]:.2f} Y{bottom_right[1]:.2f}
G1 Z{z_up_long} F3500 ; Pen up

M2 ; End of program
"""

    return gcode


def update_vpype_config_with_z_settings(
    z_up_long=20,
    z_down=0,
    feed_rate_draw=3000,
    feed_rate_travel=6000,
    feed_rate_z=1500,
    area_max_x=385,
    area_max_y=460,
):
    """
    Update the .vpype.toml configuration file with Z settings and feed rates from the YAML configuration.

    Parameters:
        z_up_long (float): Z position when pen is up in mm.
        z_down (float): Z position when pen is down in mm.
        feed_rate_draw (int): Feed rate for drawing movements in mm/min.
        feed_rate_travel (int): Feed rate for travel movements in mm/min.
        feed_rate_z (int): Feed rate for Z-axis movements in mm/min.
        area_max_x (float): Maximum X area in mm.
        area_max_y (float): Maximum Y area in mm.

    Returns:
        str: Path to the updated configuration file.
    """
    import tempfile
    import os

    # Create updated config content with all the feed rates
    config_content = f"""[gwrite.penplotte]
unit = "mm"
invert_y = true

document_start = \"\"\"G21 ; Set units to mm
G90 ; Absolute positioning
G1 Z{z_up_long} F{feed_rate_z} ; Pen up

G0 X0.0000 Y0.0000 F{feed_rate_travel} ; Move to origin
G1 Z{z_up_long} F{feed_rate_z} ; Stay pen up

\"\"\"

layer_start = "; --- Start Layer {{layer_index}} ---\\n"
line_start = "; --- Start Line {{lines_index}} X{{x:.8f}} Y{{y:.8f}} ---\\n"

segment_first = \"\"\"G1 Z{z_up_long} F{feed_rate_z} ; Pen up before move
G0 X{{x:.8f}} Y{{y:.8f}} F{feed_rate_travel} ; Travel to start
G1 Z{z_down} F{feed_rate_z} ; Pen down
\"\"\"

segment = \"\"\"G1 X{{x:.8f}} Y{{y:.8f}} F{feed_rate_draw} ; Draw
\"\"\"

line_end = "; --- End Line {{lines_index}} ---\\n"
layer_end = "; --- End Layer {{layer_index}} ---\\n"

document_end = \"\"\"G1 Z{z_up_long} F{feed_rate_z} ; Pen up
G0 X0.0000 Y0.0000 F{feed_rate_travel} ; Return to home
G1 Z{z_up_long} F{feed_rate_z} ; Stay pen up
M2 ; End of program
\"\"\"
"""

    # Create a temporary file with the updated config
    temp_fd, temp_path = tempfile.mkstemp(suffix=".toml", prefix="vpype_config_")
    with os.fdopen(temp_fd, "w") as temp_file:
        temp_file.write(config_content)

    return temp_path


def hex_to_color_name(hex_color: str) -> str:
    """
    Convert a hex color code to a human-readable color name.
    Ignores the alpha channel (last 2 digits of 8-char hex codes).

    Parameters:
        hex_color (str): Hex color code (e.g., "#FF0000" or "FF000000" with alpha)

    Returns:
        str: Human-readable color name (e.g., "red", "blue", "dark_green")
    """
    import math

    # Remove '#' if present
    hex_color = hex_color.lstrip("#")

    # If 8 characters (with alpha), ignore the last 2 digits (alpha channel)
    if len(hex_color) == 8:
        hex_color = hex_color[:6]

    # Parse RGB values
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except (ValueError, IndexError):
        return "unknown"

    # Extended color mapping with RGB values - using common, clear names
    color_map = {
        # Basic colors
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "red": (255, 0, 0),
        "green": (0, 128, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "orange": (255, 165, 0),
        "pink": (255, 192, 203),
        "purple": (128, 0, 128),
        "brown": (139, 69, 19),
        # Grays
        "gray": (128, 128, 128),
        "light_gray": (192, 192, 192),
        "dark_gray": (64, 64, 64),
        # Dark variants
        "dark_red": (139, 0, 0),
        "dark_green": (0, 100, 0),
        "dark_blue": (0, 0, 139),
        "dark_orange": (255, 140, 0),
        "dark_yellow": (204, 204, 0),
        "dark_pink": (231, 84, 128),
        "dark_purple": (48, 0, 48),
        "dark_brown": (101, 67, 33),
        "dark_cyan": (0, 139, 139),
        # Light variants
        "light_red": (255, 102, 102),
        "light_green": (144, 238, 144),
        "light_blue": (173, 216, 230),
        "light_orange": (255, 200, 150),
        "light_yellow": (255, 255, 200),
        "light_pink": (255, 182, 193),
        "light_purple": (200, 162, 200),
        "light_brown": (181, 137, 99),
        "light_cyan": (180, 255, 255),
        # Other common colors
        "navy": (0, 0, 128),
        "teal": (0, 128, 128),
        "olive": (128, 128, 0),
        "lime": (0, 255, 0),
        "beige": (245, 245, 220),
    }

    # Find the closest color by Euclidean distance
    min_distance = float("inf")
    closest_color = "unknown"

    for color_name, (cr, cg, cb) in color_map.items():
        distance = math.sqrt((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2)
        if distance < min_distance:
            min_distance = distance
            closest_color = color_name

    return closest_color


def rename_gcode_with_color_name(file_path: str) -> str:
    """
    Rename a gcode file to include a color name based on its hex color code.
    Expects filenames like: my_file#FF0000FF.gcode
    Returns new filename like: my_file#FF0000FF_red.gcode

    Parameters:
        file_path (str): Path to the gcode file

    Returns:
        str: New filename (just the name, not the full path)
    """
    import os
    import re

    dirname = os.path.dirname(file_path)
    filename = os.path.basename(file_path)

    # Match pattern: anything#XXXXXXXX.gcode (8 hex chars before extension)
    pattern = r"^(.+)#([0-9A-Fa-f]{8})(\.gcode)$"
    match = re.match(pattern, filename)

    if not match:
        # Try 6 char hex code pattern as fallback
        pattern_6 = r"^(.+)#([0-9A-Fa-f]{6})(\.gcode)$"
        match = re.match(pattern_6, filename)

    if match:
        base_name = match.group(1)
        hex_code = match.group(2)
        extension = match.group(3)

        color_name = hex_to_color_name(hex_code)
        new_filename = f"{base_name}#{hex_code}_{color_name}{extension}"

        old_path = file_path
        new_path = os.path.join(dirname, new_filename)

        if old_path != new_path and os.path.exists(old_path):
            os.rename(old_path, new_path)

        return new_filename

    return filename


def calculate_gcode_stats(file_path: str) -> dict:
    """
    Calculate statistics from a gcode file.

    Parameters:
        file_path (str): Path to the gcode file

    Returns:
        dict: Statistics including draw_distance_mm, travel_distance_mm,
              num_pen_lifts, color_name, hex_code
    """
    import re
    import math
    import os

    stats = {
        "draw_distance_mm": 0.0,
        "travel_distance_mm": 0.0,
        "num_pen_lifts": 0,
        "num_segments": 0,
        "color_name": None,
        "hex_code": None,
    }

    # Extract color info from filename
    filename = os.path.basename(file_path)
    color_match = re.search(r"#([0-9A-Fa-f]{6,8})_(\w+)\.gcode$", filename)
    if color_match:
        stats["hex_code"] = color_match.group(1)[:6]  # Just RGB, no alpha
        stats["color_name"] = color_match.group(2)

    current_x = 0.0
    current_y = 0.0
    is_drawing = False  # Track if pen is down

    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip().upper()

                # Check for pen down (Z goes negative or to 0)
                if line.startswith("G1") and "Z" in line:
                    z_match = re.search(r"Z([-+]?\d*\.?\d+)", line)
                    if z_match:
                        z_val = float(z_match.group(1))
                        if z_val <= 0:
                            is_drawing = True
                        else:
                            if is_drawing:
                                stats["num_pen_lifts"] += 1
                            is_drawing = False

                # Parse X/Y movements
                if line.startswith("G0") or line.startswith("G1"):
                    x_match = re.search(r"X([-+]?\d*\.?\d+)", line)
                    y_match = re.search(r"Y([-+]?\d*\.?\d+)", line)

                    new_x = float(x_match.group(1)) if x_match else current_x
                    new_y = float(y_match.group(1)) if y_match else current_y

                    # Calculate distance
                    distance = math.sqrt(
                        (new_x - current_x) ** 2 + (new_y - current_y) ** 2
                    )

                    if line.startswith("G1") and is_drawing and (x_match or y_match):
                        stats["draw_distance_mm"] += distance
                    elif line.startswith("G0"):
                        stats["travel_distance_mm"] += distance

                    current_x = new_x
                    current_y = new_y

                # Count segments
                if "; --- Start Line" in line.upper() or "; --- START LINE" in line:
                    stats["num_segments"] += 1

    except Exception:
        pass

    return stats


def format_distance(mm: float) -> str:
    """Format distance in mm to human-readable format."""
    if mm >= 1000:
        return f"{mm / 1000:.2f}m"
    else:
        return f"{mm:.0f}mm"


def format_time(minutes: float) -> str:
    """Format time in minutes to human-readable format."""
    if minutes < 1:
        return f"{int(minutes * 60)}s"
    elif minutes < 60:
        mins = int(minutes)
        secs = int((minutes - mins) * 60)
        if secs > 0:
            return f"{mins}m {secs}s"
        return f"{mins}m"
    else:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        if mins > 0:
            return f"{hours}h {mins}m"
        return f"{hours}h"


def estimate_draw_time(
    draw_distance_mm: float,
    travel_distance_mm: float,
    pen_lifts: int,
    feed_rate_draw: float = 4000,
    feed_rate_travel: float = 6000,
    feed_rate_z: float = 1500,
    z_up: float = 12,
    z_down: float = 0,
) -> float:
    """
    Estimate the time to draw in minutes.

    Parameters:
        draw_distance_mm: Total drawing distance in mm
        travel_distance_mm: Total travel distance in mm
        pen_lifts: Number of pen up/down cycles
        feed_rate_draw: Drawing feed rate in mm/min
        feed_rate_travel: Travel feed rate in mm/min
        feed_rate_z: Z-axis feed rate in mm/min
        z_up: Z height when pen is up in mm
        z_down: Z height when pen is down in mm

    Returns:
        Estimated time in minutes
    """
    # Time for drawing movements
    draw_time = draw_distance_mm / feed_rate_draw

    # Time for travel movements
    travel_time = travel_distance_mm / feed_rate_travel

    # Time for Z movements (up and down for each pen lift)
    z_distance_per_lift = abs(z_up - z_down) * 2  # up + down
    z_time = (pen_lifts * z_distance_per_lift) / feed_rate_z

    return draw_time + travel_time + z_time


def hex_to_rich_color(hex_code: str) -> str:
    """
    Convert a hex color code to a Rich-compatible color string.

    Parameters:
        hex_code (str): 6 or 8 character hex code (alpha ignored)

    Returns:
        str: Rich color code (e.g., "#FF0000")
    """
    hex_code = hex_code.lstrip("#")[:6]
    return f"#{hex_code}"
