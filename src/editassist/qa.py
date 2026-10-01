"""qa: automatic checks before handing an edit to the user."""
from __future__ import annotations

import re

from . import timeline as T
from .ingest import media_by_id
from .media import run
from .project import Project, read_json
from .render import PRESETS
from .transcribe import words


def check(project: Project, render_path: str | None = None, preset: str = "youtube") -> dict:
    tl = T.load(project)
    issues: list[dict] = []
    add = lambda sev, msg: issues.append({"severity": sev, "issue": msg})
    for p in T.validate(project, tl):
        add("error", p)
    for a, b in T.gaps(tl):
        add("warn", f"V1 gap (black) {a:.2f}-{b:.2f}s")
    fps = tl["fps"]
    for tr in tl["tracks"]:
        for c in tr["clips"]:
            if T.dur(c) < 3 / fps:
                add("warn", f"{tr['name']} flash frame: {T.dur(c)*fps:.0f}f clip at {c['start']:.2f}s")
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
    caps = (read_json(project.path("work", "captions.json"), {}) or {}).get("lines", [])
    for l in caps:
        text = " ".join(w["word"] for w in l["words"])
        if l["end"] - l["start"] < 0.3:
            add("info", f"caption on screen < 0.3s at {l['start']:.2f}s: {text!r}")
        if len(text) > 42:
            add("info", f"caption longer than 42 chars at {l['start']:.2f}s")
        if l["end"] > T.length(tl) + 0.05:
            add("warn", f"caption past end of timeline at {l['start']:.2f}s")
    measured = {}
    if render_path:
        src = str(project.abs(render_path))
        res = run(["ffmpeg", "-v", "info", "-i", src, "-vf", "blackdetect=d=0.25:pix_th=0.08",
                   "-af", "ebur128=peak=true", "-f", "null", "-"])
        for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", res.stderr):
            add("warn", f"black frames in render {float(a):.2f}-{float(b):.2f}s")
        i = re.findall(r"I:\s+(-?[\d.]+) LUFS", res.stderr)
        tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", res.stderr)
        if i:
            measured["lufs"] = float(i[-1])
            target = PRESETS.get(preset, PRESETS["youtube"])[0]
            if abs(measured["lufs"] - target) > 1.5:
                add("warn", f"loudness {measured['lufs']} LUFS, target for {preset} is {target}")
        if tp:
            measured["true_peak"] = float(tp[-1])
            if measured["true_peak"] > -0.5:
                add("warn", f"true peak {measured['true_peak']} dBFS (clipping risk)")
    return {"ok": not any(x["severity"] == "error" for x in issues), "issues": issues, "measured": measured,
            "length": round(T.length(tl), 2)}
