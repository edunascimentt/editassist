---
name: ingest
description: First step for any project. Catalogs media in projects/<name>/input (duration, fps, size, audio), extracts analysis audio, optional proxies. Use when the user adds footage or starts a new edit.
---
# ingest

1. If the project doesn't exist: `uv run ea new <name> [--fps 30 --width 1920 --height 1080 --language pt --platform youtube]`.
   Match fps/resolution to the main camera unless the user or `<memory>/preferences.md` says otherwise
   (vertical: `--width 1080 --height 1920`).
2. Ask the user to drop files into `projects/<name>/input/` (subfolders fine) if it's empty.
3. `uv run ea ingest <name>` (add `--proxies` for 4K+ or long footage; previews read proxies faster).
4. Report: number of clips, total duration, mixed frame rates or resolutions (flag them; a mixed-fps
   timeline needs a decision), clips without audio.
5. Read the camera fields ingest adds to `work/media.json` (Sony and others that write capture XML):
   - `log: true` / `gamma` (e.g. `s-log3-cine`): the footage is flat log. It needs a conversion LUT
     before anything looks right (color skill); don't judge exposure or pick shots by the raw look.
   - `capture_fps` 50/59.94/100/119.88 in a 23.976/25/29.97 project: shot for slow motion (S&Q).
     Use those clips at speed `project fps / capture fps` (0.4 for 59.94 in 23.976) in montages.
   - Phones/cameras record vertical with a rotation flag: media.json width/height are already
     rotated. All-vertical footage usually means a vertical deliverable: set the project to 1080x1920
     (edit `project.json`) before building the timeline, and say so.

Re-run after new files arrive; existing entries are kept.
