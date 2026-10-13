# Focus (this project)

> What matters right now in THIS project. Dates ABSOLUTE (YYYY-MM-DD).
> Finished goals get pruned or moved to decisions.md, not left rotting.

## Active priorities

1. Keep CI green on ubuntu/macos/windows (first run 2026-10-05 failed: empty launch `public/` dirs and the removed `-filter_complex_script`; both fixed the same day).
2. First real edit with real footage done 2026-10-06 (36 vertical S-Log3 clips → 64 s highlights built natively in Resolve 21.0); the OTIO/XML import into Resolve failed there and needs investigating.

## Next tool work (from the second real edit, 2026-10-06)
- `ea resolve study <folder>`: dump a client's past Resolve projects (structure, music, SFX, LUTs, speeds, captions) into a style report, one project per process, refusing when Untitled is current. Done by hand with a scratch script the first time.
- `ea qa --captions <file>` (or follow the burned file) so corrected caption sets get checked.
- Optional: write the Resolve subtitle track style directly (MCP project_db set_subtitle_style needs the project closed + Resolve restart); `--template` covers it while a styled timeline exists.
- Captions for a timeline the user cut by hand in Resolve (2026-10-09): no command mirrors a live Resolve timeline into timeline.json; it was written by hand (audio item source in/out at source_fps). Want `ea timeline <p> from-resolve` (MCP probe_timeline_structure -> clips) so `ea subtitles` + SRT append onto the existing subtitle track is one step.
- `ea subtitles` drops a word whose Whisper start is before the clip `in` even when most of the audible word is inside ("Todos" 0.56-1.08, in 0.917, cut by the user in Resolve); added back via `--lines`. Consider keeping head words whose end lands >= ~0.15 s into the clip.

- Podcast episode assembly in Resolve was done by hand through the MCP (2026-10-10, a podcast client: 8 timelines): want `ea podcast <p> --intro <file> --overlap 0.5` that writes the trimmed episode (and multi-file joins, e.g. a part-2 opener from a second file) as timeline.json with the intro on V2/A2, bakes the intro fade as an alpha .mov, and builds it via resolve_native (with set_current_folder before each create).
- resolve_native: fades/dissolves on overlay tracks could be baked as alpha .mov (ProRes 4444 + fade alpha) instead of only reported, since 21.0 has no SetFades/AddKeyframe.

## Not yet verified (as of 2026-10-05)

- Desktop app: a successful agent turn (Claude and Codex were only run up to auth with invalid keys), the Codex ChatGPT login flow, Windows build/run, signed/notarized macOS build.

- Opening exports inside Resolve, Premiere and After Effects (AE only tested against `tests/ae_mock.js`).
- `ea export --open` creating a project in Resolve (only the scripting connection was tested).
- Resolve MCP tools that change a project: add_subfolder/set_current_folder worked 2026-10-06; import_timeline failed (same as direct API).
- `ea export --open --current` native fallback ran end to end on Resolve 21.0.0 on 2026-10-06 (50 clips, LUTs, 2x conform, zooms, subtitles; checked frame by frame against the preview). Off-centre zooms set via Pan/Tilt since 2026-10-09; push-in ramps still only reported.
- WHY Resolve 21.0.0 rejects our OTIO/XML via the API (try File > Import > Timeline by hand with the same file; try Resolve 21.1).
- FCPXML import in Final Cut (format names like `FFVideoFormat3840x2160xp23.97...` come from the adapter).
- Live API calls: ElevenLabs (tts, sfx, music, dubbing), Higgsfield generation, Pexels, pyannote.
- product-launch with a real brand/product and live ElevenLabs music (composition plan), VO and SFX kit (only synthetic audio tested).
- libass path of caption burn-in (dev machine's ffmpeg has no libass).

## Blocked / waiting on

- Windows verification — CI now runs on windows-latest; waiting on the fixes above.
- Higgsfield live test — waiting on API credentials in `.env`.
