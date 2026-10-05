# editassist desktop app

The same editor as the terminal workflow (CLAUDE.md, skills, the `ea` CLI), driven from a window:
projects, drag-and-drop media, a chat with the editor, a preview player, the timeline and one-click
exports. macOS first; the code already has the Windows paths (see "Windows" below).

```
renderer (React)  ──IPC──►  main process (Electron)
  projects, chat,              ├─ engine.ts   ea CLI, setup, doctor, tool installs
  player, timeline,            ├─ agents/     Claude (Agent SDK) · Codex (Codex SDK)
  settings, wizard             ├─ store.ts    settings + keys (OS keychain via safeStorage)
                               └─ projects.ts list/create/import, file watcher, ea-media://
```

## Accounts and keys

| Editor | How it signs in |
|---|---|
| **Claude** | Anthropic API key only. Anthropic's terms don't allow third-party apps to offer claude.ai (Pro/Max) sign-in, so the app runs the Agent SDK with its own config dir and refuses any credential other than the key (`apiKeySource` check). |
| **Codex** | ChatGPT account through OpenAI's own `codex login` (the sign-in happens on OpenAI's page; the app never sees it), or an OpenAI API key. |

ElevenLabs, Higgsfield, Pexels and Hugging Face keys are validated for free when saved. All keys are
encrypted with the OS keychain (`safeStorage`), handed to the engine and the agents as environment
variables, and never sent to the renderer (it only sees the last 4 characters).

## Run from source

```bash
cd app
npm install          # npm 11 asks to approve install scripts: npm approve-scripts electron esbuild
npm run dev          # Vite + Electron, the engine is this repo
npm run typecheck
npm run build && npx electron .
```

In dev the engine is the repo itself and projects live in `projects/`.

## Package

```bash
npm run dist:mac     # release/editassist-<version>-arm64.dmg (unsigned)
```

The packaged app carries the engine (`src/`, skills, assets, Remotion, templates, vendored memory-os)
in `Resources/engine`, copies it to `~/Library/Application Support/editassist/engine` on first launch
(again after each app update) and links its `projects/` to the user's projects folder
(`~/Movies/editassist` by default). The first-run wizard installs ffmpeg / uv / Node (Homebrew) and
runs `uv sync` there.

Unsigned build: on first open, right-click the app > Open (Gatekeeper). Signing and notarizing need an
Apple Developer ID (`mac.identity` in `electron-builder.yml`).

## Tests

```bash
npm run build
node tests/smoke.mjs <out-dir> [profile-dir]                      # screenshots the first screen
STEPS=steps.mjs node tests/smoke.mjs <out-dir> <profile-dir>       # plus your own Playwright steps
EXE=release/mac-arm64/editassist.app/Contents/MacOS/editassist node tests/smoke.mjs <out>   # the package
```

Use a throwaway profile dir: the app keeps settings, keys and the agents' config there.

## Windows

Paths, tool installs (winget), the projects junction and the agent binaries are handled; `npm run
dist:win` builds an NSIS installer. Not run on Windows yet.
