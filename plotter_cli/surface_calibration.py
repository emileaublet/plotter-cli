"""
Surface height calibration: grid G-code, sampled height maps, bilinear Z offset, G-code post-pass.

Grid indices: row i = increasing Y (y_coords[i]), column j = increasing X (x_coords[j]).
points[i][j] is an integer level; node offset is level * delta_z_mm (cumulative refinement).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Match, Optional, Sequence, Tuple, Union

# --- Grid geometry ---


def axis_sample_coords(max_mm: float, spacing_mm: float) -> List[float]:
    """Sample positions 0, spacing, 2*spacing, ... while <= max_mm."""
    if spacing_mm <= 0:
        raise ValueError("grid spacing must be positive")
    coords: List[float] = []
    x = 0.0
    n = 0
    max_n = int(max_mm // spacing_mm) + 3
    while x <= max_mm + 1e-6 and n < max_n:
        coords.append(round(x, 6))
        x += spacing_mm
        n += 1
    if not coords:
        coords = [0.0]
    return coords


def grid_dimensions(
    area_width: float, area_height: float, grid_spacing_mm: float
) -> Tuple[int, int, List[float], List[float]]:
    """Return nx, ny, x_coords, y_coords."""
    x_coords = axis_sample_coords(area_width, grid_spacing_mm)
    y_coords = axis_sample_coords(area_height, grid_spacing_mm)
    return len(x_coords), len(y_coords), x_coords, y_coords


# --- JSON height map ---


def build_height_map_dict(
    *,
    grid_spacing: float,
    delta_z_mm: float,
    area_width: float,
    area_height: float,
    points: List[List[int]],
    name: str = "",
    paper: str = "",
    plotter: str = "",
    pen: str = "",
) -> Dict[str, Any]:
    ny = len(points)
    nx = len(points[0]) if ny else 0
    return {
        "version": 1,
        "grid_spacing": grid_spacing,
        "delta_z_mm": delta_z_mm,
        "area_width": area_width,
        "area_height": area_height,
        "nx": nx,
        "ny": ny,
        "points": points,
        "name": name,
        "paper": paper,
        "plotter": plotter,
        "pen": pen,
    }


def save_height_map_json(path: Union[str, Path], data: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_height_map_json(path: Union[str, Path]) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class HeightMap:
    """Bilinear interpolation of Z offsets (mm) from discrete grid samples."""

    def __init__(
        self,
        x_coords: Sequence[float],
        y_coords: Sequence[float],
        z_grid: List[List[float]],
    ):
        self.x_coords = list(x_coords)
        self.y_coords = list(y_coords)
        self.z_grid = z_grid
        self.nx = len(self.x_coords)
        self.ny = len(self.y_coords)

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> "HeightMap":
        spacing = float(data["grid_spacing"])
        delta_z = float(data["delta_z_mm"])
        area_w = float(data["area_width"])
        area_h = float(data["area_height"])
        points = data["points"]
        ny = len(points)
        nx = len(points[0]) if ny else 0

        exp_nx, exp_ny, x_coords, y_coords = grid_dimensions(area_w, area_h, spacing)
        if nx != exp_nx or ny != exp_ny:
            raise ValueError(
                f"points shape ({ny}x{nx}) does not match grid for "
                f"area {area_w}x{area_h}mm spacing {spacing}mm (expected {exp_ny}x{exp_nx})"
            )

        z_grid: List[List[float]] = []
        for row in points:
            z_row = []
            for v in row:
                vi = int(v)
                z_row.append(vi * delta_z)
            z_grid.append(z_row)

        return cls(x_coords, y_coords, z_grid)

    @classmethod
    def from_json_file(cls, path: Union[str, Path]) -> "HeightMap":
        return cls.from_json_dict(load_height_map_json(path))

    def sample_offset(self, x: float, y: float) -> float:
        if self.nx < 2 or self.ny < 2:
            if self.ny == 0 or self.nx == 0:
                return 0.0
            return self.z_grid[0][0]

        x = max(self.x_coords[0], min(x, self.x_coords[-1]))
        y = max(self.y_coords[0], min(y, self.y_coords[-1]))

        j = self._find_cell(self.x_coords, x)
        i = self._find_cell(self.y_coords, y)

        x0, x1 = self.x_coords[j], self.x_coords[j + 1]
        y0, y1 = self.y_coords[i], self.y_coords[i + 1]
        tx = 0.0 if x1 <= x0 else (x - x0) / (x1 - x0)
        ty = 0.0 if y1 <= y0 else (y - y0) / (y1 - y0)

        z00 = self.z_grid[i][j]
        z10 = self.z_grid[i][j + 1]
        z01 = self.z_grid[i + 1][j]
        z11 = self.z_grid[i + 1][j + 1]

        z0 = z00 * (1 - tx) + z10 * tx
        z1 = z01 * (1 - tx) + z11 * tx
        return z0 * (1 - ty) + z1 * ty

    @staticmethod
    def _find_cell(coords: Sequence[float], v: float) -> int:
        for j in range(len(coords) - 1):
            if coords[j] <= v <= coords[j + 1] + 1e-9:
                return j
        return len(coords) - 2


# --- Calibration mark shapes ---

# A "stroke" is a polyline: a list of (x, y) points drawn in one pen-down..pen-up
# sequence. A shape function receives the mark center (cx, cy) and the available
# half-extents (x_lo, x_hi, y_lo, y_hi), already clamped to the bed so marks never
# run off the edge, and returns a list of strokes. Marks are centered on (cx, cy)
# and scaled to fit the clamped extents (a circle/square becomes asymmetric near a
# corner — the same tradeoff the X already makes).

Point = Tuple[float, float]
Stroke = List[Point]


def _shape_cross(
    cx: float, cy: float, x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> List[Stroke]:
    return [
        [(cx - x_lo, cy - y_lo), (cx + x_hi, cy + y_hi)],
        [(cx - x_lo, cy + y_hi), (cx + x_hi, cy - y_lo)],
    ]


def _shape_plus(
    cx: float, cy: float, x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> List[Stroke]:
    return [
        [(cx - x_lo, cy), (cx + x_hi, cy)],
        [(cx, cy - y_lo), (cx, cy + y_hi)],
    ]


def _shape_square(
    cx: float, cy: float, x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> List[Stroke]:
    return [
        [
            (cx - x_lo, cy - y_lo),
            (cx + x_hi, cy - y_lo),
            (cx + x_hi, cy + y_hi),
            (cx - x_lo, cy + y_hi),
            (cx - x_lo, cy - y_lo),
        ]
    ]


def _shape_circle(
    cx: float, cy: float, x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> List[Stroke]:
    import math

    segments = 24
    pts: Stroke = []
    for k in range(segments + 1):
        theta = 2.0 * math.pi * k / segments
        c = math.cos(theta)
        s = math.sin(theta)
        ex = x_hi if c >= 0 else x_lo
        ey = y_hi if s >= 0 else y_lo
        pts.append((cx + ex * c, cy + ey * s))
    return [pts]


def _shape_swirl(
    cx: float, cy: float, x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> List[Stroke]:
    import math

    # Symmetric Archimedean spiral so the swirl reads as round, not skewed.
    r_max = min(x_lo, x_hi, y_lo, y_hi)
    if r_max <= 0:
        return []
    turns = 3.0
    steps = 72
    pts: Stroke = []
    for k in range(steps + 1):
        t = k / steps
        theta = turns * 2.0 * math.pi * t
        r = r_max * t
        pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return [pts]


SHAPES = {
    "cross": _shape_cross,
    "plus": _shape_plus,
    "square": _shape_square,
    "circle": _shape_circle,
    "swirl": _shape_swirl,
}


def generate_calibration_grid_gcode(
    area_width: float,
    area_height: float,
    *,
    grid_spacing_mm: float = 30.0,
    cross_size_mm: float = 4.0,
    shape: str = "cross",
    z_up: float,
    z_down: float,
    feed_rate_draw: float,
    feed_rate_travel: float,
    feed_rate_z: float,
) -> str:
    _, _, xs, ys = grid_dimensions(area_width, area_height, grid_spacing_mm)
    half = cross_size_mm / 2.0
    shape_fn = SHAPES.get(shape, _shape_cross)
    shape_name = shape if shape in SHAPES else "cross"

    lines: List[str] = [
        f"; Surface calibration grid — {shape_name} marks at each sample point",
        "G21 ; Set units to mm",
        "G90 ; Absolute positioning",
        f"G1 Z{z_up} F{feed_rate_z} ; Pen up",
        f"G0 X0.0000 Y0.0000 F{feed_rate_travel} ; Home",
        "",
    ]

    for yi, cy in enumerate(ys):
        for xi, cx in enumerate(xs):
            # Asymmetric extents so marks stay within the bed (no negative coords at corners)
            x_lo = min(half, cx)
            x_hi = min(half, area_width - cx)
            y_lo = min(half, cy)
            y_hi = min(half, area_height - cy)
            lines.append(f"; Grid cell row={yi} col={xi} X={cx:.2f} Y={cy:.2f}")
            for stroke in shape_fn(cx, cy, x_lo, x_hi, y_lo, y_hi):
                if len(stroke) < 2:
                    continue
                sx, sy = stroke[0]
                lines.append(f"G0 X{sx:.4f} Y{sy:.4f} F{feed_rate_travel}")
                lines.append(f"G1 Z{z_down} F{feed_rate_z} ; Pen down")
                for px, py in stroke[1:]:
                    lines.append(
                        f"G1 X{px:.4f} Y{py:.4f} F{feed_rate_draw} ; Draw"
                    )
                lines.append(f"G1 Z{z_up} F{feed_rate_z} ; Pen up")
            lines.append("")

    lines.extend(
        [
            f"G0 X0.0000 Y0.0000 F{feed_rate_travel} ; Return to home",
            f"G1 Z{z_up} F{feed_rate_z} ; Stay pen up",
            "M2 ; End of program",
        ]
    )
    return "\n".join(lines) + "\n"


_re_xy = re.compile(r"\bX([-+]?\d*\.?\d+)", re.IGNORECASE)
_re_yy = re.compile(r"\bY([-+]?\d*\.?\d+)", re.IGNORECASE)
_re_pen_down_z = re.compile(
    r"^(G1\s+Z)([-+]?\d*\.?\d+)(\s+F\d+.*;.*Pen down.*)$",
    re.IGNORECASE,
)
_re_draw_xyf = re.compile(
    r"^(G1\s+X([-+]?\d*\.?\d+)\s+Y([-+]?\d*\.?\d+))(\s+F\d+)(\s*;.*Draw.*)$",
    re.IGNORECASE,
)


def apply_height_map_to_gcode_text(
    text: str,
    height_map: HeightMap,
    *,
    z_down_base: float,
) -> str:
    """Return G-code with pen-down / draw Z adjusted (same rules as file pass)."""
    lines = text.splitlines(keepends=True)

    last_x = 0.0
    last_y = 0.0
    pen_down = False
    out: List[str] = []

    for line in lines:
        u = line.upper()

        if u.strip().startswith("G0") or u.strip().startswith("G1"):
            xm = _re_xy.search(line)
            ym = _re_yy.search(line)
            if xm:
                last_x = float(xm.group(1))
            if ym:
                last_y = float(ym.group(1))

        if "PEN UP BEFORE MOVE" in u or "STAY PEN UP" in u:
            pen_down = False
        elif "; PEN UP" in u and "BEFORE MOVE" not in u and "STAY" not in u:
            pen_down = False

        modified = line

        if _re_pen_down_z.match(line) and "PEN DOWN" in u:
            off = height_map.sample_offset(last_x, last_y)

            def _sub_pen(m: Match[str]) -> str:
                return f"{m.group(1)}{z_down_base + off:.6f}{m.group(3)}"

            modified = _re_pen_down_z.sub(_sub_pen, line, count=1)
            pen_down = True

        elif pen_down and _re_draw_xyf.match(line) and "; DRAW" in u:
            m = _re_draw_xyf.match(line)
            assert m is not None
            x = float(m.group(2))
            y = float(m.group(3))
            off = height_map.sample_offset(x, y)
            nz = z_down_base + off
            modified = f"G1 X{x:.8f} Y{y:.8f} Z{nz:.6f}{m.group(4)}{m.group(5)}\n"

        out.append(modified)

    return "".join(out)


def apply_height_map_to_gcode_file(
    path: Union[str, Path],
    height_map: HeightMap,
    *,
    z_down_base: float,
) -> None:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        apply_height_map_to_gcode_text(text, height_map, z_down_base=z_down_base),
        encoding="utf-8",
    )

def apply_height_map_if_configured(
    gcode_paths: List[str],
    settings_general: Dict[str, Any],
    height_map_path_override: Optional[str] = None,
) -> None:
    """Apply bed height map to generated G-code files when a path is configured."""
    import os

    effective = height_map_path_override
    if effective is None:
        effective = settings_general.get("height_map_path")
    if not effective:
        from .utils import get_settings_file_path

        default_path = Path(get_settings_file_path()).with_name("height_map.json")
        if default_path.is_file():
            effective = str(default_path)
    if not effective:
        return
    effective = os.path.abspath(os.path.expanduser(str(effective).strip()))
    if not os.path.isfile(effective):
        raise FileNotFoundError(f"Height map file not found: {effective}")
    hmap = HeightMap.from_json_file(effective)
    z_down_val = float(settings_general.get("z_down", 0.0))
    for gcode_file in gcode_paths:
        if os.path.basename(gcode_file).lower() == "guide.gcode":
            continue
        apply_height_map_to_gcode_file(gcode_file, hmap, z_down_base=z_down_val)

