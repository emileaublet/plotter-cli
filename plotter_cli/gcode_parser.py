#!/usr/bin/env python3
"""
G-code parser that adds travel distance comments and adjusts Z height based on travel distance.
"""

import re
import sys
import math
from pathlib import Path
from typing import Optional, Tuple


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
    ):
        """
        Initialize the parser.

        Args:
            long_distance_z: Z height for long travels (default: 10.0mm)
            short_distance_z: Z height for short travels (default: 4.0mm)
            short_distance_mm: Distance threshold in mm to determine short vs long travel (default: 1.5mm)
            z_down: Z height when pen is down (default: 0.0mm)
            feed_rate_draw: Feed rate for drawing movements (default: 4000 mm/min)
            feed_rate_z: Feed rate for Z-axis movements (default: 1500 mm/min)
        """
        self.long_distance_z = long_distance_z
        self.short_distance_z = short_distance_z
        self.short_distance_mm = short_distance_mm
        self.z_down = z_down
        self.feed_rate_draw = feed_rate_draw
        self.feed_rate_z = feed_rate_z

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

    def parse_file(self, input_file: Path) -> None:
        """
        Parse a G-code file and optimize Z heights based on travel distance.

        Args:
            input_file: Input G-code file path to modify
        """
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Read all lines first
        with open(input_file, "r", encoding="utf-8") as infile:
            lines = infile.readlines()

        # Optimize Z heights based on travel distance
        processed_lines = self._optimize_z_heights(lines)

        # Remove the boundary squares between layer 0 markers
        processed_lines = self.remove_code_between_markers(
            processed_lines,
            start_marker="; --- Start Layer 0 ---",
            end_marker="; --- End Layer 0 ---",
        )

        # Write back to the same file
        with open(input_file, "w", encoding="utf-8") as outfile:
            outfile.writelines(processed_lines)

    def _optimize_z_heights(self, lines: list[str]) -> list[str]:
        """
        Optimize Z heights based on travel distance between paths.

        Args:
            lines: List of G-code lines

        Returns:
            Modified list with optimized Z heights
        """
        processed_lines = []
        i = 0

        while i < len(lines):
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
