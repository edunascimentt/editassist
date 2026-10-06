---
name: resolve-live
description: Drive a RUNNING DaVinci Resolve Studio through the davinci-resolve MCP server (timeline, media pool, grades/nodes, markers, Fusion, Fairlight, render queue). Use after `ea export --open` to finish work inside Resolve, to inspect what the user changed there, render from Resolve, or whenever the user says "in Resolve", "no Resolve", "render it in Resolve".
---
# resolve-live

Two ways to reach Resolve, with different jobs:
- **`ea` + timeline.json** is where the edit is built and versioned: cuts, captions, music, zooms,
  colour LUTs. `uv run ea export <p> --to resolve --open` creates the Resolve project and timeline.
- **The `davinci-resolve` MCP tools** (from `.mcp.json`; 37 compound tools such as `timeline`,
  `timeline_item`, `timeline_item_color`, `media_pool`, `render`, `timeline_markers`, `fusion_comp`)
  act on the LIVE project. Use them for things that only exist in Resolve: node grades and colour
  groups, Fusion titles, Fairlight, render queue and presets, reading back what the user changed by hand.

Requirements: Resolve **Studio** running, Preferences > System > General > External scripting
using: Local. If the tools are missing, run `uv run ea doctor` and `uv run ea resolve-mcp --setup`,
then restart the session and approve the `davinci-resolve` server.

Safety (the user's real project is open):
1. Before changes, read state: current project, timeline name, track and item counts. Say what you
   are about to change.
2. Work on a duplicate timeline for anything structural (`timeline_versioning` / duplicate), never the
   user's only copy. Ask before deleting clips, timelines, projects or media, or switching projects.
3. Save the project after a batch of changes; tell the user what changed.
4. Round-trips: if the user edited in Resolve and wants the changes back in editassist, export a
   timeline from Resolve (OTIO/XML) instead of hand-copying, and say what will be lost.

Resolve Studio 21.0 API limits (21.1 adds them): no `TimelineItem.SetSpeed`, `SetFades`,
`AddTransition`; audio items have no Volume property. `ImportTimelineFromFile` returned None for every
OTIO/XML we gave it (2026-10-06), even a 3-clip one. Build with `AppendToTimeline` clip infos instead
(`ea export --open` does this automatically); slow motion via a pool copy with
`SetClipProperty("FPS", "<timeline fps>")`.

Typical finishing pass after `ea export --open`:
- check the imported timeline matches (clip count, duration vs `ea timeline <p>`)
- grade: the LUT is on node 1; add correction nodes per shot or a colour group per camera
- add the fades/dips the export listed as not carried (Video Transitions > Dip to Color)
- captions: import the SRT onto a subtitle track if `--open` only put it in the media pool
- render: pick a preset (YouTube 1080p/4K), set the output folder to `projects/<name>/output/`, add to
  the queue, start, then report the file path. Run `uv run ea qa <p> --render <file>` on the result.
