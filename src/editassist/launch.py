"""launch: product launch films, UI-first motion graphics in Remotion (product-launch skill).

projects/<name>/launch/     Remotion project made from templates/launch (beats.json = storyboard)
projects/<name>/work/launch/  stills, contact sheets, reference study, audits
projects/<name>/output/     final renders (+ format variants)

The agent directs; these commands give it eyes (stills, sheets), rules it can measure (audit) and
the audio pipeline (composed music, voice-over, effects kit), then render + verify the real file.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from .media import probe, run
from .project import ROOT, Project, read_json, write_json

TEMPLATE = ROOT / "templates" / "launch"
LUFS, TRUE_PEAK = -16.0, -1.5
SFX_PROMPTS = {
    "pop": "soft bubbly UI pop, short, clean, no reverb",
    "whoosh": "fast airy whoosh transition, modern UI motion graphics",
    "glitch": "very short digital glitch zap, crisp",
    "click": "tactile mouse click, soft, clean UI",
    "key": "single soft laptop key tap",
    "blip": "tiny friendly UI blip, high pitched, short",
    "chime": "bright success chime, two notes, short, pleasant",
    "swoosh": "soft swoosh of a card sliding in",
    "hit": "punchy deep cinematic hit, tight, no tail",
}


def ldir(project: Project) -> Path:
    d = project.path("launch")
    if not (d / "src" / "beats.json").exists():
        raise SystemExit(f"no launch film in {project.name}: run `ea launch new {project.name}`")
    return d


def _npx() -> str:
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx not found: install Node.js 20+")
    return npx


def _film(project: Project) -> dict:
    return read_json(ldir(project) / "src" / "film.json")


def _beats(project: Project) -> list[dict]:
    return read_json(ldir(project) / "src" / "beats.json")["beats"]


def _picture_frames(beats: list[dict]) -> int:
    return max((b["from"] + b["duration"] for b in beats), default=0)


# --- setup ---------------------------------------------------------------------------------------

def new(project: Project, seconds: float = 50, fps: int = 30, size: str = "1920x1080", font_black: str | None = None,
        font_bold: str | None = None, font_name: str | None = None, install: bool = True) -> dict:
    d = project.path("launch")
    if (d / "src" / "beats.json").exists():
        raise SystemExit(f"{d} already exists (delete it to start over)")
    shutil.copytree(TEMPLATE, d, ignore=shutil.ignore_patterns("node_modules", "out", "*.log"))
    fonts = d / "public" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(font_black).expanduser() if font_black else ROOT / "assets" / "fonts" / "Montserrat-Black.ttf", fonts / "Brand-Black.ttf")
    shutil.copy2(Path(font_bold or font_black).expanduser() if (font_bold or font_black) else ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf",
                 fonts / "Brand-Bold.ttf")
    w, h = (int(x) for x in size.lower().split("x"))
    film = {"name": project.name, "width": w, "height": h, "fps": fps, "playback": 1,
            "font": font_name or ("Brand" if font_black else "Montserrat")}
    write_json(d / "src" / "film.json", film)
    res = {"launch": project.rel(d), "studio": f"cd {project.rel(d)} && npm run studio", "target_seconds": seconds,
           "target_frames": int(seconds * fps)}
    if install:
        npm = shutil.which("npm")
        if not npm:
            raise SystemExit("npm not found: install Node.js 20+")
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=d, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("npm install failed:\n" + r.stderr[-1500:])
        res["installed"] = True
    return res


# --- eyes ----------------------------------------------------------------------------------------

def _label_sheet(items: list[tuple[str, Path]], dst: Path, cols: int = 5, thumb_w: int = 384) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"), 16)
    tiles = []
    for label, f in items:
        im = Image.open(f).convert("RGB")
        im = im.resize((thumb_w, int(im.height * thumb_w / im.width)))
        dr = ImageDraw.Draw(im)
        tw = dr.textlength(label, font=font) + 12
        dr.rectangle([0, 0, tw, 22], fill=(0, 0, 0))
        dr.text((6, 2), label, font=font, fill=(255, 255, 255))
        tiles.append(im)
    th = max(t.height for t in tiles)
    sheet = Image.new("RGB", (cols * thumb_w, -(-len(tiles) // cols) * th), (40, 40, 40))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * thumb_w, (i // cols) * th))
    dst.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst, quality=85)
    return dst


def _beat_at(beats: list[dict], picture_frame: float) -> str:
    for b in beats:
        if b["from"] <= picture_frame < b["from"] + b["duration"]:
            return b["id"]
    return "-"


def stills(project: Project, comp: str = "Film", every: int = 0, frames: str = "", frame_range: str = "",
           scale: float = 0.5, size: str | None = None, per_sheet: int = 20, tag: str | None = None) -> dict:
    """Render frames (OUTPUT frames of the composition) and tile them into labelled contact sheets."""
    d = ldir(project)
    film, beats = _film(project), _beats(project)
    out = project.path("work", "launch", "stills", tag or time.strftime("%H%M%S"))
    cmd = ["node", "scripts/stills.mjs", "--comp", comp, "--out", str(out), "--scale", str(scale)]
    if frames:
        cmd += ["--frames", frames]
    else:
        cmd += ["--every", str(every or 6)] + (["--range", frame_range] if frame_range else [])
    if size:
        w, h = (int(x) for x in size.lower().split("x"))
        cmd += ["--props", json.dumps({"width": w, "height": h})]
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("stills failed:\n" + (r.stderr or r.stdout)[-2000:])
    idx = read_json(out / "index.json")
    pb = film.get("playback") or 1
    items = []
    for fr in idx["frames"]:
        t = fr["frame"] / idx["fps"]
        beat = _beat_at(beats, fr["frame"] * pb) if comp == "Film" else comp
        items.append((f"f{fr['frame']} {t:.2f}s {beat}", out / fr["file"]))
    sheets = []
    for k in range(0, len(items), per_sheet):
        sheets.append(project.rel(_label_sheet(items[k:k + per_sheet], out / f"sheet_{k // per_sheet:02d}.jpg")))
    return {"frames": len(items), "look_at": sheets}


def reference(project: Project, video: str, fps: float = 2.0) -> dict:
    """Study a reference film: brightness check (screen recordings are often dimmed), contact
    sheets at `fps`, and 30 fps strips around every cut. The agent then writes the breakdown."""
    import numpy as np

    src = Path(video).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"reference not found: {src}")
    info = probe(src)
    out = project.path("work", "launch", "reference")
    if out.exists():
        shutil.rmtree(out)
    (out / "frames").mkdir(parents=True)
    # brightness: the brightest areas of a UI film should be near white
    res = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vf", "fps=1,scale=160:-2", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True)
    g = np.frombuffer(res.stdout, np.uint8)
    white = float(np.percentile(g, 99.5)) / 255 if len(g) else 1.0
    black = float(np.percentile(g, 0.5)) / 255 if len(g) else 0.0
    fix = ""
    if white < 0.85 or black > 0.12:
        lo, hi = round(black, 3), round(max(white, black + 0.2), 3)
        fix = f",colorlevels=rimin={lo}:gimin={lo}:bimin={lo}:rimax={hi}:gimax={hi}:bimax={hi}"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", f"fps={fps},scale=640:-2{fix}", "-q:v", "4",
         str(out / "frames" / "r%05d.jpg")])
    files = sorted((out / "frames").glob("r*.jpg"))
    items = [(f"{i / fps:.1f}s", f) for i, f in enumerate(files)]
    sheets = [project.rel(_label_sheet(items[k:k + 20], out / f"sheet_{k // 20:02d}.jpg")) for k in range(0, len(items), 20)]
    # cuts → 30 fps strips (8 frames before, 8 after) to study transitions frame by frame
    from .scenes import cut_times

    cuts = cut_times(str(src), 0.3)
    strips = []
    for n, c in enumerate(cuts[:24]):
        sd = out / f"cut_{n:02d}"
        sd.mkdir()
        a = max(0.0, c - 8 / 30)
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", str(src), "-frames:v", "16",
             "-vf", f"fps=30,scale=480:-2{fix}", "-q:v", "4", str(sd / "s%02d.jpg")])
        fs = sorted(sd.glob("s*.jpg"))
        strips.append(project.rel(_label_sheet([(f"{a + i / 30:.2f}s", f) for i, f in enumerate(fs)], out / f"cut_{n:02d}.jpg", cols=8, thumb_w=320)))
    report = {"duration": info.get("duration"), "size": f"{info.get('width')}x{info.get('height')}", "fps": info.get("fps"),
              "white_level": round(white, 3), "black_level": round(black, 3),
              "brightness_corrected": bool(fix), "cuts": [round(c, 2) for c in cuts], "sheets": sheets, "cut_strips": strips,
              "next": "look at every sheet and strip, then write work/launch/reference/breakdown.md (pacing, type animation, "
                      "transitions, UI techniques, colour and layout rules)"}
    write_json(out / "report.json", report)
    return report


# --- rules the agent can measure ----------------------------------------------------------------

HEX = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}(?:[0-9a-fA-F]{2})?\b")
RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


def _norm_hex(h: str) -> str:
    h = h.lstrip("#").lower()
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    return "#" + h[:6]


def audit(project: Project, motion: bool = False, scale: float = 0.2) -> dict:
    d = ldir(project)
    film, beats = _film(project), _beats(project)
    fps = film["fps"]
    palette = read_json(d / "src" / "brand" / "palette.json")["colors"]
    allowed = {_norm_hex(v) for v in palette.values()}
    issues: list[dict] = []
    add = lambda sev, area, msg: issues.append({"severity": sev, "area": area, "issue": msg})

    # storyboard
    total = _picture_frames(beats)
    t = 0
    demo = 0
    for b in beats:
        if b["from"] != t:
            add("error", "storyboard", f"{b['id']}: starts at {b['from']}, previous beat ends at {t} (gap/overlap)")
        t = b["from"] + b["duration"]
        if b.get("bg") not in palette:
            add("error", "storyboard", f"{b['id']}: bg {b.get('bg')!r} is not a palette colour")
        if b["kind"] == "demo":
            demo += b["duration"]
            if not b.get("title"):
                add("warn", "text", f"{b['id']}: demo without a title; every frame needs readable text (pinned caption)")
        for li, line in enumerate(b.get("title") or []):
            text = "".join(s["t"] for s in line)
            letters = [c for c in text if c.isalpha()]
            if len(letters) > 3 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
                add("warn", "copy", f"{b['id']} line {li + 1}: {text!r} looks ALL CAPS; use sentence case")
            n_acc = sum(1 for s in line if s.get("accent"))
            if n_acc > 1:
                add("warn", "copy", f"{b['id']} line {li + 1}: {n_acc} accent spans; one accent word per line")
        if b["kind"] == "title" and b.get("title"):
            words = sum(len(s["t"].split()) for line in b["title"] for s in line)
            settled = b["duration"] - (words * 3 + 15) - (beats[beats.index(b) + 1].get("transition", {}).get("duration", 12)
                                                          if beats.index(b) + 1 < len(beats) else 0)
            if settled < fps:
                add("warn", "pace", f"{b['id']}: title settles only {settled / fps:.2f}s before leaving (needs ~1s); lengthen the beat")
        if b.get("scene"):
            reg = (d / "src" / "scenes" / "index.ts").read_text(encoding="utf-8")
            if not re.search(rf"\b{re.escape(b['scene'])}\b", reg):
                add("error", "storyboard", f"{b['id']}: scene {b['scene']!r} is not registered in src/scenes/index.ts")
    if total and demo / total < 0.5:
        add("warn", "story", f"UI demos are {demo / total:.0%} of the film; aim for ~75% (at least half)")

    # palette discipline
    for f in sorted((d / "src").rglob("*.ts*")):
        txt = f.read_text(encoding="utf-8")
        for m in HEX.finditer(txt):
            if _norm_hex(m.group(0)) not in allowed:
                add("warn", "colour", f"{f.relative_to(d).as_posix()}: {m.group(0)} is not in the palette")
        for m in RGB.finditer(txt):
            hx = "#%02x%02x%02x" % tuple(int(x) for x in m.groups())
            if hx not in allowed:
                add("warn", "colour", f"{f.relative_to(d).as_posix()}: rgb({','.join(m.groups())}) is not a palette colour")

    # glyphs: every character on screen must exist in the brand font (₦, €, curly quotes...)
    try:
        from fontTools.ttLib import TTFont

        chars = set()
        for b in beats:
            for line in b.get("title") or []:
                for s in line:
                    chars |= set(s["t"])
        for f in (d / "src" / "scenes").glob("*.tsx"):
            for lit in re.findall(r'"([^"\n]{1,120})"|>([^<>{}\n]{1,120})<', f.read_text(encoding="utf-8")):
                chars |= set(lit[0] or lit[1])
        chars = {c for c in chars if not c.isspace()}
        for fnt in sorted((d / "public" / "fonts").glob("Brand-*.ttf")):
            cmap = TTFont(str(fnt))["cmap"].getBestCmap()
            missing = sorted(c for c in chars if ord(c) not in cmap)
            if missing:
                add("error", "font", f"{fnt.name} has no glyph for {''.join(missing)!r}: draw it or change the copy")
    except ImportError:
        add("info", "font", "fontTools not installed; glyph check skipped")

    # audio files referenced
    audio = read_json(d / "src" / "audio.json") or {}
    for entry in ([audio.get("music")] if audio.get("music") else []) + list(audio.get("vo") or []):
        if not (d / "public" / entry["file"]).exists():
            add("error", "audio", f"missing public/{entry['file']}")
    for kind, path in (audio.get("sfx") or {}).items():
        if not (d / "public" / path).exists():
            add("error", "audio", f"sfx {kind}: missing public/{path}")
    if not audio.get("sfx"):
        add("info", "audio", "no sound effects yet (`ea launch sfx-kit`)")

    measured = {}
    if motion:
        measured = _motion_audit(project, beats, film, scale, add)
    return {"ok": not any(i["severity"] == "error" for i in issues), "issues": issues, "measured": measured,
            "film_seconds": round(total / fps / (film.get("playback") or 1), 2), "demo_share": round(demo / total, 2) if total else 0}


def _motion_audit(project: Project, beats: list[dict], film: dict, scale: float, add) -> dict:
    """Density rule: inside UI demos something must move in every 8-frame window. Renders every 2nd
    picture frame of each demo at low res and measures change between samples."""
    import numpy as np
    from PIL import Image

    pb = film.get("playback") or 1
    demos = [b for b in beats if b["kind"] == "demo"]
    if not demos:
        return {}
    frames = sorted({int(round(f / pb)) for b in demos for f in range(b["from"], b["from"] + b["duration"], 2)})
    res = stills(project, "Film", frames=",".join(map(str, frames)), scale=scale, tag="motion")
    out = project.path("work", "launch", "stills", "motion")
    idx = read_json(out / "index.json")
    imgs = {fr["frame"]: np.asarray(Image.open(out / fr["file"]).convert("L"), dtype=np.float32) for fr in idx["frames"]}
    report = {}
    for b in demos:
        fs = [f for f in frames if b["from"] <= f * pb < b["from"] + b["duration"]]
        diffs = [(fs[i], float(np.abs(imgs[fs[i]] - imgs[fs[i - 1]]).mean())) for i in range(1, len(fs))]
        trans = (b.get("transition") or {}).get("duration", 12)
        still_run, longest, frozen = 0, 0, []
        for f, dv in diffs:
            if dv < 0.25:  # mean abs change < 0.25/255: nothing meaningful moved
                still_run += 2
                longest = max(longest, still_run)
                if still_run == 8:
                    frozen.append(f)
            else:
                still_run = 0
            if dv > 40 and f * pb - b["from"] > trans:
                add("warn", "motion", f"{b['id']}: jump between frames around f{f} (Δ{dv:.0f}); check for a pop or glitch")
        if frozen:
            add("warn", "motion", f"{b['id']}: nothing moves for 8+ frames at {frozen[:6]} (density rule)")
        report[b["id"]] = {"longest_still_frames": longest, "frozen_windows": len(frozen),
                           "mean_change": round(float(np.mean([d for _, d in diffs])), 2) if diffs else 0}
    report["sheets"] = res["look_at"]
    return report


# --- sound ---------------------------------------------------------------------------------------

def measure_lufs(src: Path, pre: str = "") -> float:
    r = run(["ffmpeg", "-v", "info", "-i", str(src), "-vn", "-af", f"{pre + ',' if pre else ''}ebur128", "-f", "null", "-"])
    vals = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(vals[-1]) if vals else -70.0


def normalize(src: Path, dst: Path, lufs: float = LUFS, pre: str = "", video_copy: bool = False) -> Path:
    """Gain to the integrated target + true-peak limiter, measured and corrected once.
    Deterministic, and it hits the target on peaky material where linear loudnorm can't."""
    limit = 10 ** (TRUE_PEAK / 20)
    dst.parent.mkdir(parents=True, exist_ok=True)
    gain = lufs - measure_lufs(src, pre)
    for _ in range(5):  # the limiter eats some gain on peaky material: converge in a few passes
        af = f"{pre + ',' if pre else ''}volume={gain:.2f}dB,alimiter=limit={limit:.4f}:attack=1:release=50:level=false,aresample=48000"
        codec = (["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"] if video_copy
                 else ["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", af, *codec, str(dst)])
        off = lufs - measure_lufs(dst)
        if abs(off) < 0.5:
            break
        gain += off * 1.6
    return dst


def _loudnorm(src: Path, dst: Path, lufs: float = LUFS, trim: bool = False) -> Path:
    pre = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
           "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse") if trim else ""
    return normalize(src, dst, lufs, pre)


def _audio_json(project: Project) -> tuple[Path, dict]:
    p = ldir(project) / "src" / "audio.json"
    return p, read_json(p) or {"music": None, "vo": [], "sfx": {}}


def sfx_kit(project: Project, kinds: list[str] | None = None) -> dict:
    """Standard UI sound kit via ElevenLabs, cached in .cache/sfx so later films reuse it for free."""
    from .generate import EL, _post_audio

    kinds = kinds or list(SFX_PROMPTS)
    cache = ROOT / ".cache" / "sfx"
    p, audio = _audio_json(project)
    pub = ldir(project) / "public" / "sfx"
    made, reused = [], []
    for k in kinds:
        if k not in SFX_PROMPTS:
            raise SystemExit(f"unknown sfx kind {k!r}; one of {list(SFX_PROMPTS)}")
        c = cache / f"{k}.mp3"
        if not c.exists():
            raw = cache / f"{k}_raw.mp3"
            _post_audio(f"{EL}/sound-generation", {"text": SFX_PROMPTS[k], "duration_seconds": 1.0 if k != "chime" else 1.5}, raw)
            _loudnorm(raw, c, lufs=-20)
            raw.unlink(missing_ok=True)
            made.append(k)
        else:
            reused.append(k)
        shutil.copy2(c, pub / f"{k}.mp3")
        audio.setdefault("sfx", {})[k] = f"sfx/{k}.mp3"
    write_json(p, audio)
    return {"generated": made, "reused_from_cache": reused, "sfx": audio["sfx"]}


def vo(project: Project, lines_file: str, voice: str | None = None, stability: float = 0.3, similarity: float = 0.8,
       style: float = 0.5, speed: float = 1.05, model: str = "eleven_multilingual_v2") -> dict:
    """One voice line per beat: [{"beat": id, "text": "...", "offset": 6}]. Each line explains the
    scene (doesn't repeat the title); placed `offset` picture frames after its beat starts."""
    import os

    import requests

    from .generate import EL, _key

    voice = voice or os.environ.get("ELEVENLABS_VOICE_ID")
    if not voice:
        raise SystemExit("no voice: pass --voice or set ELEVENLABS_VOICE_ID (`ea voices` lists them)")
    lines = read_json(Path(lines_file)) if Path(lines_file).is_file() else read_json(project.path(lines_file))
    beats = {b["id"]: b for b in _beats(project)}
    p, audio = _audio_json(project)
    pub = ldir(project) / "public" / "vo"
    placed = []
    for ln in lines:
        b = beats.get(ln["beat"])
        if not b:
            raise SystemExit(f"unknown beat {ln['beat']!r}")
        raw = pub / f"{ln['beat']}_raw.mp3"
        r = requests.post(f"{EL}/text-to-speech/{voice}", headers={"xi-api-key": _key("ELEVENLABS_API_KEY", "elevenlabs.io"), "accept": "audio/mpeg"},
                          json={"text": ln["text"], "model_id": model, "voice_settings": {
                              "stability": stability, "similarity_boost": similarity, "style": style, "speed": speed, "use_speaker_boost": True}},
                          timeout=300)
        if r.status_code != 200:
            raise SystemExit(f"ElevenLabs {r.status_code}: {r.text[:300]}")
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(r.content)
        dst = _loudnorm(raw, pub / f"{ln['beat']}.mp3", trim=True)
        raw.unlink(missing_ok=True)
        dur = probe(dst)["duration"]
        placed.append({"file": f"vo/{dst.name}", "at": b["from"] + int(ln.get("offset", 6)), "dur": round(dur, 3), "beat": b["id"],
                       "text": ln["text"]})
    audio["vo"] = placed
    write_json(p, audio)
    film = _film(project)
    warn = [f"{v['beat']}: line is {v['dur']:.1f}s but the beat shows {beats[v['beat']]['duration'] / film['fps'] / (film.get('playback') or 1):.1f}s"
            for v in placed if v["dur"] > beats[v["beat"]]["duration"] / film["fps"] / (film.get("playback") or 1)]
    return {"lines": len(placed), "vo": placed, "warnings": warn}


def music(project: Project, plan_file: str, gain_db: float = -6, duck_db: float = -9) -> dict:
    """Music composed to the cut. plan: {"styles": [...], "avoid": [...], "sections": [{"name": "intro hit",
    "until": "<beat id>" | "seconds": 3.0, "styles": [...]}]}. Sections are timed on the OUTPUT film
    (after playback slow-down); each must be >= 3 s (ElevenLabs limit)."""
    from .generate import EL, _post_audio

    plan = read_json(Path(plan_file)) if Path(plan_file).is_file() else read_json(project.path(plan_file))
    film, beats = _film(project), _beats(project)
    pb, fps = film.get("playback") or 1, film["fps"]
    ends = {b["id"]: (b["from"] + b["duration"]) / pb / fps for b in beats}
    total = _picture_frames(beats) / pb / fps
    sections, t = [], 0.0
    for s in plan["sections"]:
        end = ends[s["until"]] if "until" in s else t + float(s["seconds"])
        dur = end - t
        if dur < 3:
            raise SystemExit(f"section {s['name']!r} is {dur:.2f}s; ElevenLabs needs >= 3 s per section (merge it)")
        sections.append({"section_name": s["name"][:100], "positive_local_styles": s.get("styles", []),
                         "negative_local_styles": s.get("avoid", []), "duration_ms": int(round(dur * 1000)), "lines": []})
        t = end
    if abs(t - total) > 0.5:
        raise SystemExit(f"sections cover {t:.2f}s but the film is {total:.2f}s; end the last section on the last beat")
    body = {"composition_plan": {"positive_global_styles": plan.get("styles", []),
                                 "negative_global_styles": list(dict.fromkeys(plan.get("avoid", []) + ["vocals", "singing", "lyrics"])),
                                 "sections": sections}}
    pub = ldir(project) / "public" / "audio"
    raw = pub / "music_raw.mp3"
    _post_audio(f"{EL}/music", body, raw)
    dst = _loudnorm(raw, pub / "music.mp3")
    raw.unlink(missing_ok=True)
    return _place_music(project, dst, gain_db, duck_db) | {"sections": [(s["section_name"], s["duration_ms"]) for s in sections]}


def _place_music(project: Project, file: Path, gain_db: float, duck_db: float, source: str | None = None) -> dict:
    from .beats import detect_file

    film = _film(project)
    pb, fps = film.get("playback") or 1, film["fps"]
    b = detect_file(str(file))
    hits = {"bpm": b["bpm"], "beats": [round(t * fps * pb) for t in b["beats"]], "downbeats": [round(t * fps * pb) for t in b["downbeats"]],
            "_comment": "PICTURE frames (film.json fps, before playback): land big moves on these"}
    write_json(ldir(project) / "src" / "music-hits.json", hits)
    p, audio = _audio_json(project)
    audio["music"] = {"file": f"audio/{file.name}", "gainDb": gain_db, "duckDb": duck_db,
                      **({"source": source} if source else {})}
    write_json(p, audio)
    return {"music": audio["music"]["file"], "bpm": b["bpm"], "beats": len(hits["beats"]), "downbeats": len(hits["downbeats"]),
            "duration": round(probe(file)["duration"], 2)}


def stretch_music(project: Project, seconds: float, intro_bars: int = 1, outro_bars: int = 2) -> dict:
    """Free re-edit instead of re-composing: keep the intro, repeat the groove on bar lines until the
    target length, keep the original ending. Splices land on downbeats with 15 ms crossfades."""
    from .beats import detect_file

    d = ldir(project)
    _, audio = _audio_json(project)
    if not audio.get("music"):
        raise SystemExit("no music yet")
    # always splice the ORIGINAL bed, so repeated stretches never compound
    src = d / "public" / audio["music"].get("source", audio["music"]["file"])
    b = detect_file(str(src))
    db = b["downbeats"]
    if len(db) < intro_bars + outro_bars + 3:
        raise SystemExit("not enough bars detected to splice safely")
    dur = probe(src)["duration"]
    g0, g1 = db[intro_bars], db[-outro_bars - 1]
    bar = (db[-1] - db[0]) / max(1, len(db) - 1)
    glen = g1 - g0
    # groove time needed between the intro and the outro, rounded to whole bars
    need = max(bar, round((seconds - g0 - (dur - g1)) / bar) * bar)
    parts = [(0.0, g0)]
    while need > 1e-3:
        take = min(glen, need)
        parts.append((g0, g0 + take))
        need -= take
    parts.append((g1, dur))
    reps = round((sum(e - a for a, e in parts[1:-1])) / bar)
    fc, labels = [], []
    for i, (a, e) in enumerate(parts):
        fc.append(f"[0:a]atrim={a:.4f}:{e:.4f},asetpts=PTS-STARTPTS[p{i}]")
        labels.append(f"[p{i}]")
    chain = labels[0]
    for i in range(1, len(labels)):
        fc.append(f"{chain}{labels[i]}acrossfade=d=0.015:c1=tri:c2=tri[x{i}]")
        chain = f"[x{i}]"
    dst = src.with_name(f"{src.stem}_{int(round(seconds))}s.mp3")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", ";".join(fc), "-map", chain, "-c:a", "libmp3lame", "-q:a", "2", str(dst)])
    res = _place_music(project, dst, audio["music"].get("gainDb", -6), audio["music"].get("duckDb", -9),
                       source=src.relative_to(d / "public").as_posix())
    return res | {"groove_bars": reps, "bar_seconds": round(bar, 3), "target": seconds}


# --- delivery ------------------------------------------------------------------------------------

def render(project: Project, comp: str = "Film", size: str | None = None, out: str | None = None) -> dict:
    d = ldir(project)
    film = _film(project)
    name = film.get("name", project.name)
    suffix = f"_{size}" if size else ""
    raw = project.path("work", "launch", f"raw{suffix}.mp4")
    raw.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_npx(), "remotion", "render", "src/index.ts", comp, str(raw), "--codec=h264", "--crf=16", "--log=error"]
    if size:
        w, h = (int(x) for x in size.lower().split("x"))
        props = project.path("work", "launch", f"props{suffix}.json")
        write_json(props, {"width": w, "height": h})
        cmd.append(f"--props={props}")
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("remotion render failed:\n" + (r.stderr or r.stdout)[-2000:])
    dst = project.abs(out) if out else project.path("output", f"{name}{suffix}.mp4")
    dst.parent.mkdir(parents=True, exist_ok=True)
    has_audio = probe(raw).get("has_audio")
    if has_audio:  # normalise without re-encoding the picture
        normalize(raw, dst, video_copy=True)
    else:
        shutil.copy2(raw, dst)
    return {"rendered": project.rel(dst)} | verify(project, project.rel(dst))


def verify(project: Project, file: str) -> dict:
    """Check the real file, not the preview: frames, size, a sheet every 3 s, loudness."""
    src = project.abs(file)
    info = probe(src)
    cnt = run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets",
               "-of", "csv=p=0", str(src)]).stdout.strip().strip(",")
    out = project.path("work", "launch", "verify")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "fps=1/3,scale=480:-2", "-q:v", "4", str(out / "v%04d.jpg")])
    fs = sorted(out.glob("v*.jpg"))
    sheet = _label_sheet([(f"{i * 3}s", f) for i, f in enumerate(fs)], out / "sheet.jpg", cols=min(6, len(fs)), thumb_w=320) if fs else None
    issues, loud = [], {}
    if info.get("has_audio"):
        r = run(["ffmpeg", "-v", "info", "-i", str(src), "-af", "ebur128=peak=true", "-f", "null", "-"])
        i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
        tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
        loud = {"lufs": float(i[-1]) if i else None, "true_peak": float(tp[-1]) if tp else None}
        if loud["lufs"] is not None and abs(loud["lufs"] - LUFS) > 1:
            issues.append(f"loudness {loud['lufs']} LUFS, target {LUFS}")
        if loud["true_peak"] is not None and loud["true_peak"] > -1.0:
            issues.append(f"true peak {loud['true_peak']} dBTP, must stay below -1")
    else:
        issues.append("no audio track")
    return {"size": f"{info.get('width')}x{info.get('height')}", "fps": info.get("fps"), "frames": int(cnt) if cnt.isdigit() else cnt,
            "seconds": round(info["duration"], 2), **loud, "sheet": project.rel(sheet) if sheet else None, "issues": issues}
