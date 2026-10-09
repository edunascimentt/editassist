# Facts (this project)

> Durable project facts: conventions, endpoints, gotchas, where-things-live.
> One fact per line. Uncertain = `~` prefix.
>
> SHARED — written for the whole team. NO secrets/keys/tokens (env or a password manager),
> no personal emails, and no absolute paths from anyone's machine: write paths relative to
> the repo root. A key that is public BY DESIGN (already shipped in client code) is fine —
> say why it's public on the same line.

## Where things live
- One module per command group in `src/editassist/`; `cli.py` wires them. `videofx.py` = per-clip video filter chain shared by render and bake.
- Skills: `.claude/skills/<name>/SKILL.md` (32, 2026-10-05). Codex reads the same via `AGENTS.md`.
- Bundled assets: `assets/fonts/` (Montserrat, OFL) and `assets/models/face_detection_yunet_2023mar.onnx` (MIT). Captions/thumbnails depend on them; don't swap for system fonts.
- Per-project data: `projects/<name>/{input,work,output}` + `timeline.json`; `work/media.json` is the media catalog every command reads.
- memory-os lives in `vendor/memory-os/` (upstream commit ba838aa, 2026-10-05); `ea memory --install` copies it to `~/.memory-os` (leaves a git clone alone); CI runs its `check` on `.claude/_memory/`.
- Editing memory (user taste) is NOT in this repo: `uv run ea memory` prints its folder (memory-os global tier, else gitignored `memory/`).

- Desktop app: `app/src/main` (engine, agents, keys, projects), `app/src/renderer` (React UI), `app/src/shared/types.ts` (IPC contract, `window.ea`). Packaged engine lives in `~/Library/Application Support/editassist/engine`, its `projects/` links to the user's folder (`~/Movies/editassist`).

## Conventions
- Every `ea` command prints JSON (or short text) for the model to read; errors are `SystemExit` with a human message.
- Paths inside json are project-relative and POSIX (`Project.rel`), so Windows and macOS projects match.
- ffmpeg runs with `cwd=project dir` and filter args use relative paths: Windows drive letters (`C:`) break ffmpeg filter syntax (`:` is a separator).
- Times in timeline.json are seconds; `in`/`out` source time, `start` record time. Exports convert to frames from absolute times (no cumulative rounding drift).
- `-filter_complex_script` is gone in the newest ffmpeg; `media.filter_script_args()` uses `-/filter_complex <file>` on ffmpeg 7+ and the old option on 6.x (Ubuntu 24.04 apt).
- Template folders that start empty (`templates/launch/public/*`) don't survive git; code that needs them must `mkdir` them (`launch.new`).
- `ea resolve-mcp` must never print to stdout (it is the MCP JSON-RPC channel).

## Gotchas (learned the hard way, 2026-10-01/02)
- Homebrew ffmpeg 8 ships WITHOUT libass and drawtext: captions burn in via Pillow PNGs + concat demuxer fallback (`caption_frames.py`); contact sheets use Pillow, not drawtext.
- faster-whisper decoding through PyAV broke (`metadata_errors` kwarg); we pass a numpy array from the 16 kHz wav instead.
- PyAV (from faster-whisper) and OpenCV both bundle libavdevice; loading both in one process warns of crashes on macOS. Scene detection uses ffmpeg `select=scene` instead of PySceneDetect.
- Uninstalling one opencv wheel deletes the shared `cv2/` dir of another: fix with `uv sync --reinstall-package opencv-python-headless`.
- OpenCV 5 removed `CascadeClassifier` (Haar); use `cv2.FaceDetectorYN` (YuNet), works on 4.5.4+ and 5.x.
- Whisper `small` can silently drop a whole sentence; `transcribe` warns via `possibly_missed`. Default model `large-v3-turbo`.
- OTIO fcp_xml / fcpx_xml adapters do NOT write speed (LinearTimeWarp); `ea bake` renders speed/crop/zoom into files before NLE export.
- `.cube` LUT data order is red-fastest; verified against ffmpeg `lut3d` (mean diff 0.0006).
- Beat times: onset sits half a hop after the STFT frame centre (measured on synthetic tracks); phase vs off-beat chosen by low-band (kick) energy.
- GCC-PHAT lag window must be clamped to the FFT size, or short files wrap to nonsense offsets.
- Per-mic diarization: normalise each mic by its 95th-percentile frame RMS; per-sample percentiles amplify bleed.
- macOS system python3 is 3.9; the Resolve MCP needs 3.10+, so `ea resolve-mcp --setup` hands it this project's interpreter.
- Resolve external scripting (our `--open` and the MCP) works only on Resolve Studio.
- Remotion first render downloads a headless browser (~1 min in CI).
- Launch template (2026-10-02): CSS `mix-blend-mode: difference` glitch slices turn into black bars on light floods; use offset slices + an accent drop-shadow.
- Word-pop scale overshoot >5% makes neighbouring words collide ("Everyrequest"); keep the overshoot in the lift (y), cap scale.
- An accent word on a background that IS the accent colour disappears; `accentOn()` swaps to paper/ink.
- Incoming beats must show text from their first frame (title `at: 0`), or the wipe reveals a blank flood.
- One-pass and even two-pass linear `loudnorm` miss the target on short or peaky audio (-17.8 / -20.3 LUFS); `launch.normalize()` = measured gain + true-peak limiter, iterated (±0.5 LU).
- ffmpeg 6.1 (Ubuntu 24.04) `acrossfade` truncates the whole mix when one input is shorter than ~50 ms (verified in Docker 2026-10-05); `stretch_music` splices whole bars on detected downbeats so no sliver exists.
- Write and read text with `encoding="utf-8"` everywhere: Windows defaults to cp1252 and broke transcripts with accents (CI 2026-10-05).
- `stretch-music` must splice from the ORIGINAL bed (`music.source`), or repeated stretches compound and overwrite their input.
- Agent SDK (0.3.289) retries a 401 ten times with backoff (~minutes): the app watches `system/api_retry` and aborts on 401/403 (2026-10-05).
- Agent SDK ignores the `.claude/settings.json` allowlist until the workspace is trusted in its config dir: the app writes `projects[<engine>].hasTrustDialogAccepted` into its own `CLAUDE_CONFIG_DIR/.claude.json`.
- The Codex SDK has no interactive approvals; `error` events "Reconnecting… n/5" are transient, a 401 is fatal (app aborts).
- npm 11 blocks install scripts by default: `app/package.json` `allowScripts` approves electron and esbuild; Electron then downloads its binary on first run.
- GUI apps on macOS don't inherit the shell PATH: `app/src/main/paths.ts toolPath()` adds Homebrew and `~/.local/bin` for every child process.
- Native agent binaries must be in `asarUnpack` (electron-builder) and resolved via `app.asar.unpacked` (`paths.ts claudeExecutable/codexExecutable`).
- Remotion 4.0.532 `<Sequence playbackRate>` slows the picture; audio stays outside it (verified: 120 bpm bed still 120 bpm in a 1.5x-slowed render).

## Gotchas from the first real edit (2026-10-06, Sony ZV-E1 vertical 4K S-Log3 → Resolve Studio 21.0.0)
- Resolve 21.0.0 `MediaPool.ImportTimelineFromFile` returned None for our OTIO and FCP7 XML (even a 3-clip V1-only OTIO, any path, with/without options); ~cause unknown. `ea export --open` now falls back to `resolve_native.build` (AppendToTimeline clip infos, frame-exact when run by hand; the module itself is only tested against a fake API).
- Resolve 21.0 has no `TimelineItem.SetSpeed`/`SetFades` (21.1+) and audio items expose no Volume property: slow motion = a second pool copy of the 59.94 clip with `SetClipProperty("FPS", "23.976")` (Sony S&Q conform); SFX/music gains must be baked into the files; music ducking baked as a stem.
- `AppendToTimeline` source frames count the clip's own frames (59.94 clip: seconds × 59.94); a conformed copy keeps the same frame index.
- An imported .srt is a pool item of Type "Subtitle"; `AppendToTimeline([item])` after `AddTrack("subtitle")` places every cue at its SRT time.
- otio_fcpx_xml_adapter looks rates up by literal key (23.98/29.97/59.94): any NTSC timeline wrote an empty frameDuration and crashed. Fixed by `export.exact_fps` + `_fcpx_rates()`, which must patch the module returned by `otio.adapters.from_name("fcpx_xml").module()` (the plugin loader imports its own copy). Its READER still truncates 23.976 to 23 fps: check durations in the raw XML, not by reading it back.
- Captions: sizing by frame height overflowed vertical frames; subtitles.py and caption_frames.py now size by the short side, the Pillow path shrinks lines to 88% width and reads `accent` from work/captions.json. Without libass the render burns from work/captions.json, so hand edits to the .ass/.srt don't reach the preview.
- Remotion Title scaled by height (overflow on vertical); now by the short side, plus optional `y` (0..1) to clear on-screen logos.
- ffmpeg `sidechaincompress` ends at the KEY's EOF and also drops a variable tail it still buffers: `ea render` silenced the music after the last spoken word (the first real edit's v2 preview lost its last 5.4 s of audio; qa passed it). Fixed: `apad` both inputs, `atrim` to length (render.py and bake.duck_stem); qa now flags audio shorter than picture and silent stretches.
- Sony XAVC files carry `CaptureGammaEquation` (e.g. s-log3-cine) in an XML block at the END of the file; `tail -c 300000 | strings` finds it. Resolve's LUT folder ships Sony S-Log3 → Rec709 LUTs.
- ElevenLabs Music API answers 402 `paid_plan_required` on the free plan (TTS/SFX still work).
- `ea scenes` on single-shot clips gives one tile per clip: `--frames N` writes overview sheets (N moments per clip). Cut detection and `ea color` analysis read proxies; `ea color --lut` alone does no analysis (it took >5 min on 36 4K clips before).
- `ea render --out` used to resolve against the shell cwd (wrote to the repo root); it is project-relative now, like `--subs`.
- Bite padding (`ea cut`) used to swallow the previous word's tail; it now stops at neighbouring words.

## Gotchas from the second real edit (2026-10-06, client car reel, Resolve Studio 21.0.0)
- Resolve `SetLUT` only accepts a .cube inside Resolve's LUT folders (returns False for work/color/*.cube): resolve_native uses the user's creative LUT itself when the grade is just that LUT, else copies the cube to `<LUT dir>/editassist/<project>/` + `RefreshLUTList` (`lut_for_resolve`, `_install_lut`).
- Speed-up without bake works on 21.0: a pool copy conformed with `SetClipProperty("FPS", "119.88")` plays 2x in a 59.94 timeline (23.976 -> 47.952 too). resolve_native conforms any speed whose `src fps x speed` is a Resolve rate (`CONFORM_RATES`), one copy per (file, rate) in `editassist/speed <rate>` bins; others still need `ea bake`.
- Resolve 21.0 audio items take no Volume: resolve_native places audio clips that have gain/fade as rendered copies (`bake.gain_copies`, work/baked/gain_*.wav).
- `ea render` showed the black base for one frame at most cuts with 59.94 sources and cut times between output frames (the outgoing stream hit EOF a frame early; overlay `enable` compared an inexact t). Fixed: clip edges snapped to the frame grid, last frame held (`tpad`), half-frame margins on `enable`. `ea qa` did not see it (single-frame blacks): check renders with `blackdetect=d=0`.
- Ingest catalogues symlinks in input/ by their resolved target; clips written as `input/x.mp4` matched nothing by path (empty captions, no LUT, no duration check). `ea timeline validate` now rewrites them (`timeline.normalize_media`).
- zsh does not word-split an unquoted `$ids`: `ea color --media $ids` got one id and graded nothing; `color.grade` now errors on unknown ids.
- Scripting `LoadProject` while "Untitled Project" is current opens a modal "Save Current Project" dialog in the UI and the call hangs until a human answers it; ask the user to open projects instead. Loading one old client project (several in a row) crashed Resolve 21.0.0 once; run one load per process and save first.
- Studying a client's past edits: load each project and read timelines (items, source in/out -> speed, `GetProperty` Zoom/Pan/Tilt, `GetNodeGraph().GetLUT(1)`, Fusion TextPlus, subtitle items); render jobs show where finals went. Was a one-off script (see focus.md).
- `ea qa` caption checks read work/captions.json even when a `--lines`/`--name` captions file is the one burned.
- (second edit, after feedback) resolve_native rounded record start and source span separately: 1-frame holes at most cuts in Resolve. The source span now follows the record span (`endFrame = startFrame + record frames x play rate / fps`).
- Resolve subtitle STYLE (font, size, position) is a property of the subtitle track (Sm2TiTrack FieldsBlob, zstd protobuf with a Qt font string like `Inter,13,-1,5,63,...,SemiBold`); no API reads or sets it. `ea export --template "<styled timeline>"` builds inside an emptied DuplicateTimeline copy so the style survives. `ExportProject` to a scratch .drp is how to read a style.
- A pool .srt keeps the cues of its first import: re-importing the same path after editing captions gave stale text. resolve_native imports a content-hashed copy each build.
- Raw lav dialogue is ~-25..-30 LUFS and mastered music ~-8..-12: a guessed `gain_db: -12` bed sat at the voice's level. `ea level` measures each clip (ebur128 on its segment) and sets gains by role; `ea qa` warns when gains were never measured. Check balance by rendering voice-only / music-only mixes WITHOUT the final loudnorm (each stem loudnormed alone compares nothing).
- `ea shake`: jitter = RMS of frame-to-frame phase-correlation motion minus its 0.5 s average, % of width; > 0.6 = handheld. Motion graphics (a logo sting with light streaks) read as shake: set `"stabilize": false` on them. Resolve's `TimelineItem.Stabilize()` works on 21.0 and zooms in a little; preview uses ffmpeg `deshake` (no vidstab in Homebrew ffmpeg).
- Whisper word ends land early and lone short words get hallucinated in engine noise ("A" during a launch): `ea cut` pads 0.12 s in / 0.30 s out; captions include words that START inside a kept clip and drop isolated 1-2 letter words.
- zsh: `for seg in "1 18"; do set -- $seg` does not split either; use explicit fields.
- Cameras/recorders often record dual-mic stereo: lav on L, car or camera mic on R. Played as stereo the voice sits in one ear; measured as stereo the other mic's noise counted as voice and `ea level` turned the voice DOWN (in-car take: -14 LUFS stereo, -18 voice alone). `ea level` now judges each media file (voice side = wider level spread between words and pauses; a channel 20 dB quieter = empty) and sets `channel`. Resolve 21.0 scripting has no per-clip channel mapping: gain copies bake the chosen side to dual mono, and `MediaPoolItem.ReplaceClip` on an existing gain copy swaps the audio in place without touching the user's timeline.

## 2026-10-08 (inauguração edit, 128 clips 4K 10-bit 4:2:2 S-Log3)
- Transcription dictionary: `<memory>/vocabulary.md` (user's private memory, `ea vocab`); `ea transcribe` passes its terms as faster-whisper `hotwords` and fixes new transcripts, `ea vocab <p> --apply` fixes existing ones, `ea subtitles` re-applies it. `[scope]` = project-name substring.
- `subtitles.apply_fixes` doubled punctuation when the right side had its own ("Olá!!") and re-replaced already-right words; both fixed (skip span already equal).
- Sony 4K H.264 4:2:2 10-bit: VideoToolbox can't decode it ("hardware accelerator failed"), software decode ~0.5x realtime with ~4 cores; ingest now writes media.json BEFORE proxies, runs proxies in parallel (cpu/4 workers) and writes them via `.part` (an interrupted run used to leave a truncated proxy that was reused).
- resolve_native: a 59.94 source in a 23.976 timeline needs whole multiples of 2.5 source frames; `round()` of x.5 spans gave Resolve 36.8 frames, truncated to 36 = 1-frame holes. Source span is now `ceil`; clips ending < 1 frame from the next one butt it; the timeline frame rate is set (project rate when it has no timeline yet, else refuse). Check `snapshot gaps_overlaps` after every build.
- Builders must put cut times on the frame grid (`ea qa` now flags video cuts whose rounded frames differ); `cut.resolve_segments` already pads without reaching neighbouring words, reuse it instead of re-implementing.
- `ea qa --render` judges a 540p preview against the preview target (-16) and ignores fades to black at clip heads/tails; `ea shake` skips work/motion overlays; `ea subtitles` keeps multi-word dictionary terms on one line; `--fix` takes several values.
- MCP `timeline thumbnail_contact_sheet` can return black or stale frames right after a build; re-sample before calling a frame broken.
- Whisper can squeeze a word (prefeita's "habitantes" 0.16 s) when another voice follows without a pause; `cut.resolve_segments` then ends the bite at the audible end (`cut.audible_end`, noise floor + 6 dB) instead of clamping to the next word. `ea qa` errors when A1 dialogue and a V1 clip of the same file drift apart (sound piece cut, picture kept running).
- Remotion Title takes `upper`, `size`, `maxWidth`, `weight` and a user font: `ea motion --props '{"font": "<file>"}'` copies it to assets/user-fonts/ (gitignored; SF Pro may not be bundled) and passes `fontFile`. Motion file names use ms stamps (two renders in one second overwrote each other).
- MCP `timeline thumbnail_contact_sheet` draws every frame that has a ProRes 4444 overlay (titles, lower thirds) as solid black: not a timeline fault. `MediaPoolItem.ReplaceClip` swaps a title in place in an existing timeline.
- Several videos from one project (a recap + content cuts): `ea timeline <p> save <slot>` / `load <slot>` / `slots` keep each timeline in `timelines/<slot>.json` with its own captions; `load` refuses to drop unsaved work. `ea subtitles` stamps captions.json with the timeline name and qa/AE export ignore captions made for another timeline (a builder rewriting timeline.json used to inherit the recap's captions). `ea qa` warns when an overlay (end title) runs past the last V1 picture.
- Single-pass `loudnorm` misses the target on music with a wide range (music-only reel: loud montage, soft outro came out -15.7 for -14). `ea render` now measures the file and trims the gain in a remux (video copied, true peak kept under the preset's).
- Resolve: every built/imported timeline is filed by `resolve_native.file_timeline` into the root bin `TIMELINES FINAIS`; older versions of the same name (`version_base` strips `vN`, also "v1 v1") move to `editassist/versões antigas`. `Timeline.GetMediaPoolItem()` + `MediaPool.MoveClips` work on Studio 21.0; creating a bin selects it, so the current bin is restored.
- Team sync (`sync` skill): colleagues update from `origin/main`; feature branches are published with a fast-forward `git push origin HEAD:main` after merging `origin/main` in, never `--force`. `.gitattributes` sets `merge=union` on `.claude/_memory/{facts,decisions,people}.md` (tested: two people appending to facts.md rebase cleanly, both lines kept); `_index.md`/`focus.md` still conflict on purpose (lines get edited, not only added).
- Per-client preferences: `clients.py` + `ea client list|new|set|show`; `<memory>/clients/<slug>/preferences.md` from `memory.template/clients/_template/` (`init_memory` copies `_template` too; `all_clients` skips `_` folders). Slugs drop accents ("Ótica São João" -> otica-sao-joao) so folders match on every OS. `vocab` `[scope]` now matches the project name OR its client slug. `clients.py` reads `P.PROJECTS` at call time (a `from .project import PROJECTS` copy ignored the test monkeypatch).
