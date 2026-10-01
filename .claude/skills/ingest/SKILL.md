---
name: ingest
description: First step for any project. Catalogs media in projects/<name>/input (duration, fps, size, audio), extracts analysis audio, optional proxies. Use when the user adds footage or starts a new edit.
---
# ingest

1. If the project doesn't exist: `uv run ea new <name> [--fps 30 --width 1920 --height 1080 --language pt --platform youtube]`.
   Match fps/resolution to the main camera unless the user or `memory/preferences.md` says otherwise
   (vertical: `--width 1080 --height 1920`).
2. Ask the user to drop files into `projects/<name>/input/` (subfolders fine) if it's empty.
3. `uv run ea ingest <name>` (add `--proxies` for 4K+ or long footage; previews read proxies faster).
4. Report: number of clips, total duration, mixed frame rates or resolutions (flag them; a mixed-fps
   timeline needs a decision), clips without audio.

Re-run after new files arrive; existing entries are kept.
