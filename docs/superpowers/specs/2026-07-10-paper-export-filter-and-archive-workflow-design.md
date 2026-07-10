# Per-Paper Export Filter & Archive Workflow — Design

Date: 2026-07-10

## Context

`~/Dev/drawings-private` (a separate repo) now has a working `archive` CLI
(`create`, `validate`, and the `update` command added in
`docs/superpowers/specs/2026-07-10-archive-cli-v2-additions.md` there) for
archiving finished drawings. This spec covers the plotter-cli-side change
needed to support it, plus documents the end-to-end workflow Claude runs
across both repos. It complements, and does not replace,
`docs/superpowers/specs/2026-07-10-archive-opt-out-toggle-design.md` (the
header toggle, already planned separately).

When a Plotter Studio canvas holds multiple papers/artworks, each needs its
own archive entry (own SVG + own G-code folder), but the final combined
G-code (all drawings together, sent to the physical plotter) should not be
archived at all — only the per-paper exports are archival material.

Today, `POST /api/export` always exports every paper in `paper_store` in one
combined pass (confirmed by reading `gui_app.py`/`gui_utils.py` — see prior
exploration). There's no way to isolate one paper's export without
destructively removing every other paper first.

## 1. `paper_ids` export filter

Add an optional `paper_ids` field to the `POST /api/export` request body:

```json
{ "output_folder": "...", "archive": true, "paper_ids": ["paper-3"] }
```

- `paper_ids`: optional array of paper id strings. When present,
  `_validate_export_papers()` (in `gui_utils.py`) filters `paper_store` to
  only the listed ids before building the combined SVG/G-code — everything
  downstream (registration marks, combining, vpype invocation, per-color
  G-code split) is unchanged, it just operates over a subset.
- When absent or `null` (the existing behavior, e.g. the final combined
  export), every assigned paper is exported, exactly as today.
- No new persistence, no UI control for this — it's driven entirely by
  Claude via direct API calls during the archive workflow below, not by a
  human clicking something in Plotter Studio. (Contrast with the archiving
  toggle, which *is* a visible UI control — these are separate, unrelated
  changes to the same endpoint.)
- Unknown/nonexistent ids in `paper_ids` are silently ignored (filtered out,
  not an error) — consistent with treating this as a subset filter over
  whatever currently exists in `paper_store`.

## 2. End-to-end workflow (Claude-driven, not code in either repo)

Once a canvas is ready to export, for a layout with N papers:

1. For each paper `p` in the canvas (in any order):
   a. `POST /api/export {"paper_ids": [p.id], "output_folder": <scratch dir>}`
      — isolates just this paper's SVG + G-code.
   b. Read that paper's source SVG's root-element metadata (per
      `sketch-title`, `sketch-colours`, etc. — see the existing SVG metadata
      reference) to fill in `title_en`/`colours`/etc.
   c. Resolve each `sketch-colours` id against `colours.yaml` via
      `findColourByAnyId` (id or alias) as described in the archive-cli-v2
      spec; add a new catalog entry (prompting the user for brand/name/hex)
      for anything unresolved, recording the alias.
   d. `archive create --json ...` with the resolved metadata (title,
      colours, size, paper, ink, etc. — whatever is known before plotting).
      `mm_drawn`/`mm_travel`/`seconds_of_printing`/`date_plotted` are left
      unset at this point since the drawing hasn't been physically plotted
      yet.
   e. Copy the paper's `combined.svg` from the scratch export into
      `drawings/<uuid>/artwork.svg`, and its G-code files (per-color +
      guide + stats) into `drawings/<uuid>/gcode/`.
   f. Once the piece is actually plotted and stats are known (e.g. after the
      user confirms a physical print run completed, or from a stats file),
      `archive update <uuid> --mm-drawn ... --mm-travel ... --seconds-of-printing
      ... --date-plotted ...` to fill in the post-plot fields.
2. After all N papers are archived individually, do one final
   `POST /api/export {"output_folder": <any scratch location>}` with no
   `paper_ids` filter — the full combined layout, for actually driving the
   plotter. This output is not archived and its location doesn't matter.

If the archiving toggle (separate feature) is off for a given export call,
skip steps b–f for that paper entirely — just use its G-code as part of the
final combined pass.

## Out of scope

- Any UI in Plotter Studio for triggering this per-paper loop — it's driven
  by Claude via direct API calls, not a button a human clicks.
- Automatically detecting "has this paper actually been plotted yet" to
  decide when to call `archive update` — that's a judgment call Claude/the
  user makes, not something either codebase infers.
