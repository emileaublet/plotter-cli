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
