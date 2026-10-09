"""qa: automatic checks before handing an edit to the user."""
from __future__ import annotations

import re

from . import timeline as T
from .ingest import media_by_id
from .media import run
from .project import Project, read_json
from .render import PRESETS
from .transcribe import words


def check(project: Project, render_path: str | None = None, preset: str | None = None) -> dict:
    tl = T.load(project)
    issues: list[dict] = []
    add = lambda sev, msg: issues.append({"severity": sev, "issue": msg})
    for p in T.validate(project, tl):
        add("error", p)
    for a, b in T.gaps(tl):
        add("warn", f"V1 gap (black) {a:.2f}-{b:.2f}s")
    fps = tl["fps"]
    v1 = T.track(tl, "V1")["clips"]
    pic_end = max((T.end(c) for c in v1), default=0.0)
    for tr in tl["tracks"]:  # an overlay (title, end card) past the last picture ends on black
        if tr["kind"] == "video" and tr["name"] != "V1" and v1:
            for c in tr["clips"]:
                if T.end(c) > pic_end + 0.5 / fps:
                    add("warn", f"{tr['name']} {c.get('note') or 'clip'} ends at {T.end(c):.2f}s, "
                                f"{T.end(c) - pic_end:.2f}s after the last V1 picture: black under it")
    for tr in tl["tracks"]:
        if tr["kind"] == "video":  # sub-frame gaps/overlaps round to 1-frame holes in an NLE
            cs = sorted(tr["clips"], key=lambda c: c["start"])
            for a, b in zip(cs, cs[1:]):
                d = b["start"] - T.end(a)
                if abs(d) < 1.0 / fps and round(b["start"] * fps) != round(T.end(a) * fps):
                    add("warn", f"{tr['name']} cut at {b['start']:.3f}s is off by {d * fps:+.2f} frame: "
                                f"snap clip edges to the frame grid (NLE shows a 1-frame hole)")
        for c in tr["clips"]:
            if T.dur(c) < 3 / fps:
                add("warn", f"{tr['name']} flash frame: {T.dur(c)*fps:.0f}f clip at {c['start']:.2f}s")
    # dialogue under a picture of the SAME file must be in sync (lips): a builder that cut a pause out of
    # the sound but kept the picture running put Paulo's "eu sou chorão" 2.3 s late (2026-10-08)
    vids = [c for tr in tl["tracks"] if tr["kind"] == "video" for c in tr["clips"]]
    for a in T.track(tl, "A1")["clips"]:
        for v in vids:
            if v["media"] != a["media"] or v.get("speed", 1.0) != 1.0:
                continue
            lo, hi = max(a["start"], v["start"]), min(T.end(a), T.end(v))
            if hi - lo < 0.2:
                continue
            off = (v["in"] - v["start"]) - (a["in"] - a["start"])
            if abs(off) > 1.0 / fps:
                add("error", f"picture and sound out of sync by {off:+.2f}s at {lo:.2f}-{hi:.2f}s "
                             f"({project.abs(a['media']).name}): cut the picture where the sound jumps")
    # cuts that land inside a word sound like glitches
    by_path = {m["path"]: sid for sid, m in media_by_id(project).items()}
    a1 = sorted(T.track(tl, "A1")["clips"], key=lambda c: c["start"])
    for i, c in enumerate(a1):
        ws = words(project, by_path.get(c["media"], ""))
        prev = a1[i - 1] if i else None
        nxt = a1[i + 1] if i + 1 < len(a1) else None
        # a split where the source simply continues is not an audible cut
        cont_in = prev and prev["media"] == c["media"] and abs(prev["out"] - c["in"]) < 0.02 and abs(T.end(prev) - c["start"]) < 0.02
        cont_out = nxt and nxt["media"] == c["media"] and abs(c["out"] - nxt["in"]) < 0.02 and abs(T.end(c) - nxt["start"]) < 0.02
        for edge, t in (("in", c["in"]), ("out", c["out"])):
            if (edge == "in" and cont_in) or (edge == "out" and cont_out):
                continue
            w = next((w for w in ws if w["start"] + 0.04 < t < w["end"] - 0.04), None)
            if w:
                add("warn", f"A1 cut {edge} at timeline {c['start'] if edge == 'in' else T.end(c):.2f}s "
                            f"splits the word {w['word']!r} ({w['start']:.2f}-{w['end']:.2f} in source)")
    caps = (T.captions(project, tl) or {}).get("lines", [])
    for l in caps:
        text = " ".join(w["word"] for w in l["words"])
        if l["end"] - l["start"] < 0.3:
            add("info", f"caption on screen < 0.3s at {l['start']:.2f}s: {text!r}")
        if len(text) > 42:
            add("info", f"caption longer than 42 chars at {l['start']:.2f}s")
        if l["end"] > T.length(tl) + 0.05:
            add("warn", f"caption past end of timeline at {l['start']:.2f}s")
    a_clips = [(tr, c) for tr in tl["tracks"] if tr["kind"] == "audio" for c in tr["clips"]]
    if len({tr["name"] for tr, _ in a_clips}) > 1 and not any("lufs" in c for _, c in a_clips):
        add("warn", "audio gains are guesses, not measured: run `ea level` (music above the voice otherwise)")
    measured = {}
    if render_path:
        src = str(project.abs(render_path))
        res = run(["ffmpeg", "-v", "info", "-i", src, "-vf", "blackdetect=d=0:pix_th=0.08",
                   "-af", "ebur128=peak=true,silencedetect=n=-55dB:d=1.5", "-f", "null", "-"])
        if preset is None:  # a 540p preview is mixed to the preview target, a delivery to the platform's
            h = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height",
                     "-of", "csv=p=0", src]).stdout.strip()
            preview_h = PRESETS["preview"][2]
            preset = "preview" if h.isdigit() and int(h) <= preview_h else project.settings.get("platform") or "youtube"
        # fades to/from black at a clip's head/tail are intended, not flashes
        vclips = [c for tr in tl["tracks"] if tr["kind"] == "video" for c in tr["clips"]]
        faded = [c["start"] for c in vclips if (c.get("transition_in") or {}).get("type") in ("fade", "dip")] + \
                [T.end(c) for c in vclips if (c.get("transition_out") or {}).get("type") in ("fade", "dip")]
        cuts = [x for c in vclips for x in (c["start"], T.end(c))
                if not any(abs(x - f) < 0.05 for f in faded)]
        for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", res.stderr):
            a, b = float(a), float(b)
            if b - a >= 0.25:
                add("warn", f"black frames in render {a:.2f}-{b:.2f}s")
            elif any(abs(a - c) < 0.1 or abs(b - c) < 0.1 for c in cuts):  # one or two frames at a cut
                add("error", f"black flash at the cut {a:.2f}s ({round((b - a) * tl['fps'])} frames)")
        # an audio stream shorter than the picture (or silent to the end) passes loudness checks unnoticed
        durs = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", src]).stdout
        sd = {k: float(v) for k, v in (l.split(",")[:2] for l in durs.split() if "," in l) if v not in ("N/A", "")}
        if "video" in sd and "audio" in sd and sd["video"] - sd["audio"] > 0.3:
            add("warn", f"audio ends {sd['video'] - sd['audio']:.2f}s before the picture ({sd['audio']:.2f}s of {sd['video']:.2f}s)")
        for a, d in re.findall(r"silence_start: (-?[\d.]+)[\s\S]*?silence_duration: ([\d.]+)", res.stderr):
            if float(d) >= 1.5:
                add("warn", f"render silent {float(a):.2f}-{float(a) + float(d):.2f}s")
        i = re.findall(r"I:\s+(-?[\d.]+) LUFS", res.stderr)
        tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", res.stderr)
        if i:
            measured["lufs"] = float(i[-1])
            target = PRESETS.get(preset or "youtube", PRESETS["youtube"])[0]
            if abs(measured["lufs"] - target) > 1.5:
                add("warn", f"loudness {measured['lufs']} LUFS, target for {preset} is {target}")
        if tp:
            measured["true_peak"] = float(tp[-1])
            if measured["true_peak"] > -0.5:
                add("warn", f"true peak {measured['true_peak']} dBFS (clipping risk)")
    return {"ok": not any(x["severity"] == "error" for x in issues), "issues": issues, "measured": measured,
            "length": round(T.length(tl), 2)}
