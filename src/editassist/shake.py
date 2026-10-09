"""shake: find shaky footage and mark it for stabilisation.

Per clip on the timeline, the global motion between frames of the segment that is actually used is
measured with phase correlation on small grey frames (proxy when there is one). Camera moves (pans,
tracking a car) are smooth; handheld shake is the part that changes frame to frame. jitter = RMS of
motion minus its ~0.5 s moving average, in percent of the frame width. Clips above the threshold get
`"stabilize": true` (a clip set to `"stabilize": false` is left alone: motion graphics, a logo sting and
intended whip pans read as shake). `ea render` / `ea bake` apply ffmpeg deshake, the Resolve native build calls the
item's Stabilize() (full quality, adjustable in the Inspector).
"""
from __future__ import annotations

import subprocess

from . import timeline as T
from .project import Project, read_json

THRESHOLD = 0.6  # % of frame width per frame; ~1 px at 160 px wide. Tripod and gimbal shots stay < 0.4
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
    """Shake of media[a:b] in % of frame width, None if too short to tell."""
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
    return float(np.sqrt(np.mean(np.sum(resid ** 2, 1))) / W * 100)


def mark(project: Project, threshold: float = THRESHOLD, dry_run: bool = False) -> dict:
    tl = T.load(project)
    out = {"threshold": threshold, "clips": []}
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
            j = jitter(project, c["media"], c["in"], c["out"])
            if j is None:
                continue
            shaky = j > threshold
            if not dry_run:
                if shaky:
                    c["stabilize"] = True
                else:
                    c.pop("stabilize", None)
            out["clips"].append({"track": tr["name"], "start": c["start"], "media": project.abs(c["media"]).name,
                                 "jitter_pct": round(j, 2), "stabilize": shaky})
    if not dry_run:
        T.save(project, tl)
    out["marked"] = sum(1 for c in out["clips"] if c["stabilize"])
    return out
