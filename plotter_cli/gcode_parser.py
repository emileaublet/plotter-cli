#!/usr/bin/env python3
"""
G-code parser that adds travel distance comments and adjusts Z height based on travel distance.
"""

import re
import sys
import math
from pathlib import Path
from typing import Optional, Tuple


def _circumcircle(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
) -> Tuple[Optional[Tuple[float, float]], Optional[float]]:
    """Return (center, radius) of the circumcircle of three points, or (None, None) if collinear."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(D) < 1e-10:
        return None, None
    ux = (
        (ax**2 + ay**2) * (by - cy)
        + (bx**2 + by**2) * (cy - ay)
        + (cx**2 + cy**2) * (ay - by)
    ) / D
    uy = (
        (ax**2 + ay**2) * (cx - bx)
        + (bx**2 + by**2) * (ax - cx)
        + (cx**2 + cy**2) * (bx - ax)
    ) / D
    return (ux, uy), math.hypot(ax - ux, ay - uy)


class GCodeParser:
    """Parse G-code files and add travel distance comments with dynamic Z adjustment."""

    def __init__(
        self,
        long_distance_z: float = 10.0,
        short_distance_z: float = 4.0,
        short_distance_mm: float = 1.5,
        z_down: float = 0.0,
        feed_rate_draw: int = 4000,
        feed_rate_z: int = 1500,
        arc_fitting: bool = False,
        arc_tolerance: float = 0.05,
        min_arc_segments: int = 4,
        max_arc_radius: float = 2000.0,
    ):
        self.long_distance_z = long_distance_z
        self.short_distance_z = short_distance_z
        self.short_distance_mm = short_distance_mm
        self.z_down = z_down
        self.feed_rate_draw = feed_rate_draw
        self.feed_rate_z = feed_rate_z
        self.arc_fitting = arc_fitting
        self.arc_tolerance = arc_tolerance
        # An arc must replace at least this many G1 segments to be worth emitting.
        self.min_arc_segments = min_arc_segments
        # Runs fitting a circle larger than this (mm) are treated as straight lines.
        self.max_arc_radius = max_arc_radius

    def parse_start_line_comment(self, line: str) -> Optional[Tuple[float, float]]:
        """
        Parse a "Start Line" comment to extract X and Y positions.

        Example: "; --- Start Line 3738 X319.76622395 Y38.86621024 ---"

        Args:
            line: Comment line to parse

        Returns:
            Tuple of (x, y) if found, None otherwise
        """
        # Look for Start Line comment with X and Y coordinates
        pattern = r"; --- Start Line \d+ X([-+]?\d*\.?\d+) Y([-+]?\d*\.?\d+) ---"
        match = re.search(pattern, line)
        if match:
            x = float(match.group(1))
            y = float(match.group(2))
            return (x, y)
        return None

    def parse_travel_command(self, line: str) -> Optional[Tuple[float, float]]:
        """
        Parse a G0 travel command to extract destination X and Y positions.

        Example: "G0 X320.48158750 Y37.57380697 F6000 ; Travel to start"

        Args:
            line: G-code line to parse

        Returns:
            Tuple of (x, y) if found, None otherwise
        """
        line_upper = line.upper()
        if line_upper.strip().startswith("G0"):
            x_match = re.search(r"X([-+]?\d*\.?\d+)", line_upper)
            y_match = re.search(r"Y([-+]?\d*\.?\d+)", line_upper)

            if x_match and y_match:
                x = float(x_match.group(1))
                y = float(y_match.group(1))
                return (x, y)
        return None

    def is_pen_up_command(self, line: str) -> bool:
        """
        Check if line is a pen up command (G1 Z with upward movement).

        Args:
            line: G-code line to check

        Returns:
            True if it's a pen up command
        """
        line_upper = line.upper().strip()
        return (
            line_upper.startswith("G1")
            and "Z" in line_upper
            and "PEN UP BEFORE MOVE" in line_upper.upper()
        )

    def calculate_distance(
        self, pos1: Tuple[float, float], pos2: Tuple[float, float]
    ) -> float:
        """
        Calculate Euclidean distance between two points.

        Args:
            pos1: First point (x, y)
            pos2: Second point (x, y)

        Returns:
            Distance in mm
        """
        x1, y1 = pos1
        x2, y2 = pos2
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    def get_z_height_for_distance(self, distance: float) -> float:
        """
        Determine appropriate Z height based on travel distance.

        Args:
            distance: Travel distance in mm

        Returns:
            Z height to use for this travel
        """
        if distance <= self.short_distance_mm:
            return self.short_distance_z
        else:
            return self.long_distance_z

    def modify_pen_up_command(self, line: str, z_height: float) -> str:
        """
        Modify a pen up command to use the specified Z height.

        Args:
            line: Original pen up command line
            z_height: New Z height to use

        Returns:
            Modified line with new Z height
        """
        # Replace the Z value in the line while preserving the rest including newline
        pattern = r"(G1\s+Z)([-+]?\d*\.?\d+)(\s+.*?)(\n?)$"
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return f"{match.group(1)}{z_height}{match.group(3)}{match.group(4)}"
        return line

    def remove_code_between_markers(
        self, lines: list[str], start_marker: str, end_marker: str
    ) -> list[str]:
        """
        Remove all lines between start_marker and end_marker, inclusive.

        Args:
            lines: List of G-code lines
            start_marker: Marker indicating the start of the section to remove
            end_marker: Marker indicating the end of the section to remove
        Returns:
            List of G-code lines with the specified section removed
        """
        in_section = False
        result_lines = []

        for line in lines:
            if start_marker in line:
                in_section = True
                continue  # Skip the start marker line
            if end_marker in line and in_section:
                in_section = False
                continue  # Skip the end marker line
            if not in_section:
                result_lines.append(line)

        return result_lines

    def parse_file(self, input_file: Path, progress_callback=None) -> None:
        """
        Parse a G-code file and optimize Z heights based on travel distance.

        Args:
            input_file: Input G-code file path to modify
            progress_callback: Optional fn(phase: str, fraction: float) called
                during the heavy phases (Z-optimization, arc fitting). Throttled
                to ~5% steps so it can drive a live progress display.
        """
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        with open(input_file, "r", encoding="utf-8") as infile:
            lines = infile.readlines()

        # Throttle: only forward a report when its phase or 5%-bucket changes.
        last_bucket = [None]

        def report(phase: str, fraction: float) -> None:
            if progress_callback is None:
                return
            frac = max(0.0, min(1.0, fraction))
            bucket = (phase, int(frac * 100) // 5)
            if bucket != last_bucket[0]:
                last_bucket[0] = bucket
                progress_callback(phase, frac)

        processed_lines = self._optimize_z_heights(lines, report)

        processed_lines = self.remove_code_between_markers(
            processed_lines,
            start_marker="; --- Start Layer 0 ---",
            end_marker="; --- End Layer 0 ---",
        )

        if self.arc_fitting:
            processed_lines = self._compress_arcs(processed_lines, report)

        if progress_callback is not None:
            progress_callback("writing", 1.0)

        with open(input_file, "w", encoding="utf-8") as outfile:
            outfile.writelines(processed_lines)

    def _optimize_z_heights(self, lines: list[str], report=None) -> list[str]:
        """
        Optimize Z heights based on travel distance between paths.

        Args:
            lines: List of G-code lines
            report: Optional fn(phase, fraction) for progress reporting.

        Returns:
            Modified list with optimized Z heights
        """
        processed_lines = []
        i = 0
        total = len(lines)
        next_report = 0
        report_step = max(1, total // 50)

        while i < len(lines):
            if report is not None and i >= next_report:
                report("Z-optimization", i / total if total else 1.0)
                next_report = i + report_step
            current_line = lines[i]

            # Look for Start Line comment
            start_pos = self.parse_start_line_comment(current_line)

            if start_pos is not None:
                # Add the Start Line comment
                processed_lines.append(current_line)
                i += 1

                # Look ahead for pen up command and travel command
                pen_up_line = None
                travel_pos = None
                pen_up_index = None

                # Scan the next few lines to find the pattern
                j = i
                while j < min(i + 10, len(lines)):  # Look ahead up to 10 lines
                    line = lines[j]

                    # Check for pen up command
                    if self.is_pen_up_command(line):
                        pen_up_line = line
                        pen_up_index = j

                    # Check for travel command
                    travel_pos = self.parse_travel_command(line)
                    if travel_pos is not None:
                        break

                    j += 1

                # If we found both start position and travel destination
                if travel_pos is not None and pen_up_index is not None:
                    distance = self.calculate_distance(start_pos, travel_pos)
                    z_height = self.get_z_height_for_distance(distance)

                    travel_comment = f"; Will travel {distance:.2f}mm (Z={z_height})\n"

                    # Collect lines up to the pen up command, filtering out any existing travel comments
                    lines_to_add = []
                    while i < pen_up_index:
                        # Skip any existing travel distance comments to avoid duplicates
                        if not lines[i].strip().startswith("; Will travel"):
                            lines_to_add.append(lines[i])
                        i += 1

                    # Add the collected lines
                    processed_lines.extend(lines_to_add)

                    # Add the travel distance comment before the pen up command
                    processed_lines.append(travel_comment)

                    # Modify the pen up command with the calculated Z height
                    modified_pen_up = self.modify_pen_up_command(lines[i], z_height)
                    processed_lines.append(modified_pen_up)
                    i += 1
                else:
                    # No travel command found, continue processing remaining lines normally
                    # The Start Line comment was already added, just continue
                    pass
            else:
                # Normal line, just add it
                processed_lines.append(current_line)
                i += 1

        return processed_lines


    def _compress_arcs(self, lines: list[str], report=None) -> list[str]:
        """
        Replace runs of consecutive G1 draw moves with G2/G3 arc commands where the
        points lie on a circle within arc_tolerance mm.
        """
        result: list[str] = []
        pen_down = False
        current_x = 0.0
        current_y = 0.0
        # run_points[0] is the G0 destination (implicit arc start already in position).
        # run_points[1:] are the subsequent draw targets; run_lines[k] moves to run_points[k+1].
        run_points: list[Tuple[float, float]] = []
        run_lines: list[str] = []

        def flush():
            if run_lines:
                result.extend(self._fit_arcs_in_run(run_points, run_lines))
            run_points.clear()
            run_lines.clear()

        total = len(lines)
        next_report = 0
        report_step = max(1, total // 50)

        for idx, line in enumerate(lines):
            if report is not None and idx >= next_report:
                report("arc fitting", idx / total if total else 1.0)
                next_report = idx + report_step
            lu = line.upper()

            # G0 travel: update position, pass through as-is
            if lu.strip().startswith("G0") and "X" in lu and "Y" in lu:
                flush()
                xm = re.search(r"X([-+]?\d*\.?\d+)", lu)
                ym = re.search(r"Y([-+]?\d*\.?\d+)", lu)
                if xm and ym:
                    current_x = float(xm.group(1))
                    current_y = float(ym.group(1))
                result.append(line)
                continue

            # Pen down: start a new run at current position
            if "PEN DOWN" in lu:
                flush()
                pen_down = True
                run_points.append((current_x, current_y))
                result.append(line)
                continue

            # Pen up: flush current run then pass through
            if "PEN UP" in lu:
                flush()
                pen_down = False
                result.append(line)
                continue

            # G1 XY draw move: collect into run while pen is down.
            # Z may be present when surface calibration is active — accept it.
            if (
                pen_down
                and lu.strip().startswith("G1")
                and "X" in lu
                and "Y" in lu
            ):
                xm = re.search(r"X([-+]?\d*\.?\d+)", lu)
                ym = re.search(r"Y([-+]?\d*\.?\d+)", lu)
                if xm and ym:
                    current_x = float(xm.group(1))
                    current_y = float(ym.group(1))
                    run_points.append((current_x, current_y))
                    run_lines.append(line)
                    continue

            # Everything else: flush and pass through
            flush()
            result.append(line)

        flush()
        return result

    def _fit_arcs_in_run(
        self,
        points: list[Tuple[float, float]],
        original_lines: list[str],
    ) -> list[str]:
        """
        Compress a draw run into G2/G3 arcs where possible.
        points[0] is the implicit start; original_lines[k] targets points[k+1].

        For each start, the longest fitting arc is found by exponential search
        (probe windows i+3, i+4, i+6, i+10, …) followed by a binary search of
        the failing gap — O(L log L) per arc instead of O(L²). Arc-fitting is
        treated as monotone in window length; since every emitted arc is still
        fully validated by _fit_arc, a rare non-monotone case can only yield a
        slightly shorter arc, never an incorrect one.
        """
        if len(points) < 3:
            return list(original_lines)

        result: list[str] = []
        i = 0
        n = len(points)

        while i < n - 1:
            # Not enough points remain to form a circle → emit the plain move.
            if n - i < 3:
                result.append(original_lines[i])
                i += 1
                continue

            good_hi = None
            good_fit = None

            # Smallest window (3 points). If even this fails, there's no arc here.
            first_fit = self._fit_arc(points, i, i + 3)
            if first_fit is not None:
                good_hi, good_fit = i + 3, first_fit

                hi = i + 3
                jump = 1
                while good_hi is not None:
                    nxt = min(hi + jump, n)
                    fit = self._fit_arc(points, i, nxt)
                    if fit is not None:
                        good_hi, good_fit = nxt, fit
                        if nxt == n:
                            break  # can't grow further
                        hi = nxt
                        jump *= 2
                    else:
                        # Boundary is between hi (good) and nxt (bad): binary search.
                        binlo, binhi = hi, nxt
                        while binhi - binlo > 1:
                            mid = (binlo + binhi) // 2
                            fmid = self._fit_arc(points, i, mid)
                            if fmid is not None:
                                binlo, good_hi, good_fit = mid, mid, fmid
                            else:
                                binhi = mid
                        break

            if good_fit is not None and (good_hi - 1 - i) >= self.min_arc_segments:
                cmd, center = good_fit
                best_end = good_hi - 1
                ex, ey = points[best_end]
                I = center[0] - points[i][0]
                J = center[1] - points[i][1]
                result.append(
                    f"{cmd} X{ex:.4f} Y{ey:.4f} I{I:.4f} J{J:.4f} F{self.feed_rate_draw}\n"
                )
                i = best_end
            else:
                result.append(original_lines[i])
                i += 1

        return result

    def _fit_arc(
        self,
        points: list[Tuple[float, float]],
        lo: int,
        hi: int,
    ) -> Optional[Tuple[str, Tuple[float, float]]]:
        """
        Try to fit a single G2/G3 arc through points[lo:hi] in path order.

        Returns (command, center) if the points lie within arc_tolerance of a
        common circle AND sweep around it monotonically (a genuine arc, not an
        S-curve, corner, or near-collinear wobble). Returns None otherwise.

        Operates on index bounds rather than a sliced copy to avoid per-probe
        allocation in the exponential/binary search above.
        """
        length = hi - lo
        if length < 3:
            return None

        p0 = points[lo]
        pm = points[lo + length // 2]
        pn = points[hi - 1]
        center, radius = _circumcircle(p0, pm, pn)
        if center is None or radius is None:
            return None
        # Reject near-straight runs (huge radius) — keep them as G1 lines.
        if radius < 1e-6 or radius > self.max_arc_radius:
            return None

        cx, cy = center
        tol = self.arc_tolerance

        # Every point must lie within tolerance of the circle.
        for k in range(lo, hi):
            px, py = points[k]
            if abs(math.hypot(px - cx, py - cy) - radius) > tol:
                return None

        # The points must progress monotonically around the circle. This is what
        # distinguishes a real arc from points that merely sit near a circle.
        direction = 0  # +1 = CCW (G3), -1 = CW (G2)
        total_sweep = 0.0
        prev_angle = math.atan2(points[lo][1] - cy, points[lo][0] - cx)

        for k in range(lo + 1, hi):
            px, py = points[k]
            angle = math.atan2(py - cy, px - cx)
            delta = angle - prev_angle
            # Normalize step into (-pi, pi]
            while delta <= -math.pi:
                delta += 2 * math.pi
            while delta > math.pi:
                delta -= 2 * math.pi

            if abs(delta) < 1e-9:
                prev_angle = angle
                continue

            # A single step jumping more than a quarter turn means the points
            # are too sparse to be a smooth arc — bail out.
            if abs(delta) > math.pi / 2:
                return None

            step_dir = 1 if delta > 0 else -1
            if direction == 0:
                direction = step_dir
            elif step_dir != direction:
                # Sweep reversed direction → not a single arc.
                return None

            total_sweep += delta
            prev_angle = angle

        if direction == 0:
            return None
        # Don't fold a full (or over-full) circle into one arc.
        if abs(total_sweep) >= 2 * math.pi:
            return None

        cmd = "G3" if direction > 0 else "G2"
        return cmd, center


def main():
    """Main function for command line usage."""
    if len(sys.argv) < 2:
        print(
            "Usage: python gcode_parser.py <input_file> [short_distance_mm] [long_distance_z] [short_distance_z]"
        )
        print("  input_file: Path to G-code file to modify")
        print(
            "  short_distance_mm: Distance threshold for short travel (default: 1.5mm)"
        )
        print("  long_distance_z: Z height for long travels (default: 10.0mm)")
        print("  short_distance_z: Z height for short travels (default: 4.0mm)")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    short_distance_mm = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
    long_distance_z = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    short_distance_z = float(sys.argv[4]) if len(sys.argv) > 4 else 4.0

    try:
        parser = GCodeParser(
            long_distance_z=long_distance_z,
            short_distance_z=short_distance_z,
            short_distance_mm=short_distance_mm,
        )
        parser.parse_file(input_file)

        print(f"Settings used:")
        print(f"  Short distance threshold: {parser.short_distance_mm}mm")
        print(f"  Long distance Z: {parser.long_distance_z}mm")
        print(f"  Short distance Z: {parser.short_distance_z}mm")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
