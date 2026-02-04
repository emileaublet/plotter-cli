"""
Flask application for the Plotter GUI.
Provides a web-based interface for arranging multiple SVGs on a canvas.
"""

import os
import time
import json
import platform
import subprocess
import tempfile
import platform
import subprocess
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from .utils import (
    load_settings,
    get_svg_dimensions,
    calculate_gcode_stats,
    estimate_draw_time,
    format_time,
)
from .gui_utils import (
    svg_to_png,
    generate_combined_svg,
    generate_guide_gcode,
    process_svg_to_gcode,
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
    import time
    cache_bust = str(int(time.time()))
    # Check if we're in frameless mode (passed as query param)
    frameless_mode = request.args.get('frameless', 'false').lower() == 'true'
    return render_template("index.html", cache_bust=cache_bust, frameless_mode=frameless_mode)


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Get current plotter settings."""
    settings = load_settings()
    return jsonify(
        {
            "area_width": settings["general"]["area_width"],
            "area_height": settings["general"]["area_height"],
            "papers": settings["papers"],
        }
    )


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
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid SVG dimensions: {width}mm × {height}mm")

        # Generate PNG preview
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
        png_path = svg_to_png(filepath)

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
    """Remove an SVG from the library. Also removes papers that have this SVG assigned."""
    if svg_id not in svg_library:
        return jsonify({"error": "SVG not found"}), 404

    # Find papers using this SVG
    papers_using_svg = [p for p in paper_store.values() if p.get("svg_id") == svg_id]
    paper_ids_to_remove = [p["id"] for p in papers_using_svg]

    # Remove papers that have this SVG assigned
    for paper_id in paper_ids_to_remove:
        if paper_id in paper_store:
            del paper_store[paper_id]

    svg_data = svg_library[svg_id]
    filepath = svg_data["filepath"]

    # Clean up files
    try:
        # Get PNG path before deleting SVG file
        png_path = None
        if os.path.exists(filepath):
            try:
                png_path = svg_to_png(filepath)
            except Exception:
                pass  # PNG path generation might fail
        
        # Delete SVG file
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Delete PNG preview if it exists
        if png_path and os.path.exists(png_path):
            os.remove(png_path)
    except Exception:
        pass  # Ignore cleanup errors

    del svg_library[svg_id]
    return jsonify({
        "success": True,
        "papers_removed": len(paper_ids_to_remove),
        "paper_ids": paper_ids_to_remove
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
                # Try to remove PNG preview
                try:
                    png_path = svg_to_png(filepath)
                    if png_path and os.path.exists(png_path):
                        os.remove(png_path)
                except Exception:
                    pass
            except Exception:
                pass  # Ignore cleanup errors
    
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
    lines.append(f"{'Color':<20} {'Travel (mm)':>15} {'Draw (mm)':>15} {'Total (mm)':>15}")
    lines.append("-" * 60)
    
    for stat in color_stats:
        color_display = f"{stat['color_name']} (#{stat['hex_code']})"
        lines.append(
            f"{color_display:<20} {stat['travel_mm']:>15.2f} "
            f"{stat['draw_mm']:>15.2f} {stat['total_mm']:>15.2f}"
        )
    
    lines.append("-" * 60)
    lines.append(f"{'TOTAL':<20} {total_travel_mm:>15.2f} {total_draw_mm:>15.2f} {total_travel_mm + total_draw_mm:>15.2f}")
    lines.append("")
    
    # Print per-color stats - Pen operations
    lines.append("Pen Operations:")
    lines.append(f"{'Color':<20} {'Pen Lifts':>15} {'Segments':>15} {'Avg Seg (mm)':>15}")
    lines.append("-" * 60)
    
    for stat in color_stats:
        color_display = f"{stat['color_name']} (#{stat['hex_code']})"
        lines.append(
            f"{color_display:<20} {stat['pen_lifts']:>15} "
            f"{stat['segments']:>15} {stat['avg_segment_length']:>15.2f}"
        )
    
    lines.append("-" * 60)
    avg_segment_length_total = total_draw_mm / total_segments if total_segments > 0 else 0.0
    lines.append(f"{'TOTAL':<20} {total_pen_lifts:>15} {total_segments:>15} {avg_segment_length_total:>15.2f}")
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
    lines.append(f"Total Pen Lifts: {total_pen_lifts}")
    lines.append(f"Total Segments: {total_segments}")
    lines.append(f"Total Travel Distance: {total_travel_mm:.2f}mm")
    lines.append(f"Total Draw Distance: {total_draw_mm:.2f}mm")
    lines.append(f"Total Distance: {total_travel_mm + total_draw_mm:.2f}mm")
    if total_segments > 0:
        lines.append(f"Average Segment Length: {avg_segment_length_total:.2f}mm")
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

    gap = 30.0  # 30mm gap between papers

    if len(papers) == 1:
        # Center single paper
        paper = papers[0]
        paper["x"] = (canvas_width - paper["paper_width"]) / 2
        paper["y"] = (canvas_height - paper["paper_height"]) / 2
    else:
        # Arrange multiple papers in a row, centered
        total_width = 0
        max_height = 0

        for paper in papers:
            total_width += paper["paper_width"]
            if paper["paper_height"] > max_height:
                max_height = paper["paper_height"]

        # Add gaps
        total_width += gap * (len(papers) - 1)

        # Calculate starting X position to center the group
        start_x = (canvas_width - total_width) / 2
        start_y = (canvas_height - max_height) / 2

        # Position each paper
        current_x = start_x
        for paper in papers:
            paper["x"] = current_x
            paper["y"] = start_y
            current_x += paper["paper_width"] + gap

    return jsonify({"success": True, "papers": list(paper_store.values())})


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
    print(f"{'='*60}\n")

    try:
        # Build export list from papers with assigned SVGs
        export_svgs = []
        paper_count = 0
        
        for paper in paper_store.values():
            svg_id = paper.get("svg_id")
            if not svg_id:
                continue
            svg_data = svg_library.get(svg_id)
            if not svg_data:
                continue

            paper_count += 1
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

        if not export_svgs:
            return jsonify({"error": "No assigned SVGs to export"}), 400

        settings = load_settings()
        canvas_width = settings["general"]["area_width"]
        canvas_height = settings["general"]["area_height"]

        # Generate combined SVG
        combined_svg_path = os.path.join(output_folder, "combined.svg")
        generate_combined_svg(
            export_svgs, canvas_width, canvas_height, combined_svg_path
        )

        # Generate G-code files (one per color)
        gcode_files = process_svg_to_gcode(
            combined_svg_path, canvas_width, canvas_height, output_folder
        )

        # Generate guide G-code
        guide_gcode_path = os.path.join(output_folder, "guide.gcode")
        generate_guide_gcode(list(paper_store.values()), guide_gcode_path, settings)

        # Generate stats.txt file
        stats_path = os.path.join(output_folder, "stats.txt")
        generate_stats_file(
            stats_path,
            export_svgs,
            gcode_files,
            canvas_width,
            canvas_height
        )

        # Log all generated files
        print(f"EXPORT: Generated files:")
        print(f"  - Combined SVG: {combined_svg_path}")
        print(f"  - Guide G-code: {guide_gcode_path}")
        print(f"  - Stats: {stats_path}")
        for gcode_file in gcode_files:
            print(f"  - G-code: {gcode_file}")
        print(f"{'='*60}\n")

        return jsonify(
            {
                "success": True,
                "output_folder": output_folder,
                "combined_svg": combined_svg_path,
                "gcode_files": gcode_files,
                "guide_gcode": guide_gcode_path,
                "stats": stats_path,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
            import time
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
