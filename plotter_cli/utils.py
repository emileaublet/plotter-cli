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


def generate_boundary_gcode(paper_width, paper_height, area_width, area_height):
    """
    Generate G-code to draw boundaries for a selected paper size.

    Parameters:
        paper_width (float): Width of the paper in mm.
        paper_height (float): Height of the paper in mm.
        area_width (float): Width of the area in mm.
        area_height (float): Height of the area in mm.

    Returns:
        str: G-code commands to draw boundaries.
    """
    # Calculate the corners of the paper, perfectly aligned with the boundary
    top_left = (0, 0)
    top_right = (paper_width, 0)
    bottom_left = (0, paper_height)
    bottom_right = (paper_width, paper_height)

    # Generate G-code for 90-degree corners at each corner
    gcode = """
G21 ; Set units to mm
G90 ; Absolute positioning
G1 Z1.4 F3500 ; Pen up

; Top-left corner
G0 X{0:.2f} Y{1:.2f}
G1 Z0 F3500 ; Pen down
G1 X{0:.2f} Y{1:.2f}
G1 Z1.4 F3500 ; Pen up

; Top-right corner
G0 X{2:.2f} Y{3:.2f}
G1 Z0 F3500 ; Pen down
G1 X{2:.2f} Y{3:.2f}
G1 Z1.4 F3500 ; Pen up

; Bottom-left corner
G0 X{4:.2f} Y{5:.2f}
G1 Z0 F3500 ; Pen down
G1 X{4:.2f} Y{5:.2f}
G1 Z1.4 F3500 ; Pen up

; Bottom-right corner
G0 X{6:.2f} Y{7:.2f}
G1 Z0 F3500 ; Pen down
G1 X{6:.2f} Y{7:.2f}
G1 Z1.4 F3500 ; Pen up

M2 ; End of program
""".format(
        top_left[0],
        top_left[1],
        top_right[0],
        top_right[1],
        bottom_left[0],
        bottom_left[1],
        bottom_right[0],
        bottom_right[1],
    )

    return gcode
