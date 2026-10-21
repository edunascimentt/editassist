"""reformat: change aspect ratio (16:9 -> 9:16, 1:1, 4:5) with face-aware crops per clip.

Default writes a `crop` box on every video clip (render honors it). `bake=True` also renders
each cropped clip to work/reframed/ and repoints the timeline at those files, which is what
NLE exports need: XML/OTIO can't carry per-clip crop boxes reliably across editors.
"""
from __future__ import annotations

import os
import statistics
from pathlib import Path

from . import timeline as T
from .project import ROOT, Project, read_json

ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}


YUNET = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"


def face_center(path: str, t0: float, t1: float, samples: int = 8,
                prefer: str | None = None) -> tuple[float, float] | None:
    """Face centre (0..1) over a time range, or None if no face found. `prefer` = left|right: in shots
    with several faces take the one on that side (where the podcast guest sits) instead of the biggest.
    YuNet (bundled ONNX, MIT) via cv2.FaceDetectorYN: works on OpenCV 4.5.4+ and 5.x."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")  # OpenCV 5 warns about DNN targets on every call
    import cv2

    cap = cv2.VideoCapture(path)
    det = None
    found = []
    for k in range(samples):
        t = t0 + (t1 - t0) * (k + 0.5) / samples
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (640, int(640 * h / w)))
        sh, sw = small.shape[:2]
        if det is None:
            det = cv2.FaceDetectorYN.create(str(YUNET), "", (sw, sh), 0.7)
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            found.append([((x + fw / 2) / sw, (y + fh / 2) / sh, fw * fh) for x, y, fw, fh in
                          (f[:4] for f in faces)])
    cap.release()
    return pick_face(found, prefer)


def pick_face(samples: list[list[tuple[float, float, float]]], prefer: str | None = None,
              same: float = 0.08) -> tuple[float, float] | None:
    """One face position from per-frame detections [(cx, cy, area), ...]. Each frame votes for one face
    (the biggest, or the one on the `prefer` side when several are in frame); the votes are grouped by
    position and the biggest group wins. A median over the raw votes averaged two people in a wide (the
    biggest face flips between guest and host, similar sizes) and framed the empty table between them
    (2026-10-20, podcast cortes)."""
    votes = []
    for faces in samples:
        if not faces:
            continue
        if prefer in ("left", "right") and len(faces) > 1:
            f = (min if prefer == "left" else max)(faces, key=lambda f: f[0])
        else:
            f = max(faces, key=lambda f: f[2])
        votes.append(f)
    if not votes:
        return None
    groups: list[list[tuple]] = []
    for v in sorted(votes, key=lambda f: f[0]):
        if groups and v[0] - groups[-1][-1][0] <= same:
            groups[-1].append(v)
        else:
            groups.append([v])
    best = max(groups, key=lambda g: (len(g), sum(f[2] for f in g)))
    return float(statistics.median(f[0] for f in best)), float(statistics.median(f[1] for f in best))


def split_at_cuts(project: Project, tl: dict, min_shot: float = 0.4, flashes: list | None = None) -> int:
    """Split video clips where the camera cuts inside them (a switched multi-camera feed: a podcast's
    program out goes wide, close-up, reaction), so every shot gets its own face crop. One crop for a
    whole bite framed the wide on the wrong person (2026-10-10). Audio clips stay whole."""
    from .scenes import cut_times

    n = 0
    for tr in tl["tracks"]:
        if tr["kind"] != "video":
            continue
        out = []
        for c in tr["clips"]:
            sp = c.get("speed", 1.0)
            every = cut_times(str(project.abs(c["media"])), 0.3, c["in"], c["out"])
            cuts = [t for t in every if c["in"] + min_shot <= t <= c["out"] - min_shot]
            if flashes is not None:  # a camera cut right at the clip's edge flashes the other shot
                flashes += [f"{c['start'] + (t - c['in']) / sp:.2f}s ({c.get('note') or Path(c['media']).name}): "
                            f"camera cut {t - c['in'] if t - c['in'] < min_shot else c['out'] - t:.2f}s from the "
                            f"{'head' if t - c['in'] < min_shot else 'tail'}; move the edit point"
                            for t in every if t not in cuts]
            edges = [c["in"], *cuts, c["out"]]
            for k, (a, b) in enumerate(zip(edges, edges[1:])):
                part = {**c, "in": a, "out": b, "start": c["start"] + (a - c["in"]) / sp}
                if k:
                    part.pop("transition_in", None)
                if k < len(edges) - 2:
                    part.pop("transition_out", None)
                out.append(part)
            n += len(cuts)
        tr["clips"] = out
    return n


def frame_size(aspect: str, width: int | None = None, height: int | None = None) -> tuple[int, int]:
    """Output size for `aspect` at the project's resolution: the short side stays (a 4K project,
    3840x2160 or 2160x3840, gives 2160x3840 for 9:16), never below the 1080 base. Reformat used to
    write 1080x1920 over a 4K project (2026-10-20; the user wants every timeline in 4K)."""
    W, H = ASPECTS[aspect]
    short = min(width or 0, height or 0)
    k = max(1.0, short / min(W, H))
    return int(round(W * k / 2)) * 2, int(round(H * k / 2)) * 2


def reformat(project: Project, aspect: str = "9:16", bake: bool = False, prefer: str | None = None) -> dict:
    if aspect not in ASPECTS:
        raise SystemExit(f"aspect must be one of {list(ASPECTS)}")
    tl = T.load(project)
    W, H = frame_size(aspect, tl.get("width"), tl.get("height"))
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    flashes: list[str] = []
    stats = {"clips": 0, "faces": 0, "split_at_cuts": split_at_cuts(project, tl, flashes=flashes)}
    if flashes:
        stats["flash_frames"] = flashes
    for tr in tl["tracks"]:
        if tr["kind"] != "video":
            continue
        for i, c in enumerate(tr["clips"]):
            m = catalog.get(c["media"])
            if not m or m.get("kind") != "video":
                continue
            sw, sh = m["width"], m["height"]
            target = W / H
            if sw / sh > target:
                cw, ch = int(sh * target) // 2 * 2, sh
            else:
                cw, ch = sw, int(sw / target) // 2 * 2
            fc = face_center(str(project.abs(c["media"])), c["in"], c["out"], prefer=prefer)
            cx, cy = fc if fc else (0.5, 0.45)
            stats["faces"] += bool(fc)
            x = int(min(max(cx * sw - cw / 2, 0), sw - cw))
            y = int(min(max(cy * sh - ch * 0.4, 0), sh - ch))  # face sits a bit above centre
            c["crop"] = {"w": cw, "h": ch, "x": x, "y": y}
            stats["clips"] += 1
    tl["width"], tl["height"] = W, H
    T.save(project, tl)
    if bake:
        from .bake import bake as do_bake

        stats.update(do_bake(project))
    return stats
