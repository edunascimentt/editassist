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

Dual-mic stereo: field recorders and cameras often take a lavalier on one channel and a camera or car
mic on the other. Measured (and played) as stereo, the other mic's road noise counts as voice: an
in-car take measured -14 LUFS and the voice was turned DOWN under the noise, in one ear. Before
measuring, each dialogue clip's channels are compared (mic_channel) and the voice side is set as
`channel` ("L"/"R", played on both sides). `"channel": "stereo"` on a clip keeps both.
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


SILENT_DB = 20.0  # a channel this far below the other carries nothing (unplugged or muted input)
SPREAD_DB = 4.0   # the close mic's level swings this much more between words and pauses than a room mic


def mic_channel(project: Project, media: str) -> str | None:
    """'L' or 'R' when the stereo `media` holds two different mics and one side is the voice,
    None for real stereo, mono, or when it can't tell. The close (voice) mic has the wide level
    spread (words vs pauses); a car or camera mic sits on a steady noise floor. The mic layout belongs to
    the recording, so the whole file is judged (first 5 min): a short clip of it can't always tell."""
    import subprocess

    import numpy as np

    src = str(project.abs(media))
    chans = run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels",
                 "-of", "csv=p=0", src], cwd=project.dir).stdout.strip()
    if chans != "2":
        return None
    hop = 1600  # 100 ms at 16 kHz
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", "300", "-i", src, "-vn", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, cwd=project.dir).stdout
    a = np.frombuffer(raw[: len(raw) // 4 * 4], np.float32)
    if len(a) < 2 * hop * 10:
        return None
    x = a[: len(a) // (2 * hop) * 2 * hop].reshape(-1, hop, 2)
    db = 20 * np.log10(np.sqrt((x ** 2).mean(1)) + 1e-9)  # 100 ms frames x 2 channels
    p10, p95 = np.percentile(db, 10, 0), np.percentile(db, 95, 0)
    if abs(p95[0] - p95[1]) >= SILENT_DB:
        return "LR"[int(p95[1] > p95[0])]
    flat = x.reshape(-1, 2)
    if np.corrcoef(flat[:, 0], flat[:, 1])[0, 1] >= 0.6:  # same sound on both sides: real stereo
        return None
    spread = p95 - p10
    if abs(spread[0] - spread[1]) < SPREAD_DB:
        return None
    return "LR"[int(spread[1] > spread[0])]


def segment_lufs(project: Project, c: dict) -> float | None:
    """Integrated loudness of the clip's source segment (its `channel` only, when set), or None when
    it is silent / too short."""
    r = run(["ffmpeg", "-v", "info", "-ss", f"{c['in']:.3f}", "-t", f"{max(c['out'] - c['in'], 0.1):.3f}",
             "-i", str(project.abs(c["media"])), "-vn", "-af", T.channel_filter(c) + "ebur128",
             "-f", "null", "-"], cwd=project.dir)
    vals = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    v = float(vals[-1]) if vals else -70.0
    return None if v <= -69 else v


def level(project: Project, targets: dict | None = None) -> dict:
    targets = {**TARGETS, **(targets or {})}
    tl = T.load(project)
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    report: dict = {"targets": targets, "clips": []}
    mics: dict[str, str | None] = {}
    for tr in tl["tracks"]:
        if tr["kind"] != "audio":
            continue
        for c in tr["clips"]:
            m = catalog.get(c["media"]) or {}
            if m and not m.get("has_audio", True):
                continue
            rl = role(tr, c, catalog)
            picked = None
            if rl == "dialogue" and "channel" not in c:
                if c["media"] not in mics:
                    mics[c["media"]] = mic_channel(project, c["media"])
                picked = mics[c["media"]]
                if picked:
                    c["channel"] = picked
            lufs = segment_lufs(project, c)
            if lufs is None:
                report["clips"].append({"track": tr["name"], "start": c["start"], "role": rl, "silent": True})
                continue
            gain = max(-MAX_GAIN, min(MAX_GAIN, targets[rl] - lufs))
            c["gain_db"], c["lufs"] = round(gain, 1), round(lufs, 1)
            report["clips"].append({"track": tr["name"], "start": c["start"], "role": rl,
                                    "measured": round(lufs, 1), "gain_db": c["gain_db"],
                                    **({"channel": picked} if picked else {})})
    T.save(project, tl)
    return report
