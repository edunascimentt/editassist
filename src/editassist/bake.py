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


def _audio_input(project: Project, c: dict, idx: int) -> tuple[list[str], str]:
    """ffmpeg input args + filter chain for one audio clip placed at its timeline time (as render does)."""
    sp = c.get("speed", 1.0)
    d = T.dur(c)
    fi, fo = c.get("afade_in", c.get("fade", 0.0)), c.get("afade_out", c.get("fade", 0.0))
    fades = (f",afade=t=in:d={fi:.3f}" if fi else "") + (f",afade=t=out:st={max(0, d - fo):.3f}:d={fo:.3f}" if fo else "")
    ms = int(round(c["start"] * 1000))
    args = ["-ss", f"{c['in']:.3f}", "-t", f"{c['out'] - c['in']:.3f}", "-i", str(project.abs(c["media"]))]
    chain = (f"[{idx}:a]asetpts=PTS-STARTPTS,{atempo_chain(sp) + ',' if sp != 1.0 else ''}aresample=48000,"
             f"aformat=channel_layouts=stereo,volume={c.get('gain_db', 0)}dB{fades},adelay={ms}:all=1[a{idx}]")
    return args, chain


def duck_stem(project: Project, tl: dict) -> tuple[dict, str | None]:
    """NLE exchange formats keep a clip's gain but not the render's sidechain ducking. Render the ducked
    clips (music beds) as ONE stem, already ducked under every other audio track, and return a copy of
    the timeline that uses it. Two ffmpeg passes: a sidechain key fed by an amix of many delayed inputs
    stopped at the last dialogue word (ffmpeg 8), a key rendered to a file first does not."""
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    ducked, key = [], []
    for tr in tl["tracks"]:
        if tr["kind"] != "audio":
            continue
        for c in tr["clips"]:
            m = catalog.get(c["media"])
            if m is not None and not m.get("has_audio", True):
                continue
            (ducked if c.get("duck") else key).append((tr["name"], c))
    if not ducked or not key:
        return tl, None
    total = T.length(tl)
    sig = _key(total, [c for _, c in ducked], [c for _, c in key])
    out_dir = project.path("work", "baked")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"music_ducked_{sig}.wav"
    if not stem.exists():
        def mix(clips, dst):
            args, fc = [], []
            for i, (_, c) in enumerate(clips):
                a, ch = _audio_input(project, c, i)
                args += a
                fc.append(ch)
            fc.append(f"anullsrc=r=48000:cl=stereo:d={total:.3f}[sil]")
            fc.append("".join(f"[a{i}]" for i in range(len(clips))) +
                      f"[sil]amix=inputs={len(clips) + 1}:normalize=0:duration=longest[m]")
            run(["ffmpeg", "-y", "-v", "error", *args, "-filter_complex", ";".join(fc), "-map", "[m]",
                 "-t", f"{total:.3f}", "-c:a", "pcm_s24le", str(dst)])

        key_wav, bed_wav = out_dir / f"duck_key_{sig}.wav", out_dir / f"duck_bed_{sig}.wav"
        mix(key, key_wav)
        mix(ducked, bed_wav)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(bed_wav), "-i", str(key_wav), "-filter_complex",
             # sidechaincompress drops a variable tail of what it still buffers at EOF: run both inputs
             # past the end and cut back to the exact length
             "[0:a]apad=pad_dur=2[b];[1:a]apad=pad_dur=2[k];"
             f"[b][k]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400,atrim=0:{total:.3f}[o]",
             "-map", "[o]", "-t", f"{total:.3f}", "-c:a", "pcm_s24le", str(stem)])
        key_wav.unlink()
        bed_wav.unlink()
    rel = project.rel(stem)
    dur = probe(stem)["duration"]
    first = ducked[0][0]
    out = json.loads(json.dumps(tl))
    for tr in out["tracks"]:
        if tr["kind"] == "audio":
            tr["clips"] = [c for c in tr["clips"] if not c.get("duck")]
        if tr["name"] == first:
            tr["clips"].insert(0, {"media": rel, "in": 0.0, "out": round(min(total, dur), 3), "start": 0.0,
                                   "note": "music, ducking baked under the other audio"})
    catalog_all = read_json(project.path("work", "media.json"), {}) or {}
    sid = stem.stem
    if sid not in catalog_all:  # validate/export look media up in the catalog
        catalog_all[sid] = {"id": sid, "path": rel, "kind": "audio", "derived": True, **probe(stem)}
        write_json(project.path("work", "media.json"), catalog_all)
    return out, rel
