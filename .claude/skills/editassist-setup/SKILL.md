---
name: editassist-setup
description: Guided first-time setup (or repair) of editassist on this machine. Installs dependencies, memory-os, the Resolve MCP and the Whisper model; collects and validates API keys (ElevenLabs, Higgsfield, Pexels, Hugging Face) without exposing them; captures the user's editing preferences; ends with a self-test and a status table. Use for "set it up", "configura tudo", "instalar", "first time", "add my key", "my key doesn't work", or when `ea doctor` / `ea keys` shows something missing that a request needs.
---
# editassist-setup

Goal: the user leaves with everything they want working, verified, and knows what is off and how to
turn it on later. Re-runnable: when they only want one thing ("add my Higgsfield key"), jump to that step.
Talk in the user's language. Ask one group of questions at a time (AskUserQuestion), never a wall.

## 0. Where are we
Run and read: `uv run ea doctor`, `uv run ea keys --check`, `uv run ea memory`. If `uv` is missing,
go to step 1. Note the OS: macOS, Windows (PowerShell or Git Bash) or Linux. Summarise in 3-5 lines:
what's ready, what's missing.

## 1. System dependencies (asks before installing anything)
They change the machine, so confirm first. Then:
- macOS/Linux: `./setup.sh` (Homebrew/apt: ffmpeg, Node, uv; then Python + Remotion deps, the Resolve MCP if Resolve is installed).
- Windows: `powershell -ExecutionPolicy Bypass -File setup.ps1` (winget: ffmpeg, Node LTS, uv).
  After winget installs, a NEW terminal may be needed for PATH; say so if a command is still not found.
- No Homebrew on macOS: send them to https://brew.sh (it needs their password; they run it).
Re-run `uv run ea doctor` until required rows are `[ok]`.

## 2. memory-os (their private memory across repos and Claude accounts)
If `~/.memory-os` is missing, explain in one line what it gives (their taste follows them; the
project memory in `.claude/_memory/` works without it) and offer to install:
`git clone https://github.com/edunascimentt/memory-os.git ~/.memory-os && ~/.memory-os/install.sh`
(on Windows: Git Bash or WSL). Then `uv run ea memory --init` (migrates anything already in `memory/`).
Suggest they fill `~/.memory-os/memory/me.md` with who they are; don't write it for them.

## 3. API keys
Ask which features they want (multi-select). Only collect keys for those:

| Feature | Keys | Where | Notes |
|---|---|---|---|
| Voice-over, SFX, music, dubbing | `ELEVENLABS_API_KEY` (+ `ELEVENLABS_VOICE_ID`) | elevenlabs.io > Settings > API keys | `ea keys --check` shows plan + credits left; ~ music/dubbing may need a paid plan |
| Generated b-roll / images | `HF_API_KEY_ID` + `HF_API_KEY_SECRET` | console.higgsfield.ai > API keys | pay per generation; also ask their per-generation cap → `EA_HF_MAX_USD` (default 2) |
| Stock b-roll | `PEXELS_API_KEY` | pexels.com/api (free, instant) | |
| Automatic speaker detection | `HF_TOKEN` | huggingface.co/settings/tokens (read) + accept terms of `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0` | then `uv sync --extra diarize` (~2 GB) |

How to collect, safest first:
1. **Recommended**: they open `.env` in the repo root (setup created it from `.env.example`) in their editor,
   paste the values, save, and tell you "done". The keys never enter this conversation.
2. If they paste a key in the chat anyway: say once, plainly, that it is now in this conversation's
   history, then store it with the value on stdin, not in a file you create:
   `printf '%s' '<value>' | uv run ea keys set NAME` (PowerShell: `'<value>' | uv run ea keys set NAME`).
Then ALWAYS validate: `uv run ea keys --check --only NAME ...`. It uses free endpoints only. `valid: false` →
read the note (401 = wrong or revoked key, 403 = missing permission) and help fix it; network error →
retry later, it's not the key.
Voice: after ElevenLabs validates, `uv run ea voices`, let them pick 1-3 by name/labels, set
`ELEVENLABS_VOICE_ID`, and write the choice (name, not key) to `<memory>/preferences.md`.

Rules: never repeat a key back, never put a key in memory, a commit, a skill or a log; `.env` is
gitignored (`ea keys` reports `gitignored: true`; if false, stop and fix .gitignore first). Keys
already in the shell environment work too (`source: environment`); don't duplicate them into `.env`
unless they ask.

## 4. Editors
- Ask which they use: DaVinci Resolve (Studio or free?), Premiere Pro, After Effects, Final Cut, or render only.
- Resolve Studio: Preferences > System > General > External scripting using: **Local**. Then
  `uv run ea resolve-mcp --setup` if doctor shows the MCP missing, and tell them to restart Claude Code
  in this folder and approve the `davinci-resolve` server when asked. Free Resolve: export/import works;
  live control (`--open`, MCP) doesn't (Blackmagic restricts external scripting to Studio).
- Premiere / AE / FCP: nothing to install (XML, .jsx, FCPXML files).

## 5. Whisper model (optional, ~1.6 GB, one time)
Offer to download now so the first edit doesn't stall:
`uv run python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')"`
Slow machine or little disk: set `EA_WHISPER_MODEL=small` in `.env` (faster, less accurate; the
transcribe skill warns when it drops passages). NVIDIA GPU on Windows/Linux is used automatically.

## 6. Editing preferences (2-3 short questions, skippable)
Main platform (YouTube / Reels-TikTok / podcast), default frame (16:9 or 9:16), caption style
(clean / bold / boxed), how tight cuts should be (relaxed / normal / tight → min silence 0.7 / 0.45 / 0.3),
language of their videos, music taste. Write them to `<memory>/preferences.md` with today's date
(style-profile rules). Everything can change later just by telling the editor.

## 7. Verify and hand off
- `uv run ea selftest` (test suite on synthetic media, ~1 min; no keys, no downloads).
- `uv run ea doctor` and `uv run ea keys --check`.
- Final table: feature → ready / off (and the one command or step to turn it on). Then suggest a first
  task: "put a video in `projects/test/input/` and ask: cut the silences and add captions".
