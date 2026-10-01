"""bake: render per-clip changes that NLE exchange formats don't carry reliably (crop, zoom,
constant speed, optionally colour) into new files under work/baked/, and repoint the timeline at
them. Baked clips are plain cuts of plain files, so they look and time identically in Resolve,
Premiere, After Effects and Final Cut. Transitions are not baked: dissolves export natively."""
from __future__ import annotations

import hashlib
import json

from . import timeline as T
from .media import probe, run
from .project import Project, read_json, write_json
from .videofx import clip_vfilter, media_grade

PICTURE_KEYS = ("crop", "zoom")


def atempo_chain(sp: float) -> str:
    """atempo accepts 0.5..100 per instance; chain for slower speeds."""
    parts = []
    while sp < 0.5:
        parts.append("atempo=0.5")
        sp /= 0.5
    parts.append(f"atempo={sp:.6f}")
    return ",".join(parts)


def _key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:10]


def bake(project: Project, color: bool = False, handles: float = 1.0) -> dict:
    tl = T.load(project)
    catalog = read_json(project.path("work", "media.json"), {}) or {}
    by_path = {m["path"]: m for m in catalog.values()}
    grades = media_grade(project)
    W, H, fps = tl["width"], tl["height"], tl["fps"]
    stats = {"baked": 0, "reused": 0}
    out_dir = project.path("work", "baked")
    out_dir.mkdir(parents=True, exist_ok=True)

    for tr in tl["tracks"]:
        for c in tr["clips"]:
            m = by_path.get(c["media"])
            if not m or m.get("kind") == "image":
                continue
            sp = float(c.get("speed", 1.0))
            video = tr["kind"] == "video" and m.get("kind") == "video"
            grade = (c.get("color") or grades.get(c["media"])) if (color and video) else None
            picture = video and any(k in c for k in PICTURE_KEYS)
            if not (picture or grade or sp != 1.0):
                continue
            a = max(0.0, c["in"] - handles * sp)  # source seconds, handles measured in record time
            b = min(m["duration"], c["out"] + handles * sp)
            head = (c["in"] - a) / sp  # record seconds of handle before the clip
            look = {k: c.get(k) for k in PICTURE_KEYS if video and c.get(k)}
            if grade:
                look["color"] = grade
            ext = ".mp4" if video else ".wav"
            dst = out_dir / f"{m['id']}_{_key(c['media'], round(a, 3), round(b, 3), sp, look, W, H, fps)}{ext}"
            if not dst.exists():
                cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(project.abs(c["media"]))]
                if video:
                    plain = {"media": c["media"], "in": a, "out": b, "fit": c.get("fit", "fill"), "speed": sp, **look}
                    chain = ",".join(clip_vfilter(project, plain, W, H, fps, t_offset=head, apply_color=bool(grade),
                                                  grades=grades))
                    cmd += ["-vf", chain, "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p"]
                    if m.get("has_audio"):
                        cmd += (["-af", atempo_chain(sp)] if sp != 1.0 else []) + ["-c:a", "aac", "-b:a", "256k"]
                else:
                    cmd += ["-vn", "-af", atempo_chain(sp), "-c:a", "pcm_s24le"]
                run(cmd + [str(dst)], cwd=project.dir)
                stats["baked"] += 1
            else:
                stats["reused"] += 1
            c["source"] = {"media": c["media"], "in": c["in"], "out": c["out"], "speed": sp, **look}
            d = T.dur(c)
            for k in PICTURE_KEYS + ("speed",):
                c.pop(k, None)
            if grade:
                c.pop("color", None)
                c["graded"] = True
            c["media"] = project.rel(dst)
            c["in"], c["out"] = head, head + d
            sid = "baked__" + dst.stem
            if sid not in catalog:
                catalog[sid] = {"id": sid, "path": project.rel(dst), "kind": "video" if video else "audio",
                                "derived": True, **probe(dst)}
                by_path[catalog[sid]["path"]] = catalog[sid]
    write_json(project.path("work", "media.json"), catalog)
    T.save(project, tl)
    return stats
