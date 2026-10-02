"""`ea`: the command line the AI editor drives. Every command prints JSON or short text so the
model can read results directly. Run `ea <command> -h` for options."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .project import Project, read_json


def out(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False) if not isinstance(obj, str) else obj)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["resolve-mcp"]:  # MCP stdio server: hand stdout over untouched, before anything prints
        from . import resolve_mcp
        rest = argv[1:]
        if "--setup" in rest:
            i = rest.index("--setup")
            ver = rest[i + 1] if len(rest) > i + 1 and not rest[i + 1].startswith("-") else resolve_mcp.VERSION
            sys.exit(resolve_mcp.setup(ver))
        sys.exit(resolve_mcp.serve(rest))
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="ea", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="create a project folder")
    p.add_argument("name"); p.add_argument("--fps", type=float); p.add_argument("--width", type=int)
    p.add_argument("--height", type=int); p.add_argument("--language"); p.add_argument("--platform")

    p = sub.add_parser("ingest", help="catalog input/ media, extract analysis audio")
    p.add_argument("project"); p.add_argument("--proxies", action="store_true")

    p = sub.add_parser("transcribe", help="word-level transcripts (faster-whisper)")
    p.add_argument("project"); p.add_argument("--model"); p.add_argument("--language")
    p.add_argument("--only", nargs="*"); p.add_argument("--force", action="store_true")

    p = sub.add_parser("scenes", help="shot detection + keyframes + contact sheets")
    p.add_argument("project"); p.add_argument("--threshold", type=float, default=0.3, help="scene score 0..1, lower = more cuts")
    p.add_argument("--only", nargs="*")

    p = sub.add_parser("find", help="exact times of a phrase in the transcripts")
    p.add_argument("project"); p.add_argument("phrase"); p.add_argument("--media")

    p = sub.add_parser("silence-cut", help="timeline from speech only (drops pauses + hesitations)")
    p.add_argument("project"); p.add_argument("--media", nargs="*", help="media ids in order (default: all with audio)")
    p.add_argument("--min-silence", type=float, default=0.45); p.add_argument("--pad", type=float, default=0.08)
    p.add_argument("--keep-fillers", action="store_true")

    p = sub.add_parser("cut", help="timeline from a segments json written by the model")
    p.add_argument("project"); p.add_argument("segments", help="path to segments json (list)")
    p.add_argument("--tighten", action="store_true", help="also remove pauses inside each segment")
    p.add_argument("--min-silence", type=float, default=0.45)

    p = sub.add_parser("timeline", help="show or validate timeline.json")
    p.add_argument("project"); p.add_argument("action", choices=["info", "validate", "json", "ripple"], nargs="?", default="info")

    p = sub.add_parser("subtitles", help="captions on the edited timeline (.srt + styled .ass)")
    p.add_argument("project"); p.add_argument("--style", default="clean", choices=["clean", "bold", "boxed"])
    p.add_argument("--max-words", type=int, default=4); p.add_argument("--no-karaoke", action="store_true")
    p.add_argument("--lines", help="timed text json [{start,end,text}] (e.g. a translation) instead of the transcript")
    p.add_argument("--name", help="output base name, e.g. <project>_en")

    p = sub.add_parser("transcript", help="transcript of the EDITED video on timeline time (chapters, notes, translation)")
    p.add_argument("project")

    p = sub.add_parser("chapters", help="validated YouTube chapters + timeline markers from [{time, title}]")
    p.add_argument("project"); p.add_argument("file", help="json list [{time, title}] (timeline seconds)")

    p = sub.add_parser("thumbnail", help="no --text: candidate frames sheet; with --text: compose the thumbnail")
    p.add_argument("project"); p.add_argument("--text", help="headline; *word* = accent colour")
    p.add_argument("--pick", type=int, help="candidate index"); p.add_argument("--media"); p.add_argument("--t", type=float)
    p.add_argument("--image", help="background image instead of a frame"); p.add_argument("--aspect", default="16:9", choices=["16:9", "9:16", "1:1", "4:5"])
    p.add_argument("--accent", default="#FFE500"); p.add_argument("--out"); p.add_argument("-n", type=int, default=12)

    p = sub.add_parser("dub", help="ElevenLabs dubbing of a dialogue render into another language")
    p.add_argument("project"); p.add_argument("--lang", required=True, help="target ISO 639-1, e.g. en, es")
    p.add_argument("--source", required=True, help="file to dub (project-relative), see the dub skill")
    p.add_argument("--source-lang"); p.add_argument("--speakers", type=int, default=0, help="0 = detect")

    p = sub.add_parser("reformat", help="change aspect ratio with face-aware crops")
    p.add_argument("project"); p.add_argument("--aspect", default="9:16")
    p.add_argument("--bake", action="store_true", help="render cropped clips so NLE exports keep the framing")

    p = sub.add_parser("render", help="render timeline to mp4")
    p.add_argument("project"); p.add_argument("--preset", default="preview",
                                              choices=["preview", "youtube", "instagram", "tiktok", "podcast", "broadcast"])
    p.add_argument("--subs", help="burn this .ass/.srt (project-relative)"); p.add_argument("--out")

    p = sub.add_parser("export", help="editable project for Resolve / Premiere / After Effects")
    p.add_argument("project"); p.add_argument("--to", nargs="+", default=["resolve", "premiere", "aftereffects"],
                                              choices=["resolve", "premiere", "fcpx", "aftereffects", "all"])
    p.add_argument("--open", action="store_true", help="auto-import into a running DaVinci Resolve")

    p = sub.add_parser("qa", help="automatic checks on timeline, captions and (optionally) a render")
    p.add_argument("project"); p.add_argument("--render"); p.add_argument("--preset", default="youtube")

    p = sub.add_parser("voiceover", help="ElevenLabs text to speech")
    p.add_argument("project"); p.add_argument("text"); p.add_argument("--voice")
    p.add_argument("--model", default="eleven_multilingual_v2")
    sub.add_parser("voices", help="list ElevenLabs voices")

    p = sub.add_parser("sfx", help="ElevenLabs sound effect")
    p.add_argument("project"); p.add_argument("prompt"); p.add_argument("--seconds", type=float)

    p = sub.add_parser("music", help="ElevenLabs music")
    p.add_argument("project"); p.add_argument("prompt"); p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--vocals", action="store_true")

    p = sub.add_parser("broll", help="search (and download) stock b-roll from Pexels")
    p.add_argument("project"); p.add_argument("query"); p.add_argument("--orientation", choices=["landscape", "portrait", "square"])
    p.add_argument("-n", type=int, default=5); p.add_argument("--download", type=int, default=0)

    p = sub.add_parser("register", help="add an external file (Higgsfield, Remotion, asset) to media.json")
    p.add_argument("project"); p.add_argument("file"); p.add_argument("--kind", default="broll"); p.add_argument("--note", default="")

    p = sub.add_parser("motion", help="render a Remotion composition (motion graphics / captions)")
    p.add_argument("project"); p.add_argument("composition", help="Captions | LowerThird | Title")
    p.add_argument("--props", default="{}", help="json string or path to a .json file"); p.add_argument("--seconds", type=float)

    p = sub.add_parser("zoom", help="punch-ins: alternate framing on cuts, or emphasis zoom at a moment")
    p.add_argument("project"); p.add_argument("--punch", action="store_true", help="alternate punch-in on consecutive clips")
    p.add_argument("--every", type=int, default=2); p.add_argument("--scale", type=float)
    p.add_argument("--at", type=float, help="timeline seconds"); p.add_argument("--dur", type=float, default=1.5)
    p.add_argument("--ramp", type=float, default=0.0, help="push-in over N seconds instead of a hard punch")
    p.add_argument("--clear", action="store_true")

    p = sub.add_parser("transition", help="dissolve / dip / fade at cuts")
    p.add_argument("project"); p.add_argument("--at", type=float, nargs="*", help="timeline seconds (nearest cut)")
    p.add_argument("--all", action="store_true"); p.add_argument("--type", default="dissolve", choices=["dissolve", "dip", "fade"])
    p.add_argument("--dur", type=float, default=0.5); p.add_argument("--tracks", nargs="+", default=["V1", "A1"])
    p.add_argument("--fade-in", type=float, default=0.0, help="fade from black at start")
    p.add_argument("--fade-out", type=float, default=0.0, help="fade to black at end")
    p.add_argument("--clear", action="store_true")

    p = sub.add_parser("color", help="auto grade, match cameras, looks, LUTs (one .cube per media)")
    p.add_argument("project"); p.add_argument("--media", nargs="*"); p.add_argument("--auto", action="store_true")
    p.add_argument("--match", help="reference media id the others should match")
    p.add_argument("--look", choices=["warm", "cool", "punchy", "film", "bw"]); p.add_argument("--lut", help="creative .cube to add")
    p.add_argument("--strength", type=float, default=1.0); p.add_argument("--reset", action="store_true")
    p.add_argument("--compare", help="media id: write a before/after still")

    p = sub.add_parser("bake", help="render crop/zoom (and --color) into files so NLE exports match")
    p.add_argument("project"); p.add_argument("--color", action="store_true", help="also bake the grade")

    p = sub.add_parser("beats", help="tempo, beats and downbeats of a music media (work/beats/<id>.json)")
    p.add_argument("project"); p.add_argument("media")

    p = sub.add_parser("snap", help="move insert clips (b-roll, motion, sfx) onto the music's beats")
    p.add_argument("project"); p.add_argument("--music", required=True, help="music media id (with ea beats done)")
    p.add_argument("--tracks", nargs="+", default=["V2"]); p.add_argument("--downbeats", action="store_true")
    p.add_argument("--max-shift", type=float, default=0.25)

    p = sub.add_parser("montage", help="beat-cut montage from a list of shots")
    p.add_argument("project"); p.add_argument("--music", required=True); p.add_argument("segments", help="json list [{media, in}]")
    p.add_argument("--every", type=int, default=2, help="beats per shot"); p.add_argument("--start-beat", type=int, default=0)
    p.add_argument("--track", default="V1"); p.add_argument("--music-gain", type=float, default=-6.0)

    p = sub.add_parser("sync", help="align cameras/mics by sound; swap to external audio; switch camera angles")
    p.add_argument("project"); p.add_argument("--ref", help="reference media id (main camera)")
    p.add_argument("others", nargs="*", help="media ids to align to --ref")
    p.add_argument("--swap-audio", nargs=2, metavar=("FROM", "TO"), help="replace A1 dialogue from FROM with synced TO")
    p.add_argument("--switch", nargs=3, metavar=("T0", "T1", "CAMERA"), help="show CAMERA on timeline [T0, T1)")

    p = sub.add_parser("diarize", help="who speaks when: per-mic tracks or automatic (pyannote extra)")
    p.add_argument("project"); p.add_argument("media", help="transcribed media id")
    p.add_argument("--tracks", nargs="+", metavar="NAME=MEDIA", help="one mic per speaker, e.g. Ana=mic_ana Bruno=mic_bruno")
    p.add_argument("--speakers", type=int, help="number of speakers (auto mode)")
    p.add_argument("--names", nargs="*", help="names for S1, S2... in order of appearance (auto mode)")

    p = sub.add_parser("hf", help="Higgsfield: generated video/images (models, schema, estimate, generate, fetch)")
    hs = p.add_subparsers(dest="hf", required=True)
    q = hs.add_parser("models", help="catalog from docs.higgsfield.ai (cached 7 days)")
    q.add_argument("--kind", choices=["video", "image"]); q.add_argument("--search"); q.add_argument("--refresh", action="store_true")
    q = hs.add_parser("schema", help="endpoint id, usage notes and JSON input schema of one model")
    q.add_argument("endpoint")
    q = hs.add_parser("estimate", help="credit / USD estimate for a request")
    q.add_argument("endpoint"); q.add_argument("--args", default="{}", help="json string or .json file")
    q = hs.add_parser("generate", help="estimate, submit, wait, download, register in the project")
    q.add_argument("project"); q.add_argument("endpoint")
    q.add_argument("--args", default="{}", help="json string or .json file (model input fields)")
    q.add_argument("--file", action="append", default=[], help="field=local/path: upload and set that field")
    q.add_argument("--name", help="base name for the downloaded files")
    q.add_argument("--yes", action="store_true", help="allow estimates above EA_HF_MAX_USD")
    q.add_argument("--timeout", type=float, default=30, help="minutes to wait")
    q = hs.add_parser("fetch", help="resume a submitted request: wait, download, register")
    q.add_argument("project"); q.add_argument("request_id"); q.add_argument("--timeout", type=float, default=30)

    p = sub.add_parser("resolve-mcp", help="DaVinci Resolve MCP server (used by .mcp.json); --setup [version] installs it")
    p.add_argument("--setup", nargs="?", const="")

    p = sub.add_parser("launch", help="product launch film in Remotion (product-launch skill)")
    ls = p.add_subparsers(dest="launch", required=True)
    q = ls.add_parser("new", help="scaffold projects/<p>/launch from the template")
    q.add_argument("project"); q.add_argument("--seconds", type=float, default=50); q.add_argument("--fps", type=int, default=30)
    q.add_argument("--size", default="1920x1080"); q.add_argument("--font", help="brand font, heavy weight (.ttf/.otf)")
    q.add_argument("--font-bold", help="brand font, bold weight"); q.add_argument("--font-name"); q.add_argument("--no-install", action="store_true")
    q = ls.add_parser("reference", help="study a reference film: brightness fix, 2 fps sheets, 30 fps strips at cuts")
    q.add_argument("project"); q.add_argument("video"); q.add_argument("--fps", type=float, default=2.0)
    q = ls.add_parser("stills", help="render frames and tile them into labelled contact sheets")
    q.add_argument("project"); q.add_argument("--comp", default="Film"); q.add_argument("--every", type=int, default=0)
    q.add_argument("--frames", default=""); q.add_argument("--range", default=""); q.add_argument("--scale", type=float, default=0.5)
    q.add_argument("--size", help="render another format, e.g. 1080x1920")
    q = ls.add_parser("audit", help="storyboard, copy, palette, glyph, audio checks; --motion measures UI density")
    q.add_argument("project"); q.add_argument("--motion", action="store_true")
    q = ls.add_parser("sfx-kit", help="generate (or reuse cached) UI sound kit via ElevenLabs")
    q.add_argument("project"); q.add_argument("--kinds", nargs="*")
    q = ls.add_parser("vo", help="voice-over: one line per beat [{beat, text, offset}]")
    q.add_argument("project"); q.add_argument("lines"); q.add_argument("--voice")
    q.add_argument("--stability", type=float, default=0.3); q.add_argument("--similarity", type=float, default=0.8)
    q.add_argument("--style", type=float, default=0.5); q.add_argument("--speed", type=float, default=1.05)
    q = ls.add_parser("music", help="music composed to the cut from a section plan (ElevenLabs composition plan)")
    q.add_argument("project"); q.add_argument("plan"); q.add_argument("--gain", type=float, default=-6); q.add_argument("--duck", type=float, default=-9)
    q = ls.add_parser("stretch-music", help="lengthen the music bed by looping its groove on bar lines (no credits)")
    q.add_argument("project"); q.add_argument("seconds", type=float)
    q = ls.add_parser("render", help="render, normalise to -16 LUFS without re-encoding video, verify")
    q.add_argument("project"); q.add_argument("--comp", default="Film"); q.add_argument("--size"); q.add_argument("--out")
    q = ls.add_parser("verify", help="check a rendered file: frames, size, sheet every 3 s, loudness")
    q.add_argument("project"); q.add_argument("file")

    p = sub.add_parser("keys", help="API keys: status (masked), --check validates for free, `set NAME` reads the value from stdin")
    p.add_argument("action", nargs="?", default="status", choices=["status", "set"])
    p.add_argument("name", nargs="?"); p.add_argument("--check", action="store_true"); p.add_argument("--only", nargs="*")

    sub.add_parser("selftest", help="run the test suite on synthetic media (no keys, no downloads)")

    p = sub.add_parser("memory", help="where this user's editing memory lives; --init seeds/migrates it")
    p.add_argument("--init", action="store_true")

    sub.add_parser("doctor", help="check that every dependency and key is in place")

    a = ap.parse_args(argv)

    if a.cmd == "new":
        pr = Project.create(a.name, fps=a.fps, width=a.width, height=a.height, language=a.language, platform=a.platform)
        out({"project": str(pr.dir), "drop_media_into": str(pr.path("input"))})
    elif a.cmd == "ingest":
        from .ingest import ingest
        cat = ingest(Project(a.project), proxies=a.proxies)
        out({k: {x: v[x] for x in ("path", "kind", "duration", "width", "height", "fps", "has_audio") if x in v}
             for k, v in cat.items()})
    elif a.cmd == "transcribe":
        from .transcribe import transcribe
        pr = Project(a.project)
        done = transcribe(pr, a.model, a.language, a.only, a.force)
        out({"transcribed": done, "read": [f"work/transcripts/{d}.txt" for d in done]})
    elif a.cmd == "scenes":
        from .scenes import detect
        pr = Project(a.project)
        res = detect(pr, a.threshold, only=a.only)
        out({"scenes": res, "look_at": sorted(str(pr.rel(p)) for p in pr.path("work", "frames").glob("*/contact_*.jpg"))})
    elif a.cmd == "find":
        from .cut import find_phrase
        out(find_phrase(Project(a.project), a.phrase, a.media))
    elif a.cmd == "silence-cut":
        from . import timeline as T
        from .cut import speech_segments
        from .ingest import media_by_id
        pr = Project(a.project)
        ids = a.media or [k for k, m in media_by_id(pr).items() if m.get("has_audio") and not m.get("derived")]
        segs = [s for sid in ids for s in speech_segments(pr, sid, a.min_silence, a.pad, not a.keep_fillers)]
        tl = T.from_segments(pr, segs)
        T.save(pr, tl)
        out(T.summary(tl))
    elif a.cmd == "cut":
        from . import timeline as T
        from .cut import build
        pr = Project(a.project)
        spec = read_json(Path(a.segments)) if Path(a.segments).exists() else read_json(pr.path(a.segments))
        if spec is None:
            raise SystemExit(f"segments file not found: {a.segments}")
        tl = build(pr, spec, tighten=a.tighten, min_silence=a.min_silence)
        T.save(pr, tl)
        out(T.summary(tl))
    elif a.cmd == "timeline":
        from . import timeline as T
        pr = Project(a.project)
        tl = T.load(pr)
        if a.action == "validate":
            probs = T.validate(pr, tl)
            out({"ok": not probs, "problems": probs})
        elif a.action == "json":
            out(tl)
        elif a.action == "ripple":
            closed = T.ripple(tl)
            T.save(pr, tl)
            out({"closed_seconds": closed, "length": round(T.length(tl), 3)})
        else:
            out(T.summary(tl))
    elif a.cmd == "subtitles":
        from .subtitles import build, from_lines
        pr = Project(a.project)
        if a.lines:
            if not a.name:
                raise SystemExit("--lines needs --name (e.g. <project>_en)")
            out(from_lines(pr, a.lines, a.name, a.style))
        else:
            out(build(pr, a.style, a.max_words, not a.no_karaoke, a.name))
    elif a.cmd == "transcript":
        from .subtitles import transcript
        out(transcript(Project(a.project)))
    elif a.cmd == "chapters":
        from .chapters import chapters
        pr = Project(a.project)
        spec = read_json(Path(a.file)) if Path(a.file).is_file() else read_json(pr.path(a.file))
        out(chapters(pr, spec))
    elif a.cmd == "thumbnail":
        from . import thumbnail as th
        pr = Project(a.project)
        if a.text is None:
            out(th.candidates(pr, a.n))
        else:
            out(th.compose(pr, a.text, a.pick, a.media, a.t, a.image, a.aspect, a.accent, a.out))
    elif a.cmd == "dub":
        from .generate import dub
        out(dub(Project(a.project), a.lang, a.source, a.source_lang, a.speakers))
    elif a.cmd == "reformat":
        from .reformat import reformat
        out(reformat(Project(a.project), a.aspect, a.bake))
    elif a.cmd == "render":
        from .render import render
        pr = Project(a.project)
        out({"rendered": pr.rel(render(pr, a.preset, a.out, a.subs))})
    elif a.cmd == "export":
        from .export import TARGETS, export
        targets = list(TARGETS) if "all" in a.to else a.to
        out(export(Project(a.project), targets, a.open))
    elif a.cmd == "qa":
        from .qa import check
        out(check(Project(a.project), a.render, a.preset))
    elif a.cmd == "voiceover":
        from .generate import voiceover
        out(voiceover(Project(a.project), a.text, a.voice, a.model))
    elif a.cmd == "voices":
        from .generate import voices
        out(voices())
    elif a.cmd == "sfx":
        from .generate import sfx
        out(sfx(Project(a.project), a.prompt, a.seconds))
    elif a.cmd == "music":
        from .generate import music
        out(music(Project(a.project), a.prompt, a.seconds, not a.vocals))
    elif a.cmd == "broll":
        from .generate import broll_search
        out(broll_search(Project(a.project), a.query, a.orientation, a.n, a.download))
    elif a.cmd == "register":
        from .generate import register_file
        out(register_file(Project(a.project), a.file, a.kind, a.note))
    elif a.cmd == "motion":
        from .motion import render_motion
        props = read_json(Path(a.props)) if Path(a.props).is_file() else json.loads(a.props)
        out(render_motion(Project(a.project), a.composition, props, a.seconds))
    elif a.cmd == "diarize":
        from . import diarize as dz
        pr = Project(a.project)
        if a.tracks:
            out(dz.by_tracks(pr, a.media, dict(t.split("=", 1) for t in a.tracks)))
        else:
            out(dz.auto(pr, a.media, a.speakers, a.names))
    elif a.cmd == "sync":
        from . import sync as sy
        pr = Project(a.project)
        if a.swap_audio:
            out(sy.swap_audio(pr, *a.swap_audio))
        elif a.switch:
            out(sy.switch(pr, float(a.switch[0]), float(a.switch[1]), a.switch[2]))
        elif a.ref and a.others:
            out(sy.sync(pr, a.ref, a.others))
        else:
            raise SystemExit("use --ref <id> <others...>, --swap-audio FROM TO, or --switch T0 T1 CAMERA")
    elif a.cmd == "beats":
        from .beats import detect
        out(detect(Project(a.project), a.media))
    elif a.cmd == "snap":
        from .beats import snap
        out(snap(Project(a.project), a.music, a.tracks, a.downbeats, a.max_shift))
    elif a.cmd == "montage":
        from .beats import montage
        pr = Project(a.project)
        spec = read_json(Path(a.segments)) if Path(a.segments).is_file() else read_json(pr.path(a.segments))
        out(montage(pr, a.music, spec, a.every, a.start_beat, a.track, a.music_gain))
    elif a.cmd == "zoom":
        from . import zoom
        pr = Project(a.project)
        if a.clear:
            out(zoom.clear(pr))
        elif a.at is not None:
            out(zoom.at(pr, a.at, a.dur, a.scale or 1.2, a.ramp))
        elif a.punch:
            out(zoom.punch(pr, a.scale or 1.12, a.every))
        else:
            raise SystemExit("use --punch, --at <seconds> or --clear")
    elif a.cmd == "transition":
        from . import transitions as tr
        pr = Project(a.project)
        if a.clear:
            out(tr.clear(pr))
        else:
            res = {}
            if a.at or a.all:
                res.update(tr.set_at(pr, a.at, a.type, a.dur, tuple(a.tracks), a.all))
            if a.fade_in or a.fade_out:
                res.update(tr.fades(pr, a.fade_in, a.fade_out))
            out(res or "nothing to do: --at, --all, --fade-in, --fade-out or --clear")
    elif a.cmd == "color":
        from . import color
        pr = Project(a.project)
        if a.compare:
            out({"compare": color.compare(pr, a.compare)})
        else:
            out(color.grade(pr, a.media, a.auto, a.match, a.look, a.lut, a.strength, a.reset))
    elif a.cmd == "bake":
        from .bake import bake
        out(bake(Project(a.project), a.color))
    elif a.cmd == "hf":
        from . import higgsfield as hf

        def js(v):
            return read_json(Path(v)) if Path(v).is_file() else json.loads(v)

        if a.hf == "models":
            items = hf.models(a.refresh, a.kind)
            if a.search:
                q = a.search.lower()
                items = [i for i in items if q in (i["name"] + i["endpoint"] + i["summary"]).lower()]
            out([{k: i[k] for k in ("endpoint", "name", "kind", "summary")} for i in items])
        elif a.hf == "schema":
            out(hf.schema(a.endpoint))
        elif a.hf == "estimate":
            out(hf.estimate(a.endpoint, js(a.args)))
        elif a.hf == "generate":
            out(hf.generate(Project(a.project), a.endpoint, js(a.args), a.file, a.yes, a.timeout, a.name))
        elif a.hf == "fetch":
            out(hf.fetch(Project(a.project), a.request_id, timeout_min=a.timeout))
    elif a.cmd == "launch":
        from . import launch as L
        pr = Project(a.project)
        k = a.launch
        if k == "new":
            out(L.new(pr, a.seconds, a.fps, a.size, a.font, a.font_bold, a.font_name, not a.no_install))
        elif k == "reference":
            out(L.reference(pr, a.video, a.fps))
        elif k == "stills":
            out(L.stills(pr, a.comp, a.every, a.frames, a.range, a.scale, a.size))
        elif k == "audit":
            out(L.audit(pr, a.motion))
        elif k == "sfx-kit":
            out(L.sfx_kit(pr, a.kinds))
        elif k == "vo":
            out(L.vo(pr, a.lines, a.voice, a.stability, a.similarity, a.style, a.speed))
        elif k == "music":
            out(L.music(pr, a.plan, a.gain, a.duck))
        elif k == "stretch-music":
            out(L.stretch_music(pr, a.seconds))
        elif k == "render":
            out(L.render(pr, a.comp, a.size, a.out))
        elif k == "verify":
            out(L.verify(pr, a.file))
    elif a.cmd == "keys":
        from . import keys as K
        if a.action == "set":
            if not a.name:
                raise SystemExit("usage: ea keys set NAME   (value on stdin, e.g. from a file or a pipe)")
            value = sys.stdin.readline()
            out(K.set_key(a.name, value) | ({"check": K.status(True, [a.name])[0].get("note")} if a.name in K.KEYS else {}))
        else:
            out({"env_file": str(K.ENV), "gitignored": K.is_gitignored(), "keys": K.status(a.check, a.only)})
    elif a.cmd == "selftest":
        import subprocess as sp
        from .project import ROOT
        r = sp.call(["uv", "run", "--extra", "dev", "pytest", "-q"], cwd=str(ROOT))
        sys.exit(r)
    elif a.cmd == "memory":
        from .project import init_memory, memory_dir
        out(init_memory() if a.init else {"dir": str(memory_dir()),
                                          "files": sorted(str(f.relative_to(memory_dir())) for f in memory_dir().rglob("*.md"))
                                          if memory_dir().exists() else []})
    elif a.cmd == "doctor":
        from .doctor import doctor
        ok = doctor()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
