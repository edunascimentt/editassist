# Project

> What this project is. Read first — orients every answer about this repo.
> One fact per line. Uncertain = `~` prefix.
>
> SHARED — committed and read by the whole team. Paths relative to the repo root,
> never `/Users/<someone>/…` or `C:\Users\<someone>\…`.

**Name:** editassist
**What it is / goal:** AI video editor. Claude Code (or Codex) is the engine: it follows `CLAUDE.md` + `.claude/skills/*` and drives the `ea` CLI; output is an editable Resolve/Premiere/AE project or a finished mp4.
**Stack:** Python 3.12 via uv (`src/editassist/`, CLI `ea`), ffmpeg/ffprobe, faster-whisper, OpenCV (YuNet face model in `assets/models/`), OpenTimelineIO + FCP7/FCPXML adapters, Pillow/numpy; Remotion 4 (Node) in `remotion/`; DaVinci Resolve MCP (`.mcp.json`).
**Run / build:** `./setup.sh` (macOS/Linux) or `setup.ps1` (Windows); then `claude` in the repo. Tools: `uv run ea <command>`; check: `uv run ea doctor`.
**Tests:** `uv sync --extra dev && uv run pytest -q` (synthetic media, no keys, no Whisper download); CI on ubuntu/macos/windows in `.github/workflows/ci.yml`.
**Repo / hosting:** local git repo; ~ not pushed to GitHub yet (2026-10-02).
**Constraints:** must run the same on macOS and Windows; user projects (`projects/`) and personal editing memory are never committed; paid APIs (ElevenLabs, Higgsfield) need user confirmation before spending.

## Context that doesn't fit above

- 2026-10-01: Project built (initial commit 719c43e). 2026-10-02: Resolve MCP added (beed65d), memory-os project tier initialized.
- Source of truth for an edit is `projects/<name>/timeline.json` (format documented at the top of `src/editassist/timeline.py`); everything else is derived from it.
