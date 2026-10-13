---
name: premiere-live
description: Edit a RUNNING Adobe Premiere Pro live while the user watches, through the editassist UXP panel (MCP tools premiere_*, or `ea premiere`). Build an editassist timeline as a sequence, then cut, trim, move, add transitions/effects/keyframes/markers, look at frames, export. Use for "no Premiere", "in Premiere", "edita no Premiere", "quero acompanhar no Premiere", or when the user's NLE is Premiere.
---
# premiere-live

```
Claude ──MCP premiere_*──► ea premiere-mcp (hub 127.0.0.1:47821) ◄──WebSocket── editassist panel in Premiere
          `ea premiere …` ──┘                                        (UXP; runs lib.js ops, one undo step each)
```

Works on macOS and Windows, Premiere Pro 25.6+ (written against 26.3).

## Setup (once per machine)
1. `uv run ea premiere install`: packages the panel (`src/editassist/premiere_uxp/`) as a .ccx and installs it
   with Adobe's Unified Plugin Installer. It prints what to do if the installer is missing (double-click the .ccx).
2. Restart Premiere, then **Window > UXP Plugins > editassist** and dock the panel. It shows
   "connected" and a log of every operation as it runs, so the user follows along.
3. `uv run ea premiere status` (or the `premiere_status` tool): connected, Premiere version, project, sequences.
The panel carries a secret from `~/.editassist/premiere-bridge.token`; reinstalling after deleting that file
is how to rotate it. The hub refuses browser origins and anything without the token.

## Two jobs
- **Build** (the edit lives in `timeline.json`): run `ea qa <p>`, then `premiere_build {project}` or
  `uv run ea premiere build <p>` (or `ea export <p> --to premiere --open`). It creates a sequence from a
  generated preset (size, fps, enough tracks) in bin `editassist` and places every clip as an overwrite edit,
  with clip-by-clip progress in the panel. The result lists `failed`, `skipped` and `notes`: read them.
  - native in Premiere: cuts (frame-exact ticks), linked A/V when V and A mirror each other, framing (fill/fit,
    `crop` from reformat, punch-ins, push-in `ramp` as Scale + Position keyframes) as Motion, dissolves / dips /
    fades as transitions, `opacity`, `stabilize` as Warp Stabilizer (a different stabiliser than the
    preview's deshake: framing near the edges differs), sequence markers
  - rendered copies (the 26.x API can't set them; `warnings` lists each): LUT grades (the segment with the LUT,
    source size, so Motion still applies; Input LUT takes registered GUIDs only and ignores a .cube path),
    `speed` and `whip` zooms (baked like `ea bake`), music ducking (stem), audio gain/fades/one-channel
  - captions (work/captions.json): a transparent picture layer on track "Captions", styled like the preview.
    The .srt is imported into bin editassist: for editable captions the user drags it onto the sequence and
    deletes the layer (no UXP call creates a caption track, 26.3 and 26.5)
  - not possible: adding tracks to an existing sequence (`into_current` only fits what the sequence has)
  - Premiere composites in linear light: semi-transparent layers look a little brighter than the preview
- **Live edits** (the user asks for a change while watching): `premiere_sequence` to read, then
  `premiere_edit` actions: place, move, trim, remove (ripple), enable, rename, transition, add_effect,
  remove_effect, set_param (values or keyframes), motion, add_marker, remove_markers, playhead, select.
  remove takes the linked A/V half too (like a click in the timeline); a ripple closes only as far as the
  other sync-locked tracks allow, and the result's `closed` says how far: check it.
  Effect names are Premiere's display names: in 26.x "Gaussian Blur" is the new GPU blur (param "Amount"),
  the old one is "Gaussian Blur (Legacy)"; `premiere_catalog` lists them, `premiere_clip` shows params.
  Clips are referenced `{track: "V1", index: 0}` (by start order) or `{track: "V1", at: 12.5}`.
  Anything else: `premiere_api` to see what this version offers, then `premiere_exec` with a JS function body
  (`ppro`, `lib`, `args`, `ctx` in scope; edits inside `project.lockedAccess` + `executeTransaction`).

## Rules (the user's real project is open)
1. Read before changing: `premiere_status`, then `premiere_sequence` on the sequence you will touch. Say what
   you are about to change in one line.
2. Structural changes to a sequence you didn't build (ripple deletes, moving many clips): duplicate it first
   (Premiere: right-click > Duplicate, or build a new version) and ask before deleting clips, sequences or media.
3. Every op is one undo step labelled `editassist: …`: tell the user they can Cmd/Ctrl+Z it.
4. Export: `premiere_export {path}` (or `ea premiere export <out>`) renders with Premiere's own
   "Match Source - High bitrate" H.264 unless a preset .epr is given, and returns when the file is complete.
5. Look at the result: `premiere_frame {time}` returns the rendered frame (framing, effects, titles). Check a
   few cuts and every reframed shot against the editassist preview before saying it's done.
6. When the user edits by hand in Premiere and wants it back in editassist, read the sequence with
   `premiere_sequence` and write timeline.json from it (in/out are source seconds, start/end sequence seconds).
7. Save with `premiere_project {action: "save"}` after a batch (the build saves on its own).
8. Something the ops can't do and you had to script with `premiere_exec`: add it to `premiere_uxp/lib.js`
   (+ a case in `tests/test_premiere.py`, mock in `tests/premiere_mock.js`). lib.js is reloaded automatically
   when it changes; the panel itself only needs reinstalling when `main.js`/`manifest.json` change.

## Troubleshooting
- "Premiere is not connected": Premiere not running, panel not opened (Window > UXP Plugins > editassist),
  or not installed (`ea premiere install`). The panel retries every 2 s.
- A clip plays silence / shows "Media Offline" after its file was deleted and rendered again: the build
  relinks offline items by path; for one placed by hand use Premiere's Link Media.
- "bad token": the panel was installed with another token file: `ea premiere install` again.
- Port 47821 busy with something else: set `EA_PREMIERE_PORT` for `ea` AND reinstall (the port is in main.js).
- The installer answered but the panel is missing: Creative Cloud > Plugins shows it; otherwise enable
  Premiere > Settings > Plugins > developer mode and load `src/editassist/premiere_uxp/manifest.json` with
  UXP Developer Tool (development only).
