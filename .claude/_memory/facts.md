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
- Remotion 4.0.532 `<Sequence playbackRate>` slows the picture; audio stays outside it (verified: 120 bpm bed still 120 bpm in a 1.5x-slowed render).
