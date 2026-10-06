"""Build a timeline.json directly in a running Resolve through its scripting API, clip by clip.

Used by `ea export --open` when `MediaPool.ImportTimelineFromFile` rejects the OTIO (it returned None
for every OTIO and FCP7 XML on Resolve Studio 21.0.0, even a 3-clip one). AppendToTimeline with
explicit source/record frames is exact and needs nothing but the media pool.

What 21.0's API can't do, and how it is handled:
- constant speed: no TimelineItem.SetSpeed (21.1+). A 59.94 clip slowed to the timeline rate (0.4 at
  23.976) gets its own pool copy conformed to the timeline fps (the camera S&Q workflow, full quality).
  Any other speed needs `ea bake` first.
- clip gain: audio items expose no Volume property; gains are reported for the user to set (or bake).
- fades / dips: no SetFades (21.1+); reported.
"""
from __future__ import annotations

from pathlib import Path

from . import timeline as T
from .export import exact_fps
from .project import Project, read_json


def _folder(mp, parent, name):
    for f in parent.GetSubFolderList() or []:
        if f.GetName() == name:
            return f
    return mp.AddSubFolder(parent, name)


def _key(path) -> str:
    return Path(path).resolve().as_posix()


def _pool_by_path(folder, out=None) -> dict:
    """Every clip in the pool under `folder`, by resolved file path (first one wins)."""
    out = {} if out is None else out
    for c in folder.GetClipList() or []:
        p = c.GetClipProperty("File Path")
        if p:
            out.setdefault(_key(p), c)
    for sub in folder.GetSubFolderList() or []:
        _pool_by_path(sub, out)
    return out


def build(project: Project, tl: dict, rp, name: str, srt: Path | None = None, folder_name: str = "editassist") -> dict:
    """Create timeline `name` in Resolve project `rp` from `tl`. Returns a report dict."""
    from .videofx import media_grade

    mp = rp.GetMediaPool()
    fps = exact_fps(tl["fps"])
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    root = _folder(mp, mp.GetRootFolder(), folder_name)
    slow_dir = _folder(mp, root, "slowmo")
    report = {"timeline": name, "placed": 0, "failed": [], "slowmo_conformed": 0, "luts": 0, "notes": []}

    # media already anywhere in the pool is reused (the user's own bins); the rest is imported here
    pool = _pool_by_path(mp.GetRootFolder())
    slow_pool = _pool_by_path(slow_dir)
    need, slow_need = set(), set()
    for tr in tl["tracks"]:
        for c in tr["clips"]:
            p = _key(project.abs(c["media"]))
            sp = c.get("speed", 1.0)
            if tr["kind"] == "audio" and sp != 1.0:
                raise SystemExit(f"{Path(p).name}: audio at speed {sp}; run `ea bake <project>` first")
            if tr["kind"] == "video" and sp != 1.0:
                src_fps = (catalog.get(c["media"]) or {}).get("fps") or 0
                if abs(src_fps * sp - fps) > 0.05 * fps:
                    raise SystemExit(f"{Path(p).name}: speed {sp} at {src_fps} fps can't be conformed to {fps:.3f}; "
                                     "run `ea bake <project>` first")
                slow_need.add(p)
            need.add(p)
    mp.SetCurrentFolder(root)
    missing = sorted(p for p in need if p not in pool)
    if missing:
        mp.ImportMedia(missing)
        pool = _pool_by_path(mp.GetRootFolder())
    mp.SetCurrentFolder(slow_dir)
    missing = sorted(p for p in slow_need if p not in slow_pool)
    if missing:
        mp.ImportMedia(missing)
        slow_pool = _pool_by_path(slow_dir)
    for p in slow_need:
        item = slow_pool.get(p)
        if item and abs(float(item.GetClipProperty("FPS") or 0) - fps) > 0.01:
            if item.SetClipProperty("FPS", f"{fps:.3f}"):
                report["slowmo_conformed"] += 1
    lost = [Path(p).name for p in need if p not in pool] + [Path(p).name for p in slow_need if p not in slow_pool]
    if lost:
        raise SystemExit("Resolve did not import: " + ", ".join(sorted(set(lost))))

    mp.SetCurrentFolder(root)
    tlo = mp.CreateEmptyTimeline(name)
    if not tlo:
        raise SystemExit(f"Resolve could not create timeline {name!r}")
    rp.SetCurrentTimeline(tlo)
    for k, v in (("useCustomSettings", "1"), ("timelineResolutionWidth", str(tl["width"])),
                 ("timelineResolutionHeight", str(tl["height"]))):
        tlo.SetSetting(k, v)
    start0 = tlo.GetStartFrame()
    vtracks = [t for t in tl["tracks"] if t["kind"] == "video"]
    atracks = [t for t in tl["tracks"] if t["kind"] == "audio"]
    while tlo.GetTrackCount("video") < len(vtracks):
        tlo.AddTrack("video")
    while tlo.GetTrackCount("audio") < len(atracks):
        tlo.AddTrack("audio", "stereo")
    for kind, tracks in (("video", vtracks), ("audio", atracks)):
        for i, t in enumerate(tracks, 1):
            tlo.SetTrackName(kind, i, t["name"])

    luts = {_key(project.abs(k)): str(project.abs(v["lut"])) for k, v in media_grade(project).items() if v.get("lut")}
    gains, fades = [], 0
    for kind, tracks in (("video", vtracks), ("audio", atracks)):
        for ti, t in enumerate(tracks, 1):
            for c in t["clips"]:
                p = _key(project.abs(c["media"]))
                slow = kind == "video" and c.get("speed", 1.0) != 1.0
                item = slow_pool[p] if slow else pool[p]
                m = catalog.get(c["media"]) or {}
                # source frames count the file's own frames; a wav is counted at the clip's pool rate
                src_fps = m.get("fps") if m.get("has_video") else float(item.GetClipProperty("FPS") or fps)
                src_fps = exact_fps(src_fps or fps)
                info = {"mediaPoolItem": item, "startFrame": round(c["in"] * src_fps),
                        "endFrame": round(c["out"] * src_fps), "trackIndex": ti,
                        "recordFrame": start0 + round(c["start"] * fps), "mediaType": 1 if kind == "video" else 2}
                res = mp.AppendToTimeline([info])
                if not res:
                    report["failed"].append(f"{kind} {t['name']} {Path(p).name} @{c['start']:.2f}s")
                    continue
                report["placed"] += 1
                it = res[0]
                lut = (c.get("color") or {}).get("lut")
                lut = str(project.abs(lut)) if lut else luts.get(p)
                if kind == "video" and lut and it.SetLUT(1, lut):
                    report["luts"] += 1
                if kind == "audio" and c.get("gain_db") and not it.SetProperty("Volume", c["gain_db"]):
                    gains.append(f"{t['name']} @{c['start']:.2f}s {c['gain_db']:+g} dB")
                if c.get("transition_in") or c.get("transition_out"):
                    fades += 1
    if srt and srt.exists():
        mp.SetCurrentFolder(root)
        sub = (mp.ImportMedia([str(srt)]) or [None])[0]
        if sub:
            if not tlo.GetTrackCount("subtitle"):
                tlo.AddTrack("subtitle")
            report["subtitles"] = bool(mp.AppendToTimeline([sub]))
    if gains:
        report["notes"].append("set these clip gains in Resolve (21.0's API has no audio volume): " + "; ".join(gains))
    if fades:
        report["notes"].append(f"{fades} fades/transitions to add by hand (no SetFades before Resolve 21.1)")
    want = round(T.length(tl) * fps)
    got = tlo.GetEndFrame() - start0
    if abs(got - want) > 2:
        report["notes"].append(f"length check: Resolve {got} frames, timeline.json {want}")
    return report
