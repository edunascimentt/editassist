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
  already in the user's bins is reused, speed changes become conformed pool copies (2x of 59.94 =
  119.88, 0.4 = 23.976; one bin per rate, `editassist/speed <rate>`; no bake needed when the rate
  exists), centred zooms set ZoomX/Y, audio gains/fades are placed as rendered wavs, LUTs go on node 1
  (the user's own LUT when the grade is just that LUT; Resolve only loads LUTs from its LUT folders),
  the SRT lands on a subtitle track. Ignore the "run ea bake" warning for clips the native build
  handles; read the result line for what it couldn't set. Never switch the user's project without
  saying so, and never script LoadProject while "Untitled Project" is open (a modal save dialog
  blocks it): ask the user to open the project.
- `--template "<timeline>"`: build inside an emptied copy of a timeline the user already styled (their
  subtitle font/size/position are a track property no API can set). Use it whenever the project has a
  previous version or the client has a styled template; never leave the user restyling captions.
- Before handing over: check the built timeline for holes (consecutive items must butt) and render or
  still-check a few frames against the preview.
- Corrected captions (`ea subtitles --lines ... --name X`): copy `output/X.srt` to
  `output/<timeline name>.srt` before `--open`, that is the file placed on the subtitle track.
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
