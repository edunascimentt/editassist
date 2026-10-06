# Focus (this project)

> What matters right now in THIS project. Dates ABSOLUTE (YYYY-MM-DD).
> Finished goals get pruned or moved to decisions.md, not left rotting.

## Active priorities

1. Keep CI green on ubuntu/macos/windows (first run 2026-10-05 failed: empty launch `public/` dirs and the removed `-filter_complex_script`; both fixed the same day).
2. First real edit with real footage done 2026-10-06 (36 vertical S-Log3 clips → 64 s highlights built natively in Resolve 21.0); the OTIO/XML import into Resolve failed there and needs investigating.

## Not yet verified (as of 2026-10-05)

- Desktop app: a successful agent turn (Claude and Codex were only run up to auth with invalid keys), the Codex ChatGPT login flow, Windows build/run, signed/notarized macOS build.

- Opening exports inside Resolve, Premiere and After Effects (AE only tested against `tests/ae_mock.js`).
- `ea export --open` creating a project in Resolve (only the scripting connection was tested).
- Resolve MCP tools that change a project: add_subfolder/set_current_folder worked 2026-10-06; import_timeline failed (same as direct API).
- `ea export --open [--current]` native fallback (`resolve_native.py`) end to end on a live Resolve: the same calls were run by hand on 21.0.0 on 2026-10-06, the module only against a fake API.
- WHY Resolve 21.0.0 rejects our OTIO/XML via the API (try File > Import > Timeline by hand with the same file; try Resolve 21.1).
- FCPXML import in Final Cut (format names like `FFVideoFormat3840x2160xp23.97...` come from the adapter).
- Live API calls: ElevenLabs (tts, sfx, music, dubbing), Higgsfield generation, Pexels, pyannote.
- product-launch with a real brand/product and live ElevenLabs music (composition plan), VO and SFX kit (only synthetic audio tested).
- libass path of caption burn-in (dev machine's ffmpeg has no libass).

## Blocked / waiting on

- Windows verification — CI now runs on windows-latest; waiting on the fixes above.
- Higgsfield live test — waiting on API credentials in `.env`.
