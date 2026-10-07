"""level: set every audio clip's gain from its MEASURED loudness, by role, instead of fixed dB guesses.

A fixed `gain_db: -12` on a mastered music bed (around -8 LUFS) under a raw lavalier (around -30 LUFS)
leaves the music louder than the voice; the final loudnorm then only moves the whole mix. Here each
clip's own segment is measured (EBU R128 integrated, gated, so pauses don't count) and its gain set so:

  dialogue  -16 LUFS   the voice: what the platform loudness target is built around
  bed       -30 LUFS   music under speech (`duck: true`), clearly below the voice even before ducking
  music     -16 LUFS   music with nobody talking over it (montage, intro)
  sfx       -22 LUFS   risers, hits, whooshes

Roles come from the clip (`role` field if set), else: `duck` -> bed, track name with "sfx" -> sfx,
track name with "music"/"montage" or a music media -> music, anything else -> dialogue.
Results are written to timeline.json (`gain_db`, `lufs`), so render, bake and every export carry them.
"""
from __future__ import annotations

import re

from . import timeline as T
from .media import run
from .project import Project, read_json

TARGETS = {"dialogue": -16.0, "bed": -30.0, "music": -16.0, "sfx": -22.0}
MAX_GAIN = 30.0


def role(tr: dict, c: dict, catalog: dict) -> str:
    if c.get("role") in TARGETS:
        return c["role"]
    if c.get("duck"):
        return "bed"
    name = tr["name"].lower()
    if "sfx" in name:
        return "sfx"
    m = catalog.get(c["media"]) or {}
    if "music" in name or "montage" in name or str(m.get("id", "")).startswith("music__"):
        return "music"
    return "dialogue"


def segment_lufs(project: Project, c: dict) -> float | None:
    """Integrated loudness of the clip's source segment, or None when it is silent / too short."""
    r = run(["ffmpeg", "-v", "info", "-ss", f"{c['in']:.3f}", "-t", f"{max(c['out'] - c['in'], 0.1):.3f}",
             "-i", str(project.abs(c["media"])), "-vn", "-af", "ebur128", "-f", "null", "-"], cwd=project.dir)
    vals = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    v = float(vals[-1]) if vals else -70.0
    return None if v <= -69 else v


def level(project: Project, targets: dict | None = None) -> dict:
    targets = {**TARGETS, **(targets or {})}
    tl = T.load(project)
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    report: dict = {"targets": targets, "clips": []}
    for tr in tl["tracks"]:
        if tr["kind"] != "audio":
            continue
        for c in tr["clips"]:
            m = catalog.get(c["media"]) or {}
            if m and not m.get("has_audio", True):
                continue
            rl = role(tr, c, catalog)
            lufs = segment_lufs(project, c)
            if lufs is None:
                report["clips"].append({"track": tr["name"], "start": c["start"], "role": rl, "silent": True})
                continue
            gain = max(-MAX_GAIN, min(MAX_GAIN, targets[rl] - lufs))
            c["gain_db"], c["lufs"] = round(gain, 1), round(lufs, 1)
            report["clips"].append({"track": tr["name"], "start": c["start"], "role": rl,
                                    "measured": round(lufs, 1), "gain_db": c["gain_db"]})
    T.save(project, tl)
    return report
