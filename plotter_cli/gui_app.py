"""
Flask application for the Plotter GUI (Plotter Studio).

Provides a REST API consumed by the frontend (app.js) and a single HTML page
served to the pywebview native window (or a browser in --browser mode).

Architecture notes:
  - State is purely in-memory: svg_library (uploaded SVGs) and paper_store
    (papers on the canvas). Both are cleared on process exit.
  - Coordinate system: all x/y positions stored in GUI coords (top-left origin,
    Y increases downward). Conversion to plotter coords (bottom-left origin)
    happens in gui_utils.py at export time: y_plotter = canvas_height - y - h
  - PNG previews are generated once on SVG upload and the path is cached in
    svg_library[id]["preview_png_path"]. Re-generated on cache miss.
  - The native window is managed by pywebview; Flask runs in a daemon thread.
    WindowControlAPI is exposed to JS via js_api for minimize/maximize/close.
"""

import math
import os
import time
import json
import platform
import subprocess
import tempfile
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from .utils import (
    load_settings,
    save_settings,
    get_settings_file_path,
    get_svg_dimensions,
    validate_svg_dimensions,
    calculate_gcode_stats,
    estimate_draw_time,
    format_time,
    format_distance,
)
from .gui_utils import (
    svg_to_png,
    generate_combined_svg,
    generate_guide_gcode,
    process_svg_to_gcode,
)
from .surface_calibration import (
    generate_calibration_grid_gcode,
    apply_height_map_to_gcode_text,
    grid_dimensions,
    build_height_map_dict,
    save_height_map_json,
    load_height_map_json,
    HeightMap,
)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "gui", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "gui", "static"),
)

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {"svg"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = (
    256 * 1024 * 1024
)  # 256MB max file size (increased for large SVGs)

# In-memory storage (in production, use a database)
svg_library = {}  # Available SVGs that can be assigned to papers
paper_store = {}  # Papers on the canvas


def _default_height_map_path():
    """Return the standard saved height map path next to the active settings file."""
    settings_path = get_settings_file_path()
    return os.path.join(os.path.dirname(settings_path), "height_map.json")


def _height_map_status(settings=None):
    """Return the calibration map status used by Studio exports."""
    if settings is None:
        settings = load_settings()

    configured = settings["general"].get("height_map_path")
    default_path = _default_height_map_path()
    source = "none"
    effective_path = None

    if configured:
        source = "configured"
        effective_path = os.path.abspath(os.path.expanduser(str(configured).strip()))
    elif os.path.isfile(default_path):
        source = "default"
        effective_path = default_path

    exists = bool(effective_path and os.path.isfile(effective_path))
    return {
        "height_map_configured_path": configured or "",
        "height_map_default_path": default_path,
        "height_map_effective_path": effective_path or "",
        "height_map_source": source,
        "height_map_exists": exists,
        "height_map_will_apply": exists,
    }

# Window control API for frameless windows
class WindowControlAPI:
    """API exposed to JavaScript for window control in frameless mode."""
    
    def __init__(self, window):
        self.window = window
    
    def minimize(self):
        """Minimize the window."""
        if self.window:
            self.window.minimize()
    
    def maximize(self):
        """Maximize/restore the window."""
        if self.window:
            # Toggle between maximize and restore
            # Note: pywebview doesn't have a direct toggle, so we'll use maximize/restore
            # For now, just maximize - you can enhance this to toggle
            self.window.maximize()
    
    def close(self):
        """Close the window."""
        if self.window:
            self.window.destroy()


def allowed_file(filename):
    """Check if file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    """Serve the main GUI page."""
    cache_bust = str(int(time.time()))
    # Check if we're in frameless mode (passed as query param)
    frameless_mode = request.args.get('frameless', 'false').lower() == 'true'
    return render_template("index.html", cache_bust=cache_bust, frameless_mode=frameless_mode)


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Get current plotter settings."""
    settings = load_settings()
    height_map_status = _height_map_status(settings)
    return jsonify(
        {
            "area_width": settings["general"]["area_width"],
            "area_height": settings["general"]["area_height"],
            "paper_gap": settings["general"].get("paper_gap", 30.0),
            "z_up_long": settings["general"]["z_up_long"],
            "z_up_short": settings["general"]["z_up_short"],
            "z_up_threshold": settings["general"]["z_up_threshold"],
            "z_down": settings["general"]["z_down"],
            "feed_rate_draw": settings["general"]["feed_rate_draw"],
            "feed_rate_travel": settings["general"]["feed_rate_travel"],
            "feed_rate_z": settings["general"]["feed_rate_z"],
            "registration_marks_length": settings["general"]["registration_marks_length"],
            "linemerge": settings["general"].get("linemerge", True),
            "reloop": settings["general"].get("reloop", False),
            "arc_fitting": settings["general"].get("arc_fitting", False),
            "arc_tolerance": settings["general"].get("arc_tolerance", 0.05),
            "path_sorting": settings["general"].get("path_sorting", True),
            "path_reversing": settings["general"].get("path_reversing", True),
            "height_map_path": settings["general"].get("height_map_path") or "",
            "papers": settings["papers"],
            **height_map_status,
        }
    )


@app.route("/api/settings", methods=["PUT"])
def update_settings():
    """Update plotter settings."""
    try:
        data = request.get_json()
        
        # Load current settings
        settings = load_settings()
        
        # Update general settings
        if "area_width" in data:
            settings["general"]["area_width"] = float(data["area_width"])
        if "area_height" in data:
            settings["general"]["area_height"] = float(data["area_height"])
        if "paper_gap" in data:
            settings["general"]["paper_gap"] = float(data["paper_gap"])
        if "z_up_long" in data:
            settings["general"]["z_up_long"] = float(data["z_up_long"])
        if "z_up_short" in data:
            settings["general"]["z_up_short"] = float(data["z_up_short"])
        if "z_up_threshold" in data:
            settings["general"]["z_up_threshold"] = float(data["z_up_threshold"])
        if "z_down" in data:
            settings["general"]["z_down"] = float(data["z_down"])
        if "feed_rate_draw" in data:
            settings["general"]["feed_rate_draw"] = int(data["feed_rate_draw"])
        if "feed_rate_travel" in data:
            settings["general"]["feed_rate_travel"] = int(data["feed_rate_travel"])
        if "feed_rate_z" in data:
            settings["general"]["feed_rate_z"] = int(data["feed_rate_z"])
        if "registration_marks_length" in data:
            settings["general"]["registration_marks_length"] = float(data["registration_marks_length"])
        if "linemerge" in data:
            settings["general"]["linemerge"] = bool(data["linemerge"])
        if "reloop" in data:
            settings["general"]["reloop"] = bool(data["reloop"])
        if "arc_fitting" in data:
            settings["general"]["arc_fitting"] = bool(data["arc_fitting"])
        if "arc_tolerance" in data:
            settings["general"]["arc_tolerance"] = float(data["arc_tolerance"])
        if "path_sorting" in data:
            settings["general"]["path_sorting"] = bool(data["path_sorting"])
        if "path_reversing" in data:
            settings["general"]["path_reversing"] = bool(data["path_reversing"])
        if "height_map_path" in data:
            hmp = data["height_map_path"]
            settings["general"]["height_map_path"] = (
                None if hmp is None or str(hmp).strip() == "" else str(hmp).strip()
            )
        
        # Save settings
        settings_path = save_settings(settings)
        
        return jsonify({
            "success": True,
            "message": "Settings updated successfully",
            "settings_path": settings_path
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route("/api/papers", methods=["GET"])
def get_papers():
    """Get available paper sizes."""
    settings = load_settings()
    return jsonify(settings["papers"])


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error."""
    return jsonify({"error": "File too large. Maximum size is 256MB."}), 413


@app.route("/api/add-svg", methods=["POST"])
def add_svg():
    """Upload and process an SVG file."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File must be an SVG"}), 400

    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        svg_id = str(uuid.uuid4())
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], f"{svg_id}_{filename}")

        # Ensure upload folder exists
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

        file.save(filepath)

        # Get SVG dimensions
        try:
            dimensions = get_svg_dimensions(filepath)
            # Ensure we got a tuple with 2 values
            if not isinstance(dimensions, tuple):
                raise ValueError(
                    f"get_svg_dimensions returned non-tuple: {type(dimensions)} - {dimensions}"
                )
            if len(dimensions) != 2:
                raise ValueError(
                    f"get_svg_dimensions returned tuple with wrong length: {len(dimensions)} - {dimensions}"
                )
            width, height = dimensions
        except ValueError as e:
            # Re-raise ValueError as-is (these are our validation errors)
            raise
        except Exception as e:
            raise ValueError(
                f"Failed to get SVG dimensions from {filepath}: {type(e).__name__}: {e}"
            )

        # Validate dimensions
        validate_svg_dimensions(width, height)

        # Generate PNG preview once and cache the path
        try:
            png_path = svg_to_png(filepath)
        except Exception as e:
            # If PNG generation fails, we can still continue with the SVG
            print(f"Warning: Failed to generate PNG preview: {e}")
            png_path = None

        # Calculate initial SVG scale (fit to paper, which defaults to SVG size)
        initial_scale = 1.0

        # Store SVG metadata
        svg_library[svg_id] = {
            "id": svg_id,
            "filename": filename,
            "filepath": filepath,
            "preview_png_path": png_path,  # Cached PNG path
            "width": width,
            "height": height,
            "paper_width": width,  # Default to SVG dimensions
            "paper_height": height,
            "paper_name": None,
            "svg_scale": initial_scale,  # Scale factor to fit SVG inside paper (auto-calculated)
            "x": 0,
            "y": 0,
        }

        return jsonify(
            {
                "id": svg_id,
                "filename": filename,
                "width": width,
                "height": height,
                "paper_width": width,
                "paper_height": height,
                "paper_name": None,
                "svg_scale": 1.0,
                "preview_url": f"/api/svg-preview/{svg_id}",
            }
        )

    except Exception as e:
        import traceback

        error_msg = str(e)
        traceback.print_exc()
        return jsonify({"error": f"Failed to process SVG: {error_msg}"}), 500


@app.route("/api/svg-preview/<svg_id>", methods=["GET"])
def get_svg_preview(svg_id):
    """Get PNG preview of an SVG."""
    if svg_id not in svg_library:
        return jsonify({"error": "SVG not found"}), 404

    try:
        svg_data = svg_library[svg_id]
        filepath = svg_data["filepath"]

        # Use cached PNG path; regenerate only if missing from disk
        png_path = svg_data.get("preview_png_path")
        if png_path and os.path.exists(png_path):
            return send_file(png_path, mimetype="image/png")

        # Cache miss: regenerate and store
        try:
            png_path = svg_to_png(filepath)
            svg_data["preview_png_path"] = png_path
        except Exception as e:
            print(f"Warning: Failed to regenerate PNG preview for {filepath}: {e}")
            png_path = None

        if png_path and os.path.exists(png_path):
            return send_file(png_path, mimetype="image/png")

        # Fallback: serve original SVG if PNG conversion fails
        if os.path.exists(filepath):
            return send_file(filepath, mimetype="image/svg+xml")

        return jsonify({"error": "Preview not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/add-paper", methods=["POST"])
def add_paper():
    """Add a paper to the canvas."""
    data = request.json
    paper_name = data.get("paper_name")
    orientation = data.get("orientation", "landscape")  # "landscape" or "portrait"

    settings = load_settings()

    if paper_name == "custom":
        # Custom paper - use provided dimensions
        paper_width = float(data.get("paper_width", 100))
        paper_height = float(data.get("paper_height", 100))
        paper_name = None
    else:
        # Find paper in settings
        paper = next((p for p in settings["papers"] if p["name"] == paper_name), None)
        if not paper:
            return jsonify({"error": "Paper not found"}), 404

        if orientation == "landscape":
            paper_width = paper["height"]
            paper_height = paper["width"]
        else:
            paper_width = paper["width"]
            paper_height = paper["height"]

    paper_id = str(uuid.uuid4())
    paper_store[paper_id] = {
        "id": paper_id,
        "paper_name": paper_name,
        "paper_width": paper_width,
        "paper_height": paper_height,
        "svg_id": None,  # SVG assigned to this paper
        "x": 0,
        "y": 0,
        "rotation": 0,
    }

    return jsonify(
        {
            "id": paper_id,
            "paper_name": paper_name,
            "paper_width": paper_width,
            "paper_height": paper_height,
            "svg_id": None,
            "x": 0,
            "y": 0,
            "rotation": 0,
        }
    )


@app.route("/api/update-paper", methods=["POST"])
def update_paper():
    """Update paper position or assigned SVG."""
    data = request.json
    paper_id = data.get("id")

    if paper_id not in paper_store:
        return jsonify({"error": "Paper not found"}), 404

    paper_data = paper_store[paper_id]

    # Update position
    if "x" in data:
        paper_data["x"] = float(data["x"])
    if "y" in data:
        paper_data["y"] = float(data["y"])

    # Update assigned SVG
    if "svg_id" in data:
        svg_id = data["svg_id"]
        if svg_id and svg_id not in svg_library:
            return jsonify({"error": "SVG not found in library"}), 404
        paper_data["svg_id"] = svg_id if svg_id else None
        # Auto-fit SVG to paper when assigned
        if svg_id:
            _fit_svg_to_paper(paper_data, svg_library[svg_id])

    # Update paper size (if changed)
    if "paper_width" in data:
        paper_data["paper_width"] = float(data["paper_width"])
        if paper_data["svg_id"]:
            _fit_svg_to_paper(paper_data, svg_library[paper_data["svg_id"]])
    if "paper_height" in data:
        paper_data["paper_height"] = float(data["paper_height"])
        if paper_data["svg_id"]:
            _fit_svg_to_paper(paper_data, svg_library[paper_data["svg_id"]])
    if "paper_name" in data:
        paper_data["paper_name"] = data["paper_name"]

    if "rotation" in data:
        paper_data["rotation"] = int(data["rotation"])
    if "locked" in data:
        paper_data["locked"] = bool(data["locked"])
    return jsonify({"success": True, "paper": paper_data})


@app.route("/api/select-output-folder", methods=["POST"])
def select_output_folder():
    """Open a native folder picker on macOS and return the selected path."""
    try:
        if platform.system() != "Darwin":
            return jsonify({"error": "Native picker not supported on this OS"}), 400

        result = subprocess.run(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Select export folder")',
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        folder = result.stdout.strip()
        if result.returncode != 0:
            return (
                jsonify({"error": result.stderr.strip() or "Folder picker canceled"}),
                400,
            )

        return jsonify({"output_folder": folder})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _fit_svg_to_paper(paper_data, svg_data):
    """Fit SVG to paper size, maintaining aspect ratio. SVG must fit INSIDE paper."""
    svg_width = svg_data.get("width", 1)
    svg_height = svg_data.get("height", 1)
    paper_width = paper_data.get("paper_width", svg_width)
    paper_height = paper_data.get("paper_height", svg_height)

    if svg_width <= 0 or svg_height <= 0 or paper_width <= 0 or paper_height <= 0:
        paper_data["svg_scale"] = 1.0
        return

    # Calculate scale to fit SVG inside paper (maintain aspect ratio)
    scale_x = paper_width / svg_width
    scale_y = paper_height / svg_height
    scale = min(scale_x, scale_y)  # Use smaller scale to fit inside

    paper_data["svg_scale"] = scale


@app.route("/api/list-svgs", methods=["GET"])
def list_svgs():
    """Get list of all SVGs in the library."""
    svgs = []
    for svg_id, svg_data in svg_library.items():
        svgs.append(
            {
                "id": svg_data["id"],
                "filename": svg_data["filename"],
                "width": svg_data["width"],
                "height": svg_data["height"],
                "preview_url": f"/api/svg-preview/{svg_id}",
            }
        )
    return jsonify(svgs)


@app.route("/api/list-papers", methods=["GET"])
def list_papers():
    """Get list of all papers on the canvas."""
    papers = []
    for paper_id, paper_data in paper_store.items():
        paper_info = {
            "id": paper_data["id"],
            "paper_name": paper_data.get("paper_name"),
            "paper_width": paper_data["paper_width"],
            "paper_height": paper_data["paper_height"],
            "svg_id": paper_data.get("svg_id"),
            "svg_scale": paper_data.get("svg_scale", 1.0),
            "x": paper_data["x"],
            "y": paper_data["y"],
            "rotation": paper_data.get("rotation", 0),
            "locked": paper_data.get("locked", False),
        }
        # Include SVG info if assigned
        if paper_data.get("svg_id"):
            svg_id = paper_data["svg_id"]
            if svg_id in svg_library:
                svg_data = svg_library[svg_id]
                paper_info["svg"] = {
                    "id": svg_data["id"],
                    "filename": svg_data["filename"],
                    "width": svg_data["width"],
                    "height": svg_data["height"],
                    "preview_url": f"/api/svg-preview/{svg_id}",
                }
        papers.append(paper_info)
    return jsonify(papers)


@app.route("/api/clone-paper/<paper_id>", methods=["POST"])
def clone_paper(paper_id):
    """Clone a paper (with its assigned SVG) to create a duplicate on the canvas."""
    if paper_id not in paper_store:
        return jsonify({"error": "Paper not found"}), 404

    original_paper = paper_store[paper_id]

    # Create new paper with same properties
    new_paper_id = str(uuid.uuid4())
    paper_store[new_paper_id] = {
        "id": new_paper_id,
        "paper_name": original_paper.get("paper_name"),
        "paper_width": original_paper["paper_width"],
        "paper_height": original_paper["paper_height"],
        "svg_id": original_paper.get("svg_id"),  # Same SVG assigned
        "svg_scale": original_paper.get("svg_scale", 1.0),
        "x": original_paper["x"] + 50,  # Offset slightly
        "y": original_paper["y"] + 50,
        "rotation": original_paper.get("rotation", 0),
    }

    return jsonify(
        {
            "id": new_paper_id,
            "paper_name": paper_store[new_paper_id].get("paper_name"),
            "paper_width": paper_store[new_paper_id]["paper_width"],
            "paper_height": paper_store[new_paper_id]["paper_height"],
            "svg_id": paper_store[new_paper_id].get("svg_id"),
            "svg_scale": paper_store[new_paper_id].get("svg_scale", 1.0),
            "x": paper_store[new_paper_id]["x"],
            "y": paper_store[new_paper_id]["y"],
            "rotation": paper_store[new_paper_id].get("rotation", 0),
        }
    )


@app.route("/api/remove-paper/<paper_id>", methods=["DELETE"])
def remove_paper(paper_id):
    """Remove a paper from the canvas."""
    if paper_id not in paper_store:
        return jsonify({"error": "Paper not found"}), 404

    del paper_store[paper_id]
    return jsonify({"success": True})


@app.route("/api/remove-svg/<svg_id>", methods=["DELETE"])
def remove_svg(svg_id):
    """Remove an SVG from the library. Unassigns papers that have this SVG instead of removing them."""
    if svg_id not in svg_library:
        return jsonify({"error": "SVG not found"}), 404

    # Unassign papers that use this SVG
    unassigned_paper_ids = []
    for paper in paper_store.values():
        if paper.get("svg_id") == svg_id:
            paper["svg_id"] = None
            unassigned_paper_ids.append(paper["id"])

    svg_data = svg_library[svg_id]
    filepath = svg_data["filepath"]

    # Clean up files
    try:
        # Delete SVG file
        if os.path.exists(filepath):
            os.remove(filepath)

        # Delete cached PNG preview if it exists
        png_path = svg_data.get("preview_png_path")
        if png_path and os.path.exists(png_path):
            os.remove(png_path)
    except Exception:
        pass  # Ignore cleanup errors

    del svg_library[svg_id]
    return jsonify({
        "success": True,
        "unassigned_paper_ids": unassigned_paper_ids
    })


@app.route("/api/clear-all", methods=["POST"])
def clear_all():
    """Clear all papers and SVGs from the canvas and library."""
    # Count items before clearing
    paper_count = len(paper_store)
    svg_count = len(svg_library)
    
    # Clean up SVG files
    for svg_id, svg_data in list(svg_library.items()):
        filepath = svg_data.get("filepath")
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass  # Ignore cleanup errors
        # Remove cached PNG preview
        png_path = svg_data.get("preview_png_path")
        if png_path and os.path.exists(png_path):
            try:
                os.remove(png_path)
            except Exception:
                pass
    
    # Clear all data
    paper_store.clear()
    svg_library.clear()
    
    return jsonify({
        "success": True,
        "papers_removed": paper_count,
        "svgs_removed": svg_count
    })


def generate_stats_file(
    stats_path: str,
    export_svgs: list,
    gcode_files: list,
    canvas_width: float,
    canvas_height: float,
):
    """
    Generate a stats.txt file with export statistics.
    
    Args:
        stats_path: Path to save the stats file
        export_svgs: List of SVG export entries with paper info
        gcode_files: List of generated G-code file paths
        canvas_width: Canvas width in mm
        canvas_height: Canvas height in mm
    """
    lines = []
    lines.append("=" * 60)
    lines.append("EXPORT STATISTICS")
    lines.append("=" * 60)
    lines.append("")
    
    # Operations section
    lines.append("OPERATIONS")
    lines.append("-" * 60)
    lines.append(f"Canvas Size: {canvas_width:.1f}mm × {canvas_height:.1f}mm")
    lines.append(f"Total Papers: {len(export_svgs)}")
    unique_svgs = set()
    for svg in export_svgs:
        filename = svg.get('filename')
        if filename:
            unique_svgs.add(filename)
    lines.append(f"Total SVGs: {len(unique_svgs)}")
    lines.append("")
    
    # Papers and transformations
    lines.append("Papers and Transformations:")
    for idx, svg_entry in enumerate(export_svgs, 1):
        paper_name = svg_entry.get("paper_name") or "Custom"
        filename = svg_entry.get("filename", "unknown.svg")
        x = svg_entry.get("x", 0)
        y = svg_entry.get("y", 0)
        paper_width = svg_entry.get("paper_width", 0)
        paper_height = svg_entry.get("paper_height", 0)
        svg_scale = svg_entry.get("svg_scale", 1.0)
        rotation = svg_entry.get("rotation", 0)
        
        lines.append(f"  Paper {idx}: {paper_name}")
        lines.append(f"    SVG: {filename}")
        lines.append(f"    Paper Size: {paper_width:.1f}mm × {paper_height:.1f}mm")
        lines.append(f"    Position: ({x:.2f}mm, {y:.2f}mm)")
        lines.append(f"    Scale: {svg_scale:.4f}")
        lines.append(f"    Rotation: {rotation:.1f}°")
        lines.append("")
    
    lines.append("")
    lines.append("=" * 60)
    lines.append("G-CODE STATISTICS BY COLOR")
    lines.append("=" * 60)
    lines.append("")
    
    # Get feed rate settings for time estimation
    settings = load_settings()
    feed_rate_draw = settings["general"].get("feed_rate_draw", 4000)
    feed_rate_travel = settings["general"].get("feed_rate_travel", 6000)
    feed_rate_z = settings["general"].get("feed_rate_z", 1500)
    z_up = settings["general"].get("z_up_long", 12)
    z_down = settings["general"].get("z_down", 0)
    
    # Calculate stats for each G-code file (exclude guide.gcode)
    color_stats = []
    total_travel_mm = 0.0
    total_draw_mm = 0.0
    total_pen_lifts = 0
    total_segments = 0
    
    for gcode_file in gcode_files:
        if not os.path.exists(gcode_file):
            continue
        # Skip guide.gcode files
        if "guide.gcode" in gcode_file.lower():
            continue
            
        stats = calculate_gcode_stats(gcode_file)
        color_name = stats.get("color_name") or "unknown"
        hex_code = stats.get("hex_code") or "000000"
        draw_mm = stats.get("draw_distance_mm", 0.0)
        travel_mm = stats.get("travel_distance_mm", 0.0)
        pen_lifts = stats.get("num_pen_lifts", 0)
        segments = stats.get("num_segments", 0)
        total_mm = draw_mm + travel_mm
        
        # Calculate estimated time
        estimated_time_min = estimate_draw_time(
            draw_mm, travel_mm, pen_lifts,
            feed_rate_draw, feed_rate_travel, feed_rate_z,
            z_up, z_down
        )
        
        # Calculate average segment length
        avg_segment_length = draw_mm / segments if segments > 0 else 0.0
        
        color_stats.append({
            "color_name": color_name,
            "hex_code": hex_code,
            "draw_mm": draw_mm,
            "travel_mm": travel_mm,
            "total_mm": total_mm,
            "pen_lifts": pen_lifts,
            "segments": segments,
            "estimated_time_min": estimated_time_min,
            "avg_segment_length": avg_segment_length,
        })
        
        total_travel_mm += travel_mm
        total_draw_mm += draw_mm
        total_pen_lifts += pen_lifts
        total_segments += segments
    
    # Sort by color name for consistent output
    color_stats.sort(key=lambda x: x["color_name"])
    
    # Calculate total estimated time
    total_estimated_time_min = estimate_draw_time(
        total_draw_mm, total_travel_mm, total_pen_lifts,
        feed_rate_draw, feed_rate_travel, feed_rate_z,
        z_up, z_down
    )
    
    # Print per-color stats - Distance table
    lines.append("Distance Statistics:")
    lines.append(f"{'Color':<20} {'Travel':>20} {'Draw':>20} {'Total':>20}")
    lines.append("-" * 80)
    
    for stat in color_stats:
        color_display = f"{stat['color_name']} (#{stat['hex_code']})"
        travel_str = format_distance(stat['travel_mm'])
        draw_str = format_distance(stat['draw_mm'])
        total_str = format_distance(stat['total_mm'])
        lines.append(
            f"{color_display:<20} {travel_str:>20} {draw_str:>20} {total_str:>20}"
        )
    
    lines.append("-" * 80)
    total_travel_str = format_distance(total_travel_mm)
    total_draw_str = format_distance(total_draw_mm)
    total_distance_str = format_distance(total_travel_mm + total_draw_mm)
    lines.append(f"{'TOTAL':<20} {total_travel_str:>20} {total_draw_str:>20} {total_distance_str:>20}")
    lines.append("")
    
    # Print per-color stats - Pen operations
    lines.append("Pen Operations:")
    lines.append(f"{'Color':<20} {'Pen Lifts':>15} {'Segments':>15} {'Avg Seg':>20}")
    lines.append("-" * 70)
    
    for stat in color_stats:
        color_display = f"{stat['color_name']} (#{stat['hex_code']})"
        avg_seg_str = format_distance(stat['avg_segment_length'])
        lines.append(
            f"{color_display:<20} {stat['pen_lifts']:>15,} "
            f"{stat['segments']:>15,} {avg_seg_str:>20}"
        )
    
    lines.append("-" * 70)
    avg_segment_length_total = total_draw_mm / total_segments if total_segments > 0 else 0.0
    avg_seg_total_str = format_distance(avg_segment_length_total)
    lines.append(f"{'TOTAL':<20} {total_pen_lifts:>15,} {total_segments:>15,} {avg_seg_total_str:>20}")
    lines.append("")
    
    # Print per-color stats - Time estimates
    lines.append("Estimated Time:")
    lines.append(f"{'Color':<20} {'Estimated Time':>30}")
    lines.append("-" * 60)
    
    for stat in color_stats:
        color_display = f"{stat['color_name']} (#{stat['hex_code']})"
        time_str = format_time(stat['estimated_time_min'])
        lines.append(f"{color_display:<20} {time_str:>30}")
    
    lines.append("-" * 60)
    total_time_str = format_time(total_estimated_time_min)
    lines.append(f"{'TOTAL':<20} {total_time_str:>30}")
    lines.append("")
    
    # Summary statistics
    lines.append("=" * 60)
    lines.append("SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Total Colors: {len(color_stats)}")
    lines.append(f"Total Pen Lifts: {total_pen_lifts:,}")
    lines.append(f"Total Segments: {total_segments:,}")
    lines.append(f"Total Travel Distance: {format_distance(total_travel_mm)}")
    lines.append(f"Total Draw Distance: {format_distance(total_draw_mm)}")
    lines.append(f"Total Distance: {format_distance(total_travel_mm + total_draw_mm)}")
    if total_segments > 0:
        lines.append(f"Average Segment Length: {format_distance(avg_segment_length_total)}")
    lines.append(f"Estimated Total Time: {total_time_str}")
    lines.append("")
    lines.append("=" * 60)
    
    # Write to file
    with open(stats_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


@app.route("/api/auto-arrange", methods=["POST"])
def auto_arrange():
    """Auto-arrange papers on the canvas."""
    settings = load_settings()
    canvas_width = settings["general"]["area_width"]
    canvas_height = settings["general"]["area_height"]

    papers = list(paper_store.values())
    if not papers:
        return jsonify({"error": "No papers to arrange"}), 400

    gap = float(settings["general"].get("paper_gap", 30.0))

    if len(papers) == 1:
        # Center single paper
        paper = papers[0]
        paper["x"] = (canvas_width - paper["paper_width"]) / 2
        paper["y"] = (canvas_height - paper["paper_height"]) / 2
    else:
        n = len(papers)
        max_paper_w = max(p["paper_width"] for p in papers)
        max_paper_h = max(p["paper_height"] for p in papers)

        # Try a single row first; fall back to a grid if it doesn't fit.
        row_w = n * max_paper_w + (n - 1) * gap
        if row_w <= canvas_width and max_paper_h <= canvas_height:
            cols = n
        else:
            # Find the grid closest to the canvas aspect ratio that fits.
            canvas_ratio = canvas_width / canvas_height if canvas_height else 1.0
            best_cols = 1
            best_score = float("inf")
            for c in range(1, n + 1):
                r = math.ceil(n / c)
                layout_w = c * max_paper_w + (c - 1) * gap
                layout_h = r * max_paper_h + (r - 1) * gap
                if layout_w > canvas_width or layout_h > canvas_height:
                    continue
                score = abs((layout_w / layout_h if layout_h else 1.0) - canvas_ratio)
                if score < best_score:
                    best_score = score
                    best_cols = c
            cols = best_cols

        rows = math.ceil(n / cols)
        total_w = cols * max_paper_w + (cols - 1) * gap
        total_h = rows * max_paper_h + (rows - 1) * gap
        start_x = (canvas_width - total_w) / 2
        start_y = (canvas_height - total_h) / 2

        for i, paper in enumerate(papers):
            col = i % cols
            row = i // cols
            paper["x"] = start_x + col * (max_paper_w + gap)
            paper["y"] = start_y + row * (max_paper_h + gap)

    return jsonify({"success": True, "papers": list(paper_store.values())})


@app.route("/api/auto-assign-svgs", methods=["POST"])
def auto_assign_svgs():
    """Assign one SVG per paper when counts match."""
    papers = list(paper_store.values())
    svgs = list(svg_library.values())

    if not papers:
        return jsonify({"error": "No papers available"}), 400
    if not svgs:
        return jsonify({"error": "No SVGs available"}), 400
    if len(papers) != len(svgs):
        return jsonify({"error": "Paper and SVG counts must match"}), 400

    for paper, svg in zip(papers, svgs):
        paper["svg_id"] = svg["id"]
        _fit_svg_to_paper(paper, svg)

    return jsonify({"success": True, "papers": list(paper_store.values())})


@app.route("/api/align-papers", methods=["POST"])
def align_papers():
    """Align/distribute papers relative to their bounding box."""
    data = request.json
    action = data.get("action")
    paper_ids = data.get("paper_ids", [])

    # Use specified papers or all papers
    if paper_ids:
        papers = [paper_store[pid] for pid in paper_ids if pid in paper_store]
    else:
        papers = list(paper_store.values())

    if not papers:
        return jsonify({"error": "No papers to align"}), 400

    if len(papers) < 2 and action in ("distribute_h", "distribute_v"):
        return jsonify({"error": "Need at least 2 papers to distribute"}), 400

    # Calculate bounding box of all selected papers
    min_x = min(p["x"] for p in papers)
    min_y = min(p["y"] for p in papers)
    max_x = max(p["x"] + p["paper_width"] for p in papers)
    max_y = max(p["y"] + p["paper_height"] for p in papers)
    bbox_width = max_x - min_x
    bbox_height = max_y - min_y

    if action == "align_left":
        for p in papers:
            p["x"] = min_x
    elif action == "align_right":
        for p in papers:
            p["x"] = max_x - p["paper_width"]
    elif action == "align_top":
        for p in papers:
            p["y"] = min_y
    elif action == "align_bottom":
        for p in papers:
            p["y"] = max_y - p["paper_height"]
    elif action == "center_h":
        center_x = (min_x + max_x) / 2
        for p in papers:
            p["x"] = center_x - p["paper_width"] / 2
    elif action == "center_v":
        center_y = (min_y + max_y) / 2
        for p in papers:
            p["y"] = center_y - p["paper_height"] / 2
    elif action == "distribute_h":
        papers_sorted = sorted(papers, key=lambda p: p["x"])
        total_paper_w = sum(p["paper_width"] for p in papers_sorted)
        gap = (bbox_width - total_paper_w) / (len(papers_sorted) - 1) if len(papers_sorted) > 1 else 0
        cursor = min_x
        for p in papers_sorted:
            p["x"] = cursor
            cursor += p["paper_width"] + gap
    elif action == "distribute_v":
        papers_sorted = sorted(papers, key=lambda p: p["y"])
        total_paper_h = sum(p["paper_height"] for p in papers_sorted)
        gap = (bbox_height - total_paper_h) / (len(papers_sorted) - 1) if len(papers_sorted) > 1 else 0
        cursor = min_y
        for p in papers_sorted:
            p["y"] = cursor
            cursor += p["paper_height"] + gap
    else:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    return jsonify({"success": True, "papers": list(paper_store.values())})


@app.route("/api/bulk-update-papers", methods=["POST"])
def bulk_update_papers():
    """Bulk update paper positions/rotations (used for undo/redo)."""
    data = request.json
    papers_data = data.get("papers", [])

    for paper_update in papers_data:
        paper_id = paper_update.get("id")
        if paper_id not in paper_store:
            continue
        paper = paper_store[paper_id]
        if "x" in paper_update:
            paper["x"] = float(paper_update["x"])
        if "y" in paper_update:
            paper["y"] = float(paper_update["y"])
        if "rotation" in paper_update:
            paper["rotation"] = int(paper_update["rotation"])
        if "svg_id" in paper_update:
            paper["svg_id"] = paper_update["svg_id"]
        if "locked" in paper_update:
            paper["locked"] = bool(paper_update["locked"])

    return jsonify({"success": True, "papers": list(paper_store.values())})


def _validate_export_papers():
    """Build export list from papers with assigned SVGs. Returns list of export entries or raises."""
    export_svgs = []
    for paper in paper_store.values():
        svg_id = paper.get("svg_id")
        if not svg_id:
            continue
        svg_data = svg_library.get(svg_id)
        if not svg_data:
            continue
        export_entry = {
            **svg_data,
            "x": paper.get("x", 0),
            "y": paper.get("y", 0),
            "paper_width": paper.get("paper_width", svg_data.get("width", 0)),
            "paper_height": paper.get("paper_height", svg_data.get("height", 0)),
            "paper_name": paper.get("paper_name"),
            "svg_scale": paper.get("svg_scale", 1.0),
            "rotation": paper.get("rotation", 0),
        }
        export_svgs.append(export_entry)
    return export_svgs


def _run_export_pipeline(export_svgs, output_folder, settings):
    """Run SVG combine + gcode pipeline. Returns dict with file paths."""
    canvas_width = settings["general"]["area_width"]
    canvas_height = settings["general"]["area_height"]

    print(f"EXPORT: Combining {len(export_svgs)} SVG(s) into combined.svg...")
    combined_svg_path = os.path.join(output_folder, "combined.svg")
    generate_combined_svg(export_svgs, canvas_width, canvas_height, combined_svg_path)

    print(f"EXPORT: Running vpype to generate G-code...")
    gcode_files = process_svg_to_gcode(
        combined_svg_path, canvas_width, canvas_height, output_folder
    )

    print(f"EXPORT: Generating guide G-code...")
    guide_gcode_path = os.path.join(output_folder, "guide.gcode")
    generate_guide_gcode(list(paper_store.values()), guide_gcode_path, settings)

    print(f"EXPORT: Generating stats.txt...")
    stats_path = os.path.join(output_folder, "stats.txt")
    generate_stats_file(stats_path, export_svgs, gcode_files, canvas_width, canvas_height)

    return {
        "combined_svg": combined_svg_path,
        "gcode_files": gcode_files,
        "guide_gcode": guide_gcode_path,
        "stats": stats_path,
    }


def _build_export_response(output_folder, pipeline_result):
    """Build the JSON response dict for a successful export."""
    return {
        "success": True,
        "output_folder": output_folder,
        "combined_svg": pipeline_result["combined_svg"],
        "gcode_files": pipeline_result["gcode_files"],
        "guide_gcode": pipeline_result["guide_gcode"],
        "stats": pipeline_result["stats"],
    }


@app.route("/api/export", methods=["POST"])
def export():
    """Export canvas to combined SVG and G-code files."""
    data = request.json
    output_folder = data.get("output_folder")

    if not output_folder:
        output_folder = tempfile.mkdtemp(prefix="plotter_export_")

    # Log output location
    print(f"\n{'='*60}")
    print(f"EXPORT: Output folder: {output_folder}")
    print(f"{'='*60}")

    try:
        export_svgs = _validate_export_papers()
        if not export_svgs:
            return jsonify({"error": "No assigned SVGs to export"}), 400

        settings = load_settings()
        pipeline_result = _run_export_pipeline(export_svgs, output_folder, settings)

        # Log all generated files
        print(f"EXPORT: Generated files:")
        print(f"  - Combined SVG: {pipeline_result['combined_svg']}")
        print(f"  - Guide G-code: {pipeline_result['guide_gcode']}")
        print(f"  - Stats: {pipeline_result['stats']}")
        for gcode_file in pipeline_result["gcode_files"]:
            print(f"  - G-code: {gcode_file}")
        print(f"{'='*60}\n")

        return jsonify(_build_export_response(output_folder, pipeline_result))

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Surface calibration API routes ---


def _height_map_path():
    """Return the single height map file path (next to settings.yaml)."""
    return _default_height_map_path()


@app.route("/api/surface-cal/grid-info", methods=["GET"])
def surface_cal_grid_info():
    """Return grid dimensions for a given spacing."""
    settings = load_settings()
    g = settings["general"]
    spacing = float(request.args.get("spacing", 30))
    nx, ny, x_coords, y_coords = grid_dimensions(g["area_width"], g["area_height"], spacing)
    return jsonify({
        "nx": nx,
        "ny": ny,
        "x_coords": x_coords,
        "y_coords": y_coords,
        "area_width": g["area_width"],
        "area_height": g["area_height"],
    })


@app.route("/api/surface-cal/grid", methods=["POST"])
def surface_cal_grid():
    """Generate calibration grid G-code and save to file."""
    data = request.get_json()
    output_folder = data.get("output_folder")
    spacing = float(data.get("spacing", 30))
    cross_size = float(data.get("cross_size", 4))
    apply_map = bool(data.get("apply_map"))

    if not output_folder:
        return jsonify({"error": "No output folder specified"}), 400

    settings = load_settings()
    g = settings["general"]
    aw, ah = g["area_width"], g["area_height"]

    body = generate_calibration_grid_gcode(
        aw, ah,
        grid_spacing_mm=spacing,
        cross_size_mm=cross_size,
        z_up=float(g.get("z_up_long", 12)),
        z_down=float(g.get("z_down", 0)),
        feed_rate_draw=float(g.get("feed_rate_draw", 3000)),
        feed_rate_travel=float(g.get("feed_rate_travel", 6000)),
        feed_rate_z=float(g.get("feed_rate_z", 1500)),
    )

    if apply_map:
        hm_path = _height_map_path()
        if not os.path.isfile(hm_path):
            return jsonify({"error": "No saved height map to apply"}), 400
        hmap = HeightMap.from_json_file(hm_path)
        body = apply_height_map_to_gcode_text(
            body, hmap, z_down_base=float(g.get("z_down", 0))
        )

    filename = f"surface_cal_grid_{aw:.0f}x{ah:.0f}.gcode"
    out_path = os.path.join(output_folder, filename)
    os.makedirs(output_folder, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(body)

    return jsonify({"success": True, "path": out_path})


@app.route("/api/surface-cal/map", methods=["GET"])
def surface_cal_get_map():
    """Load the saved height map."""
    fpath = _height_map_path()
    if not os.path.isfile(fpath):
        return jsonify({"exists": False})
    try:
        data = load_height_map_json(fpath)
        data["exists"] = True
        data["path"] = fpath
        data["will_apply"] = _height_map_status()["height_map_will_apply"]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/surface-cal/map", methods=["PUT"])
def surface_cal_save_map():
    """Save the height map (overwrites the single file) and activate in settings."""
    map_data = request.get_json()
    if not map_data:
        return jsonify({"error": "No map data provided"}), 400

    fpath = _height_map_path()
    try:
        save_height_map_json(fpath, map_data)
        settings = load_settings()
        settings["general"]["height_map_path"] = fpath
        save_settings(settings)
        return jsonify({"success": True, "path": fpath})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/surface-cal/map", methods=["DELETE"])
def surface_cal_delete_map():
    """Delete the height map and clear from settings."""
    fpath = _height_map_path()
    if os.path.isfile(fpath):
        os.remove(fpath)
    settings = load_settings()
    settings["general"]["height_map_path"] = None
    save_settings(settings)
    return jsonify({"success": True})


def run_gui(
    host="127.0.0.1",
    port=5000,
    debug=False,
    native_window=False,
    frameless=False,
    vibrancy=False,
):
    """
    Run the Flask GUI application.
    
    Args:
        host: Host to bind the server to
        port: Port to bind the server to
        debug: Enable debug mode
        native_window: If True, open in a native window instead of browser
        frameless: If True, remove the title bar (creates frameless window)
        vibrancy: If True, enable macOS vibrancy effect (macOS only)
    """
    import threading
    import webbrowser
    
    url = f"http://{host}:{port}"
    
    if native_window:
        try:
            import webview
            
            print(f"Starting Plotter Studio GUI in native window...")
            
            # Start Flask server in a separate thread
            def run_flask():
                app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)
            
            server_thread = threading.Thread(target=run_flask, daemon=True)
            server_thread.start()
            
            # Wait a moment for server to start
            time.sleep(0.5)
            
            # Create native window
            # Add frameless query param if in frameless mode
            window_url = url
            if frameless:
                window_url = f"{url}?frameless=true"
            
            window_kwargs = {
                "title": "Plotter Studio",
                "url": window_url,
                "width": 1400,
                "height": 900,
                "min_size": (1000, 600),
                "resizable": True,
            }
            
            # Add frameless option
            if frameless:
                window_kwargs["frameless"] = True
                window_kwargs["easy_drag"] = False  # We'll use custom drag regions instead
                # Create window control API and expose it
                window_control_api = WindowControlAPI(None)  # Will be set after window creation
                window_kwargs["js_api"] = window_control_api
            
            # Add vibrancy option (macOS only)
            if vibrancy and platform.system() == "Darwin":
                window_kwargs["vibrancy"] = True
            
            # Create window
            window = webview.create_window(**window_kwargs)
            
            # Set window reference in API if frameless
            if frameless and window_control_api:
                window_control_api.window = window
            
            # Set icon via webview.start() for GTK/QT backends (not macOS)
            start_kwargs = {"debug": debug}
            
            # Start webview (this blocks until window is closed)
            webview.start(**start_kwargs)
            
        except ImportError:
            print("Warning: pywebview not installed. Falling back to browser mode.")
            print(f"Install it with: pip install pywebview")
            print(f"Starting Plotter Studio GUI...")
            print(f"Open your browser to: {url}")
            try:
                app.run(host=host, port=port, debug=debug, threaded=True)
            except Exception as e:
                print(f"Error starting server: {e}")
                raise
        except Exception as e:
            print(f"Error starting native window: {e}")
            print(f"Falling back to browser mode. Open your browser to: {url}")
            try:
                app.run(host=host, port=port, debug=debug, threaded=True)
            except Exception as e:
                print(f"Error starting server: {e}")
                raise
    else:
        print(f"Starting Plotter Studio GUI...")
        print(f"Open your browser to: {url}")
        try:
            # Try to open browser automatically
            webbrowser.open(url)
        except Exception:
            pass
        try:
            app.run(host=host, port=port, debug=debug, threaded=True)
        except Exception as e:
            print(f"Error starting server: {e}")
            raise
