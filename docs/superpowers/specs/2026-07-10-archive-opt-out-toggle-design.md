# Archiving Opt-Out Toggle — Design

## Context

A separate, in-progress repo (`~/Dev/drawings-private`) will archive finished
artwork + G-code output. Once that archive CLI exists, Claude will drive the
archiving step itself, outside of Plotter Studio, after each export. Plotter
Studio needs a way to tell Claude "don't archive this particular export"
without Claude having to guess or ask every time.

This spec covers only the Plotter Studio UI/API change: a visible, session-only
toggle that flags a single export as "don't archive." It does **not** cover
the archive CLI itself, which has not been specified yet.

## Requirements

- A control that is clearly visible in the main Studio interface (not tucked
  inside a settings modal) for opting a single export out of archiving.
- Default state is "archiving on."
- Opting out is a one-shot action: after the next export completes, the
  control resets to the default "archiving on" state.
- The choice must be readable by Claude after the export happens — Claude is
  not part of the browser session, so the signal has to travel through the
  export API response.
- No new persistence (no `settings.yaml` field, no `localStorage`, no
  database). Purely in-memory client state for the current page session.

## Design

### UI

A new button, `#archive-toggle-btn`, placed in `.header-actions`
(`plotter_cli/gui/templates/index.html`), immediately to the left of the
existing `#export-btn`.

Two visual states, toggled on click:

| State | Label | Style |
|---|---|---|
| Default (archiving on) | `💾 ARCHIVING` | primary/neutral button style |
| Opted out (one-shot) | `⚠️ NOT ARCHIVING` | warning style (amber/red border or background) |

Icons use the existing Lucide pattern (`data-lucide="..."`, refreshed via
`lucide.createIcons({ nodes: [...] })` after any DOM update that changes the
icon).

### Frontend state (`plotter_cli/gui/static/app.js`)

- New instance field, e.g. `this.archiveNextExport`, initialized to `true` on
  app load. Being a plain JS field (not `localStorage`), a page reload also
  naturally resets it to `true` — reinforcing the "does not persist" rule via
  two independent paths (post-export reset, and reload reset).
- Click handler on `#archive-toggle-btn` flips `this.archiveNextExport` and
  repaints the button's label/icon/class to match.
- In `export()`, the existing `POST /api/export` body gains one field:
  `{ output_folder, archive: this.archiveNextExport }`.
- After the export request settles (in both the success and error/failure
  branches), the frontend resets `this.archiveNextExport = true` and repaints
  the button back to the default state. This is unconditional — even if the
  user exported with archiving ON, the button state is recomputed to `true`
  every time, which is a no-op visually in that case.

### Backend (`plotter_cli/gui_app.py`, `/api/export` route)

- Reads `archive = data.get("archive", True)` from the request body — no
  other request-handling changes.
- No behavioral effect on the export pipeline itself (nothing in
  `gui_utils.py` changes); this is purely a pass-through flag.
- The flag is included verbatim in the JSON response Plotter Studio already
  returns (alongside `combined_svg`, `gcode_files`, `guide_gcode`, `stats`),
  e.g. `"archive": false`. This is the one place Claude reads the signal —
  Claude is expected to inspect this field after calling/observing an export
  and skip invoking the (future) archive CLI when it is `false`.

## Out of scope

- The archive CLI itself and its invocation from Claude — pending details
  from `~/Dev/drawings-private`.
- Any settings-modal equivalent, persistence, or per-paper archiving
  granularity — this toggle is a single global one-shot flag for "the next
  export," not tied to specific papers.

## Testing

No test framework exists in this repo (per `CLAUDE.md`). Verification is
manual: toggle the button, confirm label/style change, run an export with the
toggle off, confirm the response JSON contains `"archive": false`, and
confirm the button visually resets to `💾 ARCHIVING` afterward regardless of
export success/failure.
