# Calibration Grid Shapes — Design

## Goal

Let the surface-calibration grid draw shapes other than the current X/cross at
each sample point. Support five shapes — **cross, plus, circle, square, swirl** —
selectable from both the CLI and Studio.

## Constraint (must not break)

The height-map compensation pass (`apply_height_map_to_gcode_text`) keys off the
`Pen down` / `; Draw` / `Pen up` comments and the per-line `X.. Y.. ; Draw`
structure to bake pen-down Z offsets. Every shape must emit that exact structure
so height-map baking keeps working for all shapes.

## Approach — shape registry returning strokes

Refactor `generate_calibration_grid_gcode` (in `plotter_cli/surface_calibration.py`)
so per-point drawing is delegated to small pure shape functions.

A **stroke** is a polyline: a list of `(x, y)` points drawn in one pen-down..pen-up
sequence. A shape function has the signature:

```python
def shape_strokes(cx, cy, x_lo, x_hi, y_lo, y_hi) -> list[list[tuple[float, float]]]
```

`x_lo/x_hi/y_lo/y_hi` are the available half-extents in each direction, already
clamped to the bed (the same corner-clamping the current X computes), so marks
never run off the bed. Shapes are centered on `(cx, cy)` and scaled to fit the
clamped extents (a circle/square becomes asymmetric near a corner — same tradeoff
the current X already makes).

Shapes:
- **cross** — two diagonal strokes (current behaviour; default).
- **plus** — one horizontal + one vertical stroke.
- **square** — one closed 5-point polyline.
- **circle** — one closed polyline of ~24 segments.
- **swirl** — one continuous Archimedean spiral polyline outward from center.

A `SHAPES` dict maps name → function. `generate_calibration_grid_gcode` gains a
`shape: str = "cross"` keyword arg and, for each grid point, emits per stroke:

```
G0 X.. Y.. F{travel}        ; travel to stroke start
G1 Z{z_down} F{fz} ; Pen down
G1 X.. Y.. F{draw} ; Draw   (one per polyline vertex after the first)
G1 Z{z_up} F{fz} ; Pen up
```

The first point of each stroke is reached by the `G0` travel move (so the pen-down
Z sample is taken there, as today); remaining points are `; Draw` lines.

## Wiring

**CLI** (`plotter_cli/commands.py`, `surface_cal_grid`):
- Add `--shape` option, choices `cross|plus|circle|square|swirl`, default `cross`.
- Relabel `--cross-size` help to "Mark size (mm)"; keep the flag name for
  backward compatibility.
- Pass `shape=shape` into `generate_calibration_grid_gcode`.

**Studio** (`plotter_cli/gui/templates/index.html`, `app.js`, `gui_app.py`):
- Add a shape `<select>` above "Cross Size" in the Generate Grid tab.
- Include `shape` in the `/api/surface-cal/grid` POST body from `app.js`.
- Read `shape` in the `surface_cal_grid` route and pass it through; keep the
  JSON key `cross_size` unchanged.

## Non-goals / YAGNI

- No new dependencies.
- No persistence/settings changes; `cross_size` still controls mark size.
- No per-shape size overrides — one size value drives all shapes.
- Invalid shape names fall back to `cross`.
