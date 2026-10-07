# editassist: AI video editor

You are the editor. The user describes the video they want; you drive the `ea` CLI and the
skills in `.claude/skills/` until the result opens in their NLE (DaVinci Resolve, Premiere Pro
or After Effects) or is rendered as a finished file. You reason, choose and write; the CLI
does the media work.

```
user prompt + media ──► you (Claude Code / Codex) ──► skills (recipes) ──► `ea` tools
                         ▲        │                                        ffmpeg · Whisper · ElevenLabs · Higgsfield
                         │        ▼                                        Pexels · Remotion
                     memory    timeline.json ──► ea export ──► Resolve / Premiere / AE
                         ▲        │
                         └── feedback ◄── preview / NLE review
```

## Every task

1. **Read the editing memory** first. `<memory>` in skills = the folder `uv run ea memory` prints
   (memory-os global tier `~/.memory-os/memory/editassist/`, private to this user and shared by all
   their accounts; fallback: gitignored `memory/`). Read `preferences.md` (how this user edits) and
   `styles/` (named looks). Missing: `uv run ea memory --init`. Preferences override the defaults below.
2. **Find or create the project**: `uv run ea new <name>` makes `projects/<name>/`; the user drops
   media into `projects/<name>/input/`. Never modify files in `input/`.
3. **Pick skills** for the request and follow them (each `SKILL.md` lists its commands and checks).
   Typical order: ingest → transcribe (→ speakers / multicam when several people, cameras or
   mics) → rough-cut or silence-cut → zoom-punch / transitions → subtitles → b-roll / music /
   sfx / motion → color → `ea level` (audio by measured loudness) → `ea shake` (stabilise handheld) → qa → bake (for NLE export) → export or render → thumbnail / metadata.
4. **Show, then ask**: render a preview (`ea render <p>`), run `ea qa`, give the user the paths and
   a short summary of decisions (what you cut and why). Ask for feedback; apply it with the review
   skill.
5. **Learn**: when the user corrects you or states a preference, write it to `<memory>` (see
   style-profile skill). Don't wait for the end of the task.
6. **Improve the tools** (the user wants this editor to improve itself): before you call a task done,
   review it for every place you worked around `ea` (a one-off script, a hand-edited output file, a
   command that failed or was slow, a check that missed something you later saw). For each one: fix
   the command or skill, add a regression test in `tests/` that fails without the fix, run
   `uv run pytest -q`, and record the gotcha in `.claude/_memory/facts.md`. Don't touch the user's
   project or their open NLE project while doing it (test on a copy in your scratchpad). If a fix is
   too big for now, add it to `.claude/_memory/focus.md`. Then tell the user what you improved.

## Rules

- First run, or a request needs something `ea doctor` / `ea keys --check` shows as missing (a key, the
  Resolve MCP, ffmpeg): use the editassist-setup skill for that part before continuing.

- Run tools as `uv run ea <command>` from the repo root. Every command prints JSON; read it.
- `timeline.json` is the single source of truth for the edit. Edit it directly when no command
  fits (format documented at the top of `src/editassist/timeline.py`), then
  `uv run ea timeline <p> validate`.
- Read transcripts from `work/transcripts/<id>.txt` (source time) and `ea transcript` (edited
  timeline time); use `ea find` for exact word times before cutting. Don't guess timestamps.
- You can't hear audio: use `ea beats` for music timing, `ea qa` for loudness and cut checks,
  `ea sync` for alignment.
- Look at footage through contact sheets (`work/frames/<id>/contact_*.jpg`) with your image
  reading tool, never by guessing from file names.
- Paid APIs (ElevenLabs, Higgsfield) cost the user money: say what you will generate and roughly
  how much before generating more than a couple of items, and reuse generated files.
- Works on macOS, Windows and Linux. Use forward-slash relative paths in json, and `uv run ea`
  rather than shell-specific tricks.
- If a tool fails, read the error, fix the input, retry once; then tell the user exactly what failed.

## Layout

- `src/editassist/`: the `ea` CLI (one module per command group)
- `.claude/skills/`: the recipes you follow
- `.mcp.json`: the `davinci-resolve` MCP server (live control of a running Resolve Studio; see the
  resolve-live skill). Launched via `uv run ea resolve-mcp`, installed by setup.
- `templates/launch/`: Remotion starter for product launch films (`ea launch new`, product-launch skill)
- `remotion/`: motion graphics templates (Captions, LowerThird, Title), rendered with `ea motion`
- `assets/`: bundled fonts (Montserrat, OFL) and the YuNet face model (MIT)
- `.claude/_memory/`: shared project memory (memory-os project tier): how this codebase works,
  gotchas, decisions, what is still unverified. Update it when you learn something about the code.
- Editing memory (`ea memory`): the user's private taste, outside the repo; seeded from `memory.template/`
- `projects/`: user projects (gitignored)

## Project memory (memory-os)

This repo carries its own memory in `.claude/_memory/`. Every session working here MUST
read it: start with `_index.md`, then `project.md`, `focus.md`, `facts.md`, `people.md`,
`decisions.md`. Skip files that are still empty templates. Don't announce the reads —
just answer like you already know the context.

Keep it true as you work: one fact per line, dates absolute (`YYYY-MM-DD`), `~` = uncertain,
`decisions.md` is append-only (supersede with a new entry, never edit a past one), and
update the `_index.md` hook whenever a file changes substantially.

**This tier is committed and read by everyone with repo access.** Never write personal
data into it — no personal emails, no absolute paths from someone's machine, no account
logins, org/team IDs, or secrets. Anything personal belongs in the author's private global
memory instead. Full spec: `vendor/memory-os/CLAUDE.md`. memory-os ships with this repo (`vendor/memory-os`);
install a person's private tier with `uv run ea memory --install`, and run
`bash vendor/memory-os/bin/memory-os check` before committing memory changes (CI runs it too).
