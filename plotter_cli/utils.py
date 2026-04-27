import copy
import yaml
import xml.etree.ElementTree as ET
import importlib.resources
import re
import os


# Module-level settings cache — avoids repeated disk reads within a session.
# Invalidated by save_settings() so changes are picked up immediately.
_settings_cache = None
_settings_cache_path = None


def load_settings():
    """
    Load settings from YAML, with caching.

    Search order:
      1. ./settings.yaml (current working directory)
      2. plotter_cli/settings.yaml (package directory)
      3. Hardcoded defaults

    Returns a deep copy so callers can mutate without affecting the cache.

    Returns:
        dict: Settings dict with 'general' and 'papers' keys.
    """
    global _settings_cache, _settings_cache_path

    # Determine which settings file would be used
    if os.path.exists("settings.yaml"):
        candidate_path = os.path.abspath("settings.yaml")
    else:
        module_settings = os.path.join(os.path.dirname(__file__), "settings.yaml")
        if os.path.exists(module_settings):
            candidate_path = os.path.abspath(module_settings)
        else:
            candidate_path = None

    # Return cached value if it's for the same path
    if _settings_cache is not None and candidate_path == _settings_cache_path:
        return copy.deepcopy(_settings_cache)

    # Load fresh from disk
    if os.path.exists("settings.yaml"):
        with open("settings.yaml", "r") as file:
            settings = yaml.safe_load(file)
        _settings_cache = settings
        _settings_cache_path = candidate_path
        return copy.deepcopy(settings)

    # Try to load from the module directory (preferred for development/source access)
    module_settings = os.path.join(os.path.dirname(__file__), "settings.yaml")
    if os.path.exists(module_settings):
        with open(module_settings, "r") as file:
            settings = yaml.safe_load(file)
        _settings_cache = settings
        _settings_cache_path = candidate_path
        return copy.deepcopy(settings)

    # Fallback to package resources
    try:
        with importlib.resources.open_text("plotter_cli", "settings.yaml") as file:
            settings = yaml.safe_load(file)
        _settings_cache = settings
        _settings_cache_path = None
        return copy.deepcopy(settings)
    except FileNotFoundError:
        # If all else fails, return a default structure
        return {
            "general": {
                "area_width": 880,
                "area_height": 470,
                "paper_gap": 30.0,
                "z_up_long": 12,
                "z_up_short": 6,
                "z_up_threshold": 1.5,
                "z_down": -0.25,
                "feed_rate_draw": 8000,
                "feed_rate_travel": 8000,
                "feed_rate_z": 2400,
                "registration_marks_length": 4,
                "height_map_path": None,
            },
            "papers": [],
        }


def get_settings_file_path():
    """Get the path to the settings file that should be used for saving."""
    # Try current directory first (user's working directory)
    current_dir_settings = os.path.abspath("settings.yaml")
    if os.path.exists("settings.yaml"):
        return current_dir_settings
    
    # Fall back to module directory (package settings)
    module_settings = os.path.join(os.path.dirname(__file__), "settings.yaml")
    # If module settings doesn't exist, create it in current directory instead
    if not os.path.exists(module_settings):
        return current_dir_settings
    return os.path.abspath(module_settings)


def save_settings(settings):
    """
    Save settings to the YAML file.

    Args:
        settings: Dictionary containing settings to save (must include 'general' and 'papers' keys)

    Returns:
        str: Path to the saved settings file
    """
    global _settings_cache, _settings_cache_path

    settings_path = get_settings_file_path()

    # Ensure directory exists (only if path has a directory component)
    dir_path = os.path.dirname(settings_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    # Write settings to file
    with open(settings_path, "w", encoding="utf-8") as file:
        yaml.dump(settings, file, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Invalidate cache so the next load reads fresh data
    _settings_cache = None
    _settings_cache_path = None

    return settings_path


def parse_dimension(value):
    """Parse an SVG dimension string into a float value in mm."""
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    # Match number and optional unit
    match = re.match(r"^\s*([-+]?\d*\.?\d+)\s*([a-z%]*)\s*$", str(value), re.I)
    if not match:
        return 0.0

    number = float(match.group(1))
    unit = match.group(2).lower()

    if unit == "mm":
        return number
    elif unit == "cm":
        return number * 10
    elif unit == "in":
        return number * 25.4
    elif unit == "pt":
        return number * 25.4 / 72
    elif unit == "pc":
        return number * 25.4 / 6
    elif unit == "px":
        # Standard SVG pixel is 1/96 inch
        return number * 25.4 / 96
    else:
        # Default to pixels (1/96 inch) if unit is unknown or missing
        # This aligns with standard SVG behavior and vpype defaults
        return number * 25.4 / 96


def get_svg_dimensions(svg_file):
    """
    Parse the width and height of an SVG file in millimetres.

    Resolution order:
      1. width/height attributes on the root <svg> element (with unit conversion)
      2. viewBox attribute (width/height fields), treated as px if no unit

    Args:
        svg_file (str): Path to the SVG file.

    Returns:
        tuple[float, float]: (width_mm, height_mm)

    Raises:
        ValueError: If dimensions cannot be determined or the file is invalid XML.
    """
    try:
        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Handle namespaces - strip them if present
        # SVG root might be in a namespace like {http://www.w3.org/2000/svg}svg
        width_str = root.attrib.get("width")
        height_str = root.attrib.get("height")
        viewbox_str = root.attrib.get("viewBox")
        
        # Also try with namespace
        if not width_str or not height_str:
            # Try common SVG namespace
            ns = {"svg": "http://www.w3.org/2000/svg"}
            if not width_str:
                width_str = root.attrib.get("{http://www.w3.org/2000/svg}width")
            if not height_str:
                height_str = root.attrib.get("{http://www.w3.org/2000/svg}height")
            if not viewbox_str:
                viewbox_str = root.attrib.get("{http://www.w3.org/2000/svg}viewBox")

        width_is_percent = isinstance(width_str, str) and width_str.strip().endswith("%")
        height_is_percent = isinstance(height_str, str) and height_str.strip().endswith("%")
        width = parse_dimension(width_str) if width_str else 0.0
        height = parse_dimension(height_str) if height_str else 0.0

        # Fallback to viewBox if width or height are missing/zero OR percent-based.
        # Percent root dimensions are viewport-relative and not absolute physical size.
        if (not width or not height or width_is_percent or height_is_percent) and viewbox_str:
            parts = viewbox_str.split()
            if len(parts) == 4:
                # viewBox="min-x min-y width height"
                vb_width = parse_dimension(parts[2])
                vb_height = parse_dimension(parts[3])
                if not width or width == 0.0 or width_is_percent:
                    width = vb_width
                if not height or height == 0.0 or height_is_percent:
                    height = vb_height

        # Final fallback - if still no dimensions, raise an error
        if not width or width == 0.0 or not height or height == 0.0:
            raise ValueError(
                f"Could not determine SVG dimensions. "
                f"Width: {width_str}, Height: {height_str}, ViewBox: {viewbox_str}"
            )

        return float(width), float(height)
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse SVG file: {e}")
    except Exception as e:
        raise ValueError(f"Error getting SVG dimensions: {e}")


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
    area_max_x=880,
    area_max_y=470,
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

    except Exception as e:
        print(f"Warning: Failed to parse gcode stats from {file_path}: {e}")

    return stats


def validate_svg_dimensions(width: float, height: float) -> None:
    """
    Validate SVG dimensions, raising ValueError if either is zero or negative.

    Args:
        width: SVG width in mm
        height: SVG height in mm

    Raises:
        ValueError: If width or height is <= 0
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid SVG dimensions: {width}mm × {height}mm")


def format_distance(mm: float) -> str:
    """
    Format distance in mm to human-readable format.
    Uses mm for values < 1km (1,000,000mm), and km for values >= 1km.
    Numbers use thousand separators (e.g. 1,234,567.89mm).
    """
    if mm < 1_000_000:
        return f"{mm:,.2f}mm"
    else:
        km = mm / 1_000_000  # Convert mm to km (1 km = 1,000,000 mm)
        return f"{km:,.4f}km"


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
