# Decisions (this project)

> Append-only log of real decisions in this project. Never edit past entries —
> if a decision is reversed, add a NEW entry that supersedes it.
> Format: `## YYYY-MM-DD — title` then what + why (1-3 lines).

## 2026-10-01 — Claude Code as the engine, `ea` CLI as the hands
The model reasons, picks and writes JSON; a small Python CLI does media work and prints JSON back.
Keeps the tools deterministic and testable, and lets Codex use the same repo via AGENTS.md.

## 2026-10-01 — Own timeline.json, OTIO only for export
A format small enough for the model to read and edit by hand; converted to OTIO / FCP7 XML / FCPXML /
AE .jsx at export. NLE quirks stay in `export.py`.

## 2026-10-01 — Bundle fonts and the face model
Montserrat (OFL) and YuNet (MIT) live in `assets/` so captions, thumbnails and reframing look the
same on every OS, independent of installed fonts or OpenCV builds.

## 2026-10-01 — No librosa / PySceneDetect / scenedetect
Beat tracking is numpy (spectral flux + DP), scene detection is ffmpeg. Avoids numba and the
PyAV/OpenCV double-libav problem; installs the same on Windows.

## 2026-10-01 — Bake instead of exotic NLE metadata
Crop, zoom and speed are rendered into `work/baked/` before Resolve/Premiere/FCP export, because
exchange formats don't carry them reliably. Dissolves and LUTs export natively.

## 2026-10-01 — Higgsfield via its REST API, schema from the docs
Models and parameters are read from docs.higgsfield.ai (cached a week), never hardcoded; estimate
before submit; `EA_HF_MAX_USD` (default $2) requires explicit `--yes` above it.

## 2026-10-02 — Resolve MCP through `ea resolve-mcp`
samuelgursky/davinci-resolve-mcp pinned at 4.8.26, one managed install per machine; `.mcp.json`
calls `uv run ea resolve-mcp` so the repo holds no absolute paths and works on macOS and Windows.

## 2026-10-02 — Memory: memory-os, two tiers
Codebase knowledge in `.claude/_memory/` (this tier, shared). Each user's editing taste goes to their
private memory-os global tier (`<global>/editassist/`), shared across their Claude accounts; repo
`memory/` (gitignored) is only the fallback when memory-os isn't installed.
