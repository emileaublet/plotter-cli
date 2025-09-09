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
    paper_width, paper_height, area_width, area_height, z_up=20, z_down=0
):
    """
    Generate G-code to draw boundaries for a selected paper size.

    Parameters:
        paper_width (float): Width of the paper in mm.
        paper_height (float): Height of the paper in mm.
        area_width (float): Width of the area in mm.
        area_height (float): Height of the area in mm.
        z_up (float): Z position when pen is up in mm.
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
G1 Z{z_up} F3500 ; Pen up

; Top-left corner
G0 X{top_left[0]:.2f} Y{top_left[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{top_left[0]:.2f} Y{top_left[1]:.2f}
G1 Z{z_up} F3500 ; Pen up

; Top-right corner
G0 X{top_right[0]:.2f} Y{top_right[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{top_right[0]:.2f} Y{top_right[1]:.2f}
G1 Z{z_up} F3500 ; Pen up

; Bottom-left corner
G0 X{bottom_left[0]:.2f} Y{bottom_left[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{bottom_left[0]:.2f} Y{bottom_left[1]:.2f}
G1 Z{z_up} F3500 ; Pen up

; Bottom-right corner
G0 X{bottom_right[0]:.2f} Y{bottom_right[1]:.2f}
G1 Z{z_down} F3500 ; Pen down
G1 X{bottom_right[0]:.2f} Y{bottom_right[1]:.2f}
G1 Z{z_up} F3500 ; Pen up

M2 ; End of program
"""

    return gcode


def update_vpype_config_with_z_settings(
    z_up=20,
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
        z_up (float): Z position when pen is up in mm.
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
G1 Z{z_up} F{feed_rate_z} ; Pen up

G0 X0.0000 Y0.0000 F{feed_rate_travel} ; Move to origin
G1 Z{z_up} F{feed_rate_z} ; Stay pen up

\"\"\"

layer_start = "; --- Start Layer ---\\nG90 ; Absolute positioning\\n"

line_start = "; --- Start Line ---\\n"

segment_first = \"\"\"G1 Z{z_up} F{feed_rate_z} ; Pen up before move
G0 X{{x:.4f}} Y{{y:.4f}} F{feed_rate_travel} ; Travel to start
G1 Z{z_down} F{feed_rate_z} ; Pen down
\"\"\"

segment = \"\"\"G1 X{{x:.4f}} Y{{y:.4f}} F{feed_rate_draw} ; Draw
\"\"\"

line_end = \"\"\"G1 Z{z_up} F{feed_rate_z} ; Pen up
\"\"\"

document_end = \"\"\"G1 Z{z_up} F{feed_rate_z} ; Pen up
G0 X0.0000 Y0.0000 F{feed_rate_travel} ; Return to home
G1 Z{z_up} F{feed_rate_z} ; Stay pen up
M2 ; End of program
\"\"\"
"""

    # Create a temporary file with the updated config
    temp_fd, temp_path = tempfile.mkstemp(suffix=".toml", prefix="vpype_config_")
    with os.fdopen(temp_fd, "w") as temp_file:
        temp_file.write(config_content)

    return temp_path
