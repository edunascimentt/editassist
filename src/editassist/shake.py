"""shake: find shaky footage and mark it for stabilisation.

Per clip on the timeline, the global motion between frames of the segment that is actually used is
measured with phase correlation on small grey frames (proxy when there is one). Camera moves (pans,
tracking a car) are smooth; handheld shake is the part that changes frame to frame. jitter = RMS of
motion minus its ~0.5 s moving average, in percent of the frame width. wobble = RMS of the camera path
around a smooth (quadratic) move: the slow sway of a hand-held camera that jitter averages away, and
that slow motion makes obvious. Clips above either threshold get `"stabilize": true` (a clip set to `"stabilize": false` is left alone: motion graphics, a logo sting and
intended whip pans read as shake). `ea render` / `ea bake` apply ffmpeg deshake, the Resolve native build calls the
item's Stabilize() (full quality, adjustable in the Inspector).
"""
from __future__ import annotations

import subprocess

from . import timeline as T
from .project import Project, read_json

# Measured on the inauguração footage (ZV-E1 4K, 2026-10-09): tripod shots jitter 0.03-0.09, hand-held
# 0.13-0.7 (0.6 left 33 of 38 hand-held clips unstabilised; the client saw them all). Wobble: tripod
# speeches 0.1-0.4 over 7 s, hand-held speeches 1.1-2.2.
THRESHOLD = 0.12  # jitter, % of frame width per frame
WOBBLE = 0.5  # % of frame width
W = 160
FPS = 15


def _frames(project: Project, src: str, a: float, b: float, rotated_h: int):
    import numpy as np

    cmd = ["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{max(b - a, 0.2):.3f}", "-i", src,
           "-vf", f"fps={FPS},scale={W}:{rotated_h},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, cwd=project.dir).stdout
    n = len(raw) // (W * rotated_h)
    return np.frombuffer(raw[:n * W * rotated_h], np.uint8).reshape(n, rotated_h, W).astype(np.float32)


def jitter(project: Project, media: str, a: float, b: float) -> float | None:
    """Frame-to-frame shake of media[a:b] in % of frame width, None if too short to tell."""
    m = measure(project, media, a, b)
    return m and m[0]


def measure(project: Project, media: str, a: float, b: float) -> tuple[float, float] | None:
    """(jitter, wobble) of media[a:b] in % of frame width, None if too short to tell."""
    import cv2
    import numpy as np

    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    m = catalog.get(media) or {}
    src = str(project.abs(m["proxy"])) if m.get("proxy") else str(project.abs(media))
    h = int(round(W * (m.get("height") or 9) / (m.get("width") or 16) / 2) * 2)
    f = _frames(project, src, a, b, h)
    if len(f) < 9:
        return None
    win = np.outer(np.hanning(f.shape[1]), np.hanning(f.shape[2])).astype(np.float32)
    d = np.array([cv2.phaseCorrelate(f[i] * win, f[i + 1] * win)[0] for i in range(len(f) - 1)])
    k = np.ones(7) / 7
    smooth = np.stack([np.convolve(d[:, j], k, "same") for j in (0, 1)], 1)
    resid = (d - smooth)[3:-3]
    path = np.cumsum(d, 0)
    x = np.arange(len(path))
    fit = np.stack([np.polyval(np.polyfit(x, path[:, j], 2), x) for j in (0, 1)], 1)
    return (float(np.sqrt(np.mean(np.sum(resid ** 2, 1))) / W * 100),
            float(np.sqrt(np.mean(np.sum((path - fit) ** 2, 1))) / W * 100))


MIN_SPAN = 1.2  # s of source: shorter slow-motion shots (0.2-0.7 s at 0.4x) gave too few frames to judge


def _window(project: Project, c: dict) -> tuple[float, float]:
    """The clip's source span, widened around its middle to MIN_SPAN when shorter (same take, same hand):
    short slow-motion shots used to be skipped, so they were never stabilised (2026-10-09)."""
    a, b = c["in"], c["out"]
    if b - a >= MIN_SPAN:
        return a, b
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    dur = (catalog.get(c["media"]) or {}).get("duration") or b + MIN_SPAN
    mid = (a + b) / 2
    a = max(0.0, min(mid - MIN_SPAN / 2, dur - MIN_SPAN))
    return a, min(dur, a + MIN_SPAN)


def mark(project: Project, threshold: float = THRESHOLD, dry_run: bool = False, wobble: float = WOBBLE) -> dict:
    tl = T.load(project)
    out = {"threshold": threshold, "wobble_threshold": wobble, "clips": []}
    for tr in tl["tracks"]:
        if tr["kind"] != "video":
            continue
        for c in tr["clips"]:
            if c.get("stabilize") is False:  # set by hand: motion graphics, intended whip pans
                continue
            if project.abs(c["media"]).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                continue
            if c["media"].startswith("work/motion/"):  # rendered titles/lower thirds: animation, not shake
                c.pop("stabilize", None)
                continue
            a, b = _window(project, c)
            m = measure(project, c["media"], a, b)
            if m is None:
                continue
            j, w = m
            shaky = j > threshold or w > wobble
            if not dry_run:
                if shaky:
                    c["stabilize"] = True
                else:
                    c.pop("stabilize", None)
            out["clips"].append({"track": tr["name"], "start": c["start"], "media": project.abs(c["media"]).name,
                                 "jitter_pct": round(j, 2), "wobble_pct": round(w, 2), "stabilize": shaky})
    if not dry_run:
        T.save(project, tl)
    out["marked"] = sum(1 for c in out["clips"] if c["stabilize"])
    return out
