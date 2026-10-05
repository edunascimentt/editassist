# editassist

An AI video editor that runs inside Claude Code (or Codex). You describe the video, drop the
footage in a folder, and the agent cuts it, syncs cameras and mics, adds captions, music cut to the
beat, b-roll, zooms, colour and motion graphics, then hands you a project that opens ready in
**DaVinci Resolve**, **Premiere Pro** or **After Effects**, or a finished mp4 with thumbnail,
chapters and metadata.

```
 prompt + footage
        │
        ▼
 ┌─────────────── the engine ───────────────┐
 │  Claude Code / Codex  (reads CLAUDE.md)  │
 │        │ follows                         │
 │        ▼                                 │
 │  skills  (.claude/skills/*, 32 recipes)  │      ┌─ DaVinci Resolve (.otio, auto-import + LUTs)
 │        │ calls                           │      │
 │        ▼                                 │      ├─ Premiere Pro (.xml)
 │  `ea` CLI  ── ffmpeg · Whisper ·         │ ───► │
 │              ElevenLabs · Higgsfield ·   │      ├─ After Effects (.jsx)
 │              Pexels · Remotion · faces   │      │
 │        │                                 │      └─ mp4 · thumbnail · chapters · SRT
 │        ▼                                 │
 │  projects/<name>/ timeline.json          │
 └──────────────────────────────────────────┘
        ▲                     │
        └── memory ◄── your feedback (preferences, styles, vocabulary)
```

Works on **macOS, Windows and Linux** (CI runs the test suite on all three).

## Desktop app (macOS)

Prefer a window to a terminal? [`app/`](app/README.md) is the same editor as an Electron app: projects,
drag-and-drop media, chat with the editor, preview player, timeline, one-click exports, and a setup
wizard that installs the tools and validates every key. It runs Claude with an Anthropic API key
(claude.ai sign-in isn't allowed in third-party apps) or Codex with a ChatGPT account or OpenAI key.
Build it with `cd app && npm install && npm run dist:mac`.

## Setup

You need [Claude Code](https://claude.com/claude-code) (or Codex). The setup script installs the
rest: ffmpeg, Node.js, uv, and the Python and Remotion dependencies.

**macOS / Linux**
```bash
git clone https://github.com/edunascimentt/editassist.git && cd editassist
./setup.sh
```

**Windows** (PowerShell)
```powershell
git clone https://github.com/edunascimentt/editassist.git; cd editassist
powershell -ExecutionPolicy Bypass -File setup.ps1
```

**Easiest: let the agent do it.** Open Claude Code in the folder (`claude`) and say
"configura o editassist" / "set up editassist". The `editassist-setup` skill installs what's missing
(asking first), collects and validates your API keys without exposing them, sets up Resolve and
memory, records your editing preferences and runs the self-test.

Or by hand: fill in `.env` with the keys you want to use (all optional):

| Key | For | Where |
|---|---|---|
| `ELEVENLABS_API_KEY` | voiceover, sound effects, music, dubbing | elevenlabs.io > API keys |
| `ELEVENLABS_VOICE_ID` | default narration voice | `uv run ea voices` |
| `HF_API_KEY_ID` + `HF_API_KEY_SECRET` | Higgsfield generated shots and images | console.higgsfield.ai |
| `PEXELS_API_KEY` | stock b-roll search (free) | pexels.com/api |
| `HF_TOKEN` | automatic speaker detection (optional extra) | huggingface.co/settings/tokens |

Check everything with `uv run ea doctor` and `uv run ea keys --check` (validates each key against a
free endpoint, prints only the last 4 characters). `uv run ea selftest` runs the test suite.

For Resolve auto-import, open Resolve and set **Preferences > System > General > External
scripting using: Local**. Without it you import the `.otio` file manually.

**Live Resolve control (Studio only).** Setup also installs the
[DaVinci Resolve MCP server](https://github.com/samuelgursky/davinci-resolve-mcp) (pinned
version, one managed copy per machine). `.mcp.json` registers it for Claude Code as
`davinci-resolve`; approve it the first time you start `claude` in this folder. The agent then
grades, adds transitions, manages the render queue and reads back your manual changes in the open
Resolve project (resolve-live skill). Reinstall or update: `uv run ea resolve-mcp --setup [version]`.
The free edition of Resolve blocks external scripting; see the MCP's README for its in-app bridge.

## Using it

```bash
claude            # inside the editassist folder
```

Then talk to it:

> New project "podcast-ep12". Two cameras and two mics are in input. Sync everything, use the mics,
> cut to whoever is talking, remove dead air, captions in the clean style, lofi music under it,
> chapters and a thumbnail. Give me a Resolve project.

> Find the 5 best moments of this interview and turn them into vertical shorts with bold captions
> and punch-in zooms.

> At 1:23 cut the part about pricing, and the captions are too small.

The agent creates `projects/<name>/`, tells you where to drop the media, shows you a preview and
its decisions, and applies your notes. Anything you correct twice ("tighter cuts", "never use
that font") is saved to your editing memory and becomes the default next time.

## Memory

editassist ships with [memory-os](https://github.com/edunascimentt/memory-os) in `vendor/memory-os/`:
two tiers split by who may read them.

| | where | holds | shared? |
|---|---|---|---|
| **Your editing taste** | memory-os global tier, `~/.memory-os/memory/editassist/` | pacing, caption style, music, looks, vocabulary, named styles, delivery log | private: yours only, every Claude account you use, never committed |
| **Project knowledge** | `.claude/_memory/` in this repo | how the code works, gotchas, decisions, what's unverified | committed: everyone who clones gets it |

Install your private tier once with `uv run ea memory --install` (copies `vendor/memory-os` to
`~/.memory-os`, no download); a session-start notice reminds you if it's missing. Without it, your taste
is kept in the gitignored `memory/` folder instead and `ea memory --init` migrates it later.
`uv run ea memory` shows where yours lives. `bash vendor/memory-os/bin/memory-os check` scans the
project tier for personal data; CI runs it on every push.

## Skills

| Stage | Skill | What it does |
|---|---|---|
| Analysis | `ingest` | catalog media, extract audio, proxies |
| | `transcribe` | word-level transcripts (faster-whisper), flags passages Whisper skipped |
| | `visual-index` | shot detection + contact sheets the agent looks at |
| | `speakers` | who speaks when: one mic per person, or automatic (pyannote) |
| | `multicam` | sync cameras/mics by sound, swap in the clean mic, switch angles |
| Cut | `rough-cut` | story from the transcript, best takes, target length |
| | `silence-cut` | remove pauses and hesitations (jump cuts) |
| | `highlight` | find standalone moments for shorts |
| | `reformat` | 16:9 to 9:16 / 1:1 / 4:5 with face tracking |
| | `zoom-punch` | punch-ins that hide jump cuts, emphasis push-ins |
| | `transitions` | dissolves, dips, fades in/out |
| Audio | `audio-cleanup` | denoise, EQ, compression, loudness |
| | `music` | generated or provided bed, ducked; beat detection, snap to beat, beat-cut montages |
| | `sfx` | generated sound effects on cuts and reveals |
| | `voiceover` | ElevenLabs narration |
| Visual | `subtitles` | SRT + styled burn-in, word-by-word highlight, speaker-aware |
| | `color` | auto grade, camera matching, looks, LUTs (one .cube per camera) |
| | `b-roll` | own footage > Pexels stock > generated |
| | `higgsfield` | text/image-to-video and images via the Higgsfield API (80+ models) |
| | `motion-graphics` | Remotion lower thirds, titles, animated captions |
| Launch films | `product-launch` | UI-first product launch film in Remotion: reference study, storyboard, UI kit + bench, elastic stage, density-audited scenes, composed music, VO, SFX, verified export |
| Delivery | `export-nle` | Resolve / Premiere / After Effects / Final Cut |
| | `render` | mp4 with platform loudness presets |
| | `thumbnail` | best-frame candidates + composed thumbnail |
| | `metadata` | titles, description, validated YouTube chapters, tags |
| | `translate-dub` | translated subtitles, ElevenLabs dubbing |
| Setup | `editassist-setup` | guided install, API keys (validated, never echoed), Resolve, memory, preferences, self-test |
| Meta | `qa` | gaps, flash frames, mid-word cuts, loudness, black frames |
| | `review` | apply feedback on a version |
| | `style-profile` | maintain the memory: preferences, named styles, vocabulary |
| | `preferences-quiz` | short questionnaire that fills the user's preferences (quick, full or one section) |

## CLI

The agent drives these, but you can also run them yourself (`uv run ea <command> -h` for options):

```
ea new <name>                       ea ingest <p> [--proxies]        ea transcribe <p>
ea scenes <p>                       ea find <p> "phrase"             ea transcript <p>
ea silence-cut <p>                  ea cut <p> segments.json         ea timeline <p> [info|validate|json|ripple]
ea sync <p> --ref cam_a cam_b mic   ea sync <p> --swap-audio cam_a mic   ea sync <p> --switch T0 T1 cam_b
ea diarize <p> <id> --tracks Ana=mic_a Bruno=mic_b
ea subtitles <p> [--style bold] [--lines subs_en.json --name <p>_en]
ea reformat <p> --aspect 9:16 [--bake]   ea zoom <p> --punch | --at T --dur S [--ramp R]
ea transition <p> --at T --type dissolve | --fade-in 0.5 --fade-out 1
ea color <p> --auto [--match cam_a] [--look film] [--lut x.cube] [--compare cam_b]
ea beats <p> <music>     ea snap <p> --music <id> --tracks V2     ea montage <p> --music <id> shots.json
ea voiceover <p> "text"  ea voices   ea sfx <p> "prompt"   ea music <p> "prompt"   ea dub <p> --lang en --source f
ea broll <p> "query" [--download 2]  ea register <p> <file>
ea hf models [--kind video]  ea hf schema <endpoint>  ea hf estimate <endpoint> --args a.json
ea hf generate <p> <endpoint> --args a.json [--file image_url=frame.png]   ea hf fetch <p> <request_id>
ea motion <p> LowerThird|Title|Captions --props '{...}'
ea bake <p> [--color]    ea render <p> [--preset youtube] [--subs output/<p>.ass]
ea export <p> --to resolve premiere aftereffects [fcpx] [--open]
ea qa <p> [--render file.mp4]    ea chapters <p> chapters.json    ea thumbnail <p> [--pick N --text "..."]
ea launch new|reference|stills|audit|sfx-kit|vo|music|stretch-music|render|verify <p> ...   (launch films)
ea resolve-mcp [--setup [version]]     (MCP server for .mcp.json)
ea memory [--init]                     (where your editing memory lives; seed/migrate it)
ea keys [--check] | ea keys set NAME < value     ea selftest
ea doctor
```

## Project folder

```
projects/<name>/
  input/          your footage (never modified)
  work/           transcripts, frames, sync/beats/colour data, generated media, media.json
  timeline.json   the edit (simple JSON, documented in src/editassist/timeline.py)
  output/         previews, renders, .otio / .xml / .jsx / .fcpxml, .srt, thumbnail, chapters
```

`projects/` and your editing memory are never committed: each person keeps their own footage and
taste. To share a style with someone, send them the file from `<memory>/styles/`.

## Development

```bash
uv sync --extra dev
uv run pytest -q          # synthetic media, no API keys or Whisper download needed
```

`tests/ae_mock.js` runs generated After Effects scripts against a mock of the AE scripting API.

## Limits worth knowing

- Speed changes, crops and zooms must be baked (`ea bake`) before exporting to Resolve, Premiere
  or Final Cut. XML/OTIO can't carry them reliably. After Effects applies them natively.
- Music ducking, fades/dips to black and burned captions exist in renders. In NLE exports the
  gains, dissolves, LUTs and SRT are carried over, and the export lists what to redo.
- Higgsfield models and their parameters come from docs.higgsfield.ai (cached for a week; refresh
  with `ea hf models --refresh`). Generations above `EA_HF_MAX_USD` (default $2) need your OK.
- Automatic speaker detection without one mic per person needs the `diarize` extra (PyTorch,
  ~2 GB) and a Hugging Face token.
- Exported projects point to absolute media paths, so relink in the NLE if the files move.
- Whisper models download on first use (`large-v3-turbo` is about 1.6 GB). With an NVIDIA GPU it
  runs on CUDA, otherwise on CPU.

## Licenses

- Code: MIT (`LICENSE`).
- `assets/fonts/` Montserrat: SIL Open Font License (`assets/fonts/OFL.txt`).
- `assets/models/` YuNet face detector: MIT (opencv_zoo).
- [Remotion](https://www.remotion.dev/license) is free for individuals and companies of up to 3
  people. Larger companies need a Remotion company license.
