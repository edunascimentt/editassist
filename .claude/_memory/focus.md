# Focus (this project)

> What matters right now in THIS project. Dates ABSOLUTE (YYYY-MM-DD).
> Finished goals get pruned or moved to decisions.md, not left rotting.

## Active priorities

1. Make CI green: first run (2026-10-05) failed on ubuntu/macos/windows while local passes: `test_launch_scaffold_audit_and_music_tools` (`templates/launch/public/` is an empty dir, git doesn't track it) and `test_render_with_fx_and_burned_captions` (ffmpeg "Error splitting the argument list: Option not found", ~ libass caption path).
2. First real edit with real footage end to end (everything so far tested on synthetic media).

## Not yet verified (as of 2026-10-02)

- Opening exports inside Resolve, Premiere and After Effects (AE only tested against `tests/ae_mock.js`).
- `ea export --open` creating a project in Resolve (only the scripting connection was tested).
- Resolve MCP tools that change a project (only handshake + tool list tested).
- Live API calls: ElevenLabs (tts, sfx, music, dubbing), Higgsfield generation, Pexels, pyannote.
- product-launch with a real brand/product and live ElevenLabs music (composition plan), VO and SFX kit (only synthetic audio tested).
- libass path of caption burn-in (dev machine's ffmpeg has no libass).

## Blocked / waiting on

- Windows verification — CI now runs on windows-latest; waiting on the fixes above.
- Higgsfield live test — waiting on API credentials in `.env`.
