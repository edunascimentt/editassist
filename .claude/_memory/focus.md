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
- resolve_native: V1 dissolves and the end fade are reported, not placed (21.0 has no transition API): the 15-anos recap (2026-10-13) needed 3 dissolves + a fade added by hand. Bake them (render the overlap as one clip) so Resolve matches the preview.
- `ea qa --shots` (or `ea scenes --timeline`): one frame from the middle of every V1 shot of a render on one sheet. Done with a scratch script on the 15-anos recap (2026-10-14); it caught a shot where the phone had panned to a white wall.
- resolve_native: fades/dissolves on overlay tracks could be baked as alpha .mov (ProRes 4444 + fade alpha) instead of only reported, since 21.0 has no SetFades/AddKeyframe.

- `ea sync --map/--build`: fit clock drift per piece (shift + rate) and split long pieces where it passes half a frame; today one median shift per piece (~40 ms at the ends of a 35-min piece, 2026-10-29). Also `--build` for every camera in one call.

## Premiere live bridge (built + verified on macOS Premiere 26.3.2, 2026-10-13)
- 2026-10-13 full pass: every MCP tool and edit action driven over stdio against live Premiere (90/90 checks), a build with LUT, vertical crop, Warp Stabilizer, push-in, dips, still, speed, captions, ducking and one-channel voice compared frame by frame and by audio level with `ea render`, `premiere_export`, new/open project, `--current`.
- Still unverified: Windows (no Windows machine or VM here; code reviewed and Windows paths/encodings unit-tested only), the MCP inside a real Claude session (stdio driven by a script, same protocol), Premiere with "Scale to frame size" on (pref read + math unit-tested only), anamorphic (non-square pixel) media: `ea render` ignores SAR, Premiere honours it.

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

## Team memory + review (from a team meeting, 2026-10-14)
- Team-shared memory tier: general + client prefs live only in each person's private memory today, so one editor's lessons never reach the others. Idea: a private team git repo layered as team > client > video type > editor; changes by PR, only the two senior editors approve (real access control; a folder password would sit in Claude's memory).
- Editor identity: ask "who uses this computer?" on first run (`ea whoami`), per-editor profile file, and "edit with <editor>'s preferences" loads it.
- Video types inside a client (testimonial, CTA, studio, scripted static): `clients/<c>/formats/<type>.md`; the team asked for "pattern per project/video type, not per client".
- `learn-edit` skill: read the live Resolve/Premiere timeline the editor just finished (or corrected), list what was done/changed, ask which tier to save it to. New team rule: every project passes through the AI before export.
- Independent reviewer subagent (`.claude/agents/reviewer.md`, fresh context): `ea qa`, a second transcription with another model to flag caption text errors, and an approval model built from each reviewer's criteria (agreement = standard, disagreement = taste/options).
- Memory history: "edit the line" rules lose what was removed and when; the team expects a dated history.

- (2026-10-20) `ea resolve-style <template> --from <styled .drp/.drt or timeline>`: automate the subtitle-style transplant done by hand for a podcast client's cortes (facts.md 2026-10-20), so a new client project gets the user's caption style without restyling.
- (2026-10-20) Captions from long podcast transcripts: Whisper loses punctuation in long stretches; want `ea transcript <p> --punct <bites>` (or a `--lines`-from-text helper) that re-punctuates chosen bites keeping word times, instead of a scratch script. Also capitalise the first caption of a video when the bite starts mid-sentence ("gaste menos" -> "Gaste").
- (2026-10-20) Captions sit at a fixed track Y (58 %): in a podcast wide two-shot the guest's head is lower and the line crosses his face for a few seconds; consider a per-shot check in `ea qa` (face box vs caption band).
- (2026-10-20) `ea level` should target the bed level AFTER ducking (measure the ducked stem, or know the duck depth) so a ducked bed sits at -30 under speech instead of -36..-41.
- (2026-10-21) `ea timeline <p> retrim <ranges>`: rebuild A1/V1 of a built (reformatted) timeline from new source ranges, keeping each shot's crop, filling dropped pauses with the shot before, J-cut leads, and re-fitting the music bed to a downbeat so its end still lands on the video end. Done with a scratch script to fix 3 podcast cortes.
- (2026-10-21) A second-model caption check (large-v3 on the low-probability words of the chosen bites) as an `ea qa --captions` step: it caught 2 of 3 caption text errors on the podcast cortes.
