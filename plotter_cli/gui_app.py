"""
Flask application for the Plotter GUI.
Provides a web-based interface for arranging multiple SVGs on a canvas.
"""

import os
import time
import json
import tempfile
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from .utils import load_settings, get_svg_dimensions
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


def allowed_file(filename):
    """Check if file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    """Serve the main GUI page."""
    return render_template("index.html", cache_bust=str(int(time.time())))


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
            paper_width = paper["width"]
            paper_height = paper["height"]
        else:
            paper_width = paper["height"]
            paper_height = paper["width"]

    paper_id = str(uuid.uuid4())
    paper_store[paper_id] = {
        "id": paper_id,
        "paper_name": paper_name,
        "paper_width": paper_width,
        "paper_height": paper_height,
        "svg_id": None,  # SVG assigned to this paper
        "x": 0,
        "y": 0,
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
        }
    )


@app.route("/api/update-paper", methods=["POST"])
def update_paper():
    """Update paper position or assigned SVG."""
    data = request.json
    paper_id = data.get("id")

    app.logger.info("update_paper request: %s", data)

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

    app.logger.info("update_paper stored: %s", paper_data)
    return jsonify({"success": True, "paper": paper_data})


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
    """Remove an SVG from the library."""
    if svg_id not in svg_library:
        return jsonify({"error": "SVG not found"}), 404

    # Check if any papers are using this SVG
    papers_using_svg = [p for p in paper_store.values() if p.get("svg_id") == svg_id]
    if papers_using_svg:
        return (
            jsonify(
                {
                    "error": f"Cannot remove SVG: it is assigned to {len(papers_using_svg)} paper(s)"
                }
            ),
            400,
        )

    svg_data = svg_library[svg_id]

    # Clean up files
    try:
        if os.path.exists(svg_data["filepath"]):
            os.remove(svg_data["filepath"])
        png_path = svg_to_png(svg_data["filepath"])
        if os.path.exists(png_path):
            os.remove(png_path)
    except Exception:
        pass  # Ignore cleanup errors

    del svg_library[svg_id]
    return jsonify({"success": True})


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

    try:
        # Build export list from papers with assigned SVGs
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
            }
            export_svgs.append(export_entry)
            app.logger.info("export entry: %s", {
                "paper_id": paper.get("id"),
                "svg_id": svg_id,
                "x": export_entry["x"],
                "y": export_entry["y"],
                "paper_width": export_entry["paper_width"],
                "paper_height": export_entry["paper_height"],
                "svg_scale": export_entry["svg_scale"],
                "filename": export_entry.get("filename"),
            })

        if not export_svgs:
            return jsonify({"error": "No assigned SVGs to export"}), 400

        settings = load_settings()
        canvas_width = settings["general"]["area_width"]
        canvas_height = settings["general"]["area_height"]

        # Generate combined SVG
        combined_svg_path = os.path.join(output_folder, "combined.svg")
        app.logger.info("Generating combined SVG: %s", combined_svg_path)
        generate_combined_svg(export_svgs, canvas_width, canvas_height, combined_svg_path)

        # Generate G-code files (one per color)
        gcode_files = process_svg_to_gcode(
            combined_svg_path, canvas_width, canvas_height, output_folder
        )

        # Generate guide G-code
        guide_gcode_path = os.path.join(output_folder, "guide.gcode")
        generate_guide_gcode(list(paper_store.values()), guide_gcode_path, settings)

        return jsonify(
            {
                "success": True,
                "output_folder": output_folder,
                "combined_svg": combined_svg_path,
                "gcode_files": gcode_files,
                "guide_gcode": guide_gcode_path,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_gui(host="127.0.0.1", port=5000, debug=False):
    """Run the Flask GUI application."""
    print(f"Starting Plotter Studio GUI...")
    print(f"Open your browser to: http://{host}:{port}")
    try:
        app.run(host=host, port=port, debug=debug, threaded=True)
    except Exception as e:
        print(f"Error starting server: {e}")
        raise
