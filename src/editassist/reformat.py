"""reformat: change aspect ratio (16:9 -> 9:16, 1:1, 4:5) with face-aware crops per clip.

Default writes a `crop` box on every video clip (render honors it). `bake=True` also renders
each cropped clip to work/reframed/ and repoints the timeline at those files, which is what
NLE exports need: XML/OTIO can't carry per-clip crop boxes reliably across editors.
"""
from __future__ import annotations

import os
import statistics

from . import timeline as T
from .project import ROOT, Project, read_json

ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}


YUNET = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"


def face_center(path: str, t0: float, t1: float, samples: int = 8) -> tuple[float, float] | None:
    """Median face centre (0..1) over a time range, or None if no face found.
    YuNet (bundled ONNX, MIT) via cv2.FaceDetectorYN: works on OpenCV 4.5.4+ and 5.x."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")  # OpenCV 5 warns about DNN targets on every call
    import cv2

    cap = cv2.VideoCapture(path)
    det = None
    xs, ys = [], []
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
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])[:4]  # biggest face = speaker
            xs.append((x + fw / 2) / sw)
            ys.append((y + fh / 2) / sh)
    cap.release()
    if not xs:
        return None
    return float(statistics.median(xs)), float(statistics.median(ys))


def reformat(project: Project, aspect: str = "9:16", bake: bool = False) -> dict:
    if aspect not in ASPECTS:
        raise SystemExit(f"aspect must be one of {list(ASPECTS)}")
    W, H = ASPECTS[aspect]
    tl = T.load(project)
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    stats = {"clips": 0, "faces": 0}
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
            fc = face_center(str(project.abs(c["media"])), c["in"], c["out"])
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
