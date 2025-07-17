import yaml
import xml.etree.ElementTree as ET


# Load settings from the YAML file
def load_settings():
    with open("settings.yaml", "r") as file:
        return yaml.safe_load(file)


# Extract width and height from an SVG file
def get_svg_dimensions(svg_file):
    tree = ET.parse(svg_file)
    root = tree.getroot()
    width = float(root.attrib.get("width", 0))
    height = float(root.attrib.get("height", 0))
    return width, height
