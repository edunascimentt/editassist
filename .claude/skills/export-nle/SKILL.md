---
name: export-nle
description: Deliver the edit as an editable project in DaVinci Resolve, Premiere Pro, After Effects (or Final Cut). Use when the user wants to open/finish the edit in their editor.
---
# export-nle

`uv run ea export <p> --to resolve premiere aftereffects [fcpx] [--open]`

- Run `uv run ea qa <p>` first; export refuses invalid timelines.
- Crops, zooms and speed changes must be baked for Resolve/Premiere/FCP: `uv run ea bake <p>`
  (add `--color` to also burn the grade in, for editors who won't apply LUTs). The export warns when
  something is unbaked.
- Grades: Resolve gets each media's LUT applied with `--open`. For Premiere/AE the export lists the
  .cube files to load (Lumetri > Input LUT / Apply Color LUT).
- Dissolves export as real transitions. Fades and dips are listed for you to add in the NLE.
- Chapters (metadata skill) export as timeline markers.
- **Resolve**: `output/<name>.otio`. `--open --current` adds the timeline to the project OPEN in
  Resolve (what the user usually means by "no projeto do DaVinci que está aberto"); plain `--open`
  creates/opens a project named after the timeline. If Resolve rejects the OTIO (Studio 21.0.0 did for
  every OTIO/XML), `--open` builds the timeline natively clip by clip (`resolve_native.py`): media
  already in the user's bins is reused, 59.94 slow-motion clips get conformed pool copies in
  `editassist/slowmo`, LUTs go on node 1, the SRT lands on a subtitle track. Read the result line: it
  lists gains and fades the 21.0 API can't set. Never switch the user's project without saying so.
- With `--open` and Resolve running (Preferences > System >
  General > External scripting using: Local), it saves the current project, then creates/opens a
  project named after the timeline and imports it, plus the SRT into the media pool. Manual: File >
  Import > Timeline > pick the .otio.
- After the import, finish inside Resolve with the resolve-live skill (MCP tools: grades,
  transitions, render queue).
- **Premiere**: `output/<name>.xml` (FCP7 XML). File > Import > choose the .xml; relink if media moved.
  Captions: File > Import the .srt, drag to a caption track.
- **After Effects**: `output/<name>.jsx`. File > Scripts > Run Script File. Builds the comp, layers,
  crops, gains and caption text layers.
- **Final Cut Pro**: `output/<name>.fcpxml`.
- Media paths are absolute: if the project moves to another machine, relink in the NLE (or re-export
  there).
- Music ducking is baked into a stem on export (re-export after changing dialogue or music).
- Not carried to NLEs: burned captions (use the SRT), fades to black, caption styling. Tell the user
  what to redo.
- After `--open`, render a check from Resolve (resolve-live) and compare frames against the ea preview
  at the same times: that is how you know the NLE timeline matches.
