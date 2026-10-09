"""Build a timeline.json directly in a running Resolve through its scripting API, clip by clip.

Used by `ea export --open` when `MediaPool.ImportTimelineFromFile` rejects the OTIO (it returned None
for every OTIO and FCP7 XML on Resolve Studio 21.0.0, even a 3-clip one). AppendToTimeline with
explicit source/record frames is exact and needs nothing but the media pool.

What 21.0's API can't do, and how it is handled:
- constant speed: no TimelineItem.SetSpeed (21.1+). A clip at speed s gets its own pool copy conformed
  to source fps x s when that is a rate Resolve can conform to: a 59.94 clip slowed to 0.4 in a 23.976
  timeline (the camera S&Q workflow), or sped up 2x as 119.88 in a 59.94 timeline. Full quality, the
  original media stays linked. One pool copy per (file, rate), in editassist/speed <rate>.
  Any other speed needs `ea bake` first.
- zoom: centred punch-ins set ZoomX/ZoomY on the item; an off-centre zoom is reported.
- clip gain / audio fades: audio items expose no Volume property and there is no SetFades, so audio
  clips with a gain or fade are placed as rendered copies with both applied (bake.gain_copies).
- fades / dips: no SetFades (21.1+); reported.
"""
from __future__ import annotations

import re

import math

from pathlib import Path

from . import timeline as T
from .export import exact_fps, resolve_rate
from .project import Project, read_json


def _folder(mp, parent, name):
    for f in parent.GetSubFolderList() or []:
        if f.GetName() == name:
            return f
    return mp.AddSubFolder(parent, name)


# Clip Attributes > Frame Rate choices in Resolve (what SetClipProperty("FPS", ...) can conform to)
CONFORM_RATES = (16, 18, 23.976, 24, 25, 29.97, 30, 47.952, 48, 50, 59.94, 60, 72, 95.904, 96, 100, 119.88, 120)


def conform_rate(src_fps: float, speed: float, timeline_fps: float | None = None) -> float | None:
    """The Resolve conform rate that plays a `src_fps` clip at `speed` (frame for frame), or None.
    The timeline's own rate always counts (S&Q footage conformed to the project rate)."""
    want = src_fps * speed
    if not want:
        return None
    best = min(CONFORM_RATES + ((timeline_fps,) if timeline_fps else ()), key=lambda r: abs(r - want))
    return best if abs(best - want) <= 0.002 * want else None


def _rate_name(r: float) -> str:
    return f"speed {r:g}"


def resolve_lut_dirs() -> list[Path]:
    """Folders Resolve loads LUTs from (SetLUT refuses a .cube anywhere else)."""
    import os
    import platform

    system = platform.system()
    if system == "Darwin":
        return [Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"),
                Path.home() / "Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"]
    if system == "Windows":
        return [Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Blackmagic Design/DaVinci Resolve/Support/LUT"]
    return [Path("/opt/resolve/LUT"), Path.home() / ".local/share/DaVinciResolve/LUT"]


def lut_for_resolve(project: Project, grade: dict) -> str | None:
    """The .cube to hand Resolve for a media's grade: the creative LUT itself when the grade is just
    that LUT (it already lives in Resolve's LUT folder, as the user's own LUTs do), else our baked
    cube. Resolve's SetLUT accepts only files inside its LUT folders: see _install_lut."""
    ops = grade.get("ops") or []
    if len(ops) == 1 and ops[0].get("op") == "lut" and project.abs(ops[0]["file"]).exists():
        return str(project.abs(ops[0]["file"]))
    return str(project.abs(grade["lut"])) if grade.get("lut") else None


def _install_lut(project: Project, lut: str, rp) -> str | None:
    """Copy a .cube into Resolve's LUT folder (editassist/<project>/) and refresh, so SetLUT takes it."""
    import shutil

    for d in resolve_lut_dirs():
        dst = d / "editassist" / project.dir.name / Path(lut).name
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lut, dst)
        except OSError:
            continue
        if hasattr(rp, "RefreshLUTList"):
            rp.RefreshLUTList()
        return str(dst)
    return None


def _key(path) -> str:
    return Path(path).resolve().as_posix()


def _conformed_bin(name: str) -> bool:
    """Our bins of conformed copies (their FPS no longer matches the file): never reuse them as-is."""
    return name.startswith("speed ") or name == "slowmo"


def _pool_by_path(folder, out=None, top_only: bool = False) -> dict:
    """Every clip in the pool under `folder`, by resolved file path (first one wins), skipping the
    bins of conformed copies. `top_only`: that folder's own clips, no subfolders."""
    out = {} if out is None else out
    for c in folder.GetClipList() or []:
        p = c.GetClipProperty("File Path")
        if p:
            out.setdefault(_key(p), c)
    if not top_only:
        for sub in folder.GetSubFolderList() or []:
            if not _conformed_bin(sub.GetName()):
                _pool_by_path(sub, out)
    return out


FINALS_BIN = "TIMELINES FINAIS"  # at the pool root: only the current version of each delivered video
OLD_BIN = "versões antigas"  # inside the editassist bin: versions a newer build replaced


def version_base(name: str) -> str:
    """"x v3" -> "x"; "x v1 v1" (an old naming bug) -> "x"."""
    while (m := re.match(r"^(.*?)\s+v\d+$", name)):
        name = m.group(1)
    return name


def file_timeline(rp, timeline) -> dict:
    """Put `timeline` in the finals bin and move the versions it replaces (same name, other version
    number) out of it and out of the editassist bin into editassist/versões antigas. The user wants
    finished timelines in a bin of their own, nothing else in it (2026-10-09)."""
    mp = rp.GetMediaPool()
    root, was = mp.GetRootFolder(), mp.GetCurrentFolder()
    finals = _folder(mp, root, FINALS_BIN)
    ours = _folder(mp, root, "editassist")
    item = timeline.GetMediaPoolItem()
    if not item:
        return {"bin": None, "note": "Resolve gave no media pool item for the timeline: not filed"}
    me, base = item.GetUniqueId(), version_base(timeline.GetName())
    old = [c for f in (finals, ours) for c in (f.GetClipList() or [])
           if c.GetClipProperty("Type") == "Timeline" and c.GetUniqueId() != me and version_base(c.GetName()) == base]
    if old:
        mp.MoveClips(old, _folder(mp, ours, OLD_BIN))
    ok = mp.MoveClips([item], finals)
    if was:
        mp.SetCurrentFolder(was)  # creating a bin selects it in the user's Media Pool
    if not ok:
        return {"bin": None, "note": f"Resolve refused to move the timeline into {FINALS_BIN}"}
    return {"bin": FINALS_BIN, "replaced": [c.GetName() for c in old]}


def _from_template(rp, template: str, name: str):
    """Duplicate the user's timeline `template` as `name` and empty it. Track styles (the subtitle
    track's font/size/position, which no API can set) and track names/layout survive."""
    src = next((t for t in (rp.GetTimelineByIndex(i + 1) for i in range(rp.GetTimelineCount()))
                if t and t.GetName() == template), None)
    if not src:
        raise SystemExit(f"template timeline {template!r} not found in project {rp.GetName()!r}")
    dup = src.DuplicateTimeline(name)
    if not dup:
        raise SystemExit(f"Resolve could not duplicate {template!r}")
    for kind in ("video", "audio", "subtitle"):
        for i in range(1, (dup.GetTrackCount(kind) or 0) + 1):
            items = dup.GetItemListInTrack(kind, i) or []
            if items:
                dup.DeleteClips(items, False)
    return dup


def build(project: Project, tl: dict, rp, name: str, srt: Path | None = None, folder_name: str = "editassist",
          template: str | None = None) -> dict:
    """Create timeline `name` in Resolve project `rp` from `tl`. Returns a report dict.
    `template`: build inside an emptied copy of that existing timeline (keeps its subtitle style)."""
    from .videofx import media_grade

    from .bake import gain_copies

    tl, gained = gain_copies(project, tl)
    mp = rp.GetMediaPool()
    fps = exact_fps(tl["fps"])
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    root = _folder(mp, mp.GetRootFolder(), folder_name)
    report = {"timeline": name, "placed": 0, "failed": [], "speed_conformed": 0, "luts": 0, "zooms": 0,
              "gain_baked": gained, "notes": []}

    # media already anywhere in the pool is reused (the user's own bins); the rest is imported here.
    # Speed changes need their own conformed copy per rate, kept in editassist/speed <rate>.
    pool = _pool_by_path(mp.GetRootFolder())
    need, speed_need = set(), {}  # speed_need: rate -> paths
    for tr in tl["tracks"]:
        for c in tr["clips"]:
            p = _key(project.abs(c["media"]))
            sp = c.get("speed", 1.0)
            if tr["kind"] == "audio" and sp != 1.0:
                raise SystemExit(f"{Path(p).name}: audio at speed {sp}; run `ea bake <project>` first")
            if tr["kind"] == "video" and sp != 1.0:
                src_fps = (catalog.get(c["media"]) or {}).get("fps") or 0
                rate = conform_rate(src_fps, sp, fps)
                if not rate:
                    raise SystemExit(f"{Path(p).name}: speed {sp} at {src_fps} fps is no Resolve conform rate "
                                     f"({src_fps * sp:.3f}); run `ea bake <project>` first")
                speed_need.setdefault(rate, set()).add(p)
            else:
                need.add(p)
    mp.SetCurrentFolder(root)
    missing = sorted(p for p in need if p not in pool)
    if missing:
        mp.ImportMedia(missing)
        pool = _pool_by_path(mp.GetRootFolder())
    speed_pool = {}
    for rate, paths in speed_need.items():
        d = _folder(mp, root, _rate_name(rate))
        got = _pool_by_path(d, top_only=True)
        mp.SetCurrentFolder(d)
        missing = sorted(p for p in paths if p not in got)
        if missing:
            mp.ImportMedia(missing)
            got = _pool_by_path(d, top_only=True)
        for p in paths:
            item = got.get(p)
            if not item:
                continue
            if abs(float(item.GetClipProperty("FPS") or 0) - rate) > 0.01:
                if not item.SetClipProperty("FPS", f"{rate:.3f}".rstrip("0").rstrip(".")):
                    raise SystemExit(f"Resolve refused to conform {Path(p).name} to {rate} fps")
                report["speed_conformed"] += 1
            speed_pool[(p, rate)] = item
    lost = [Path(p).name for p in need if p not in pool] + [Path(p).name for r, ps in speed_need.items()
                                                          for p in ps if (p, r) not in speed_pool]
    if lost:
        raise SystemExit("Resolve did not import: " + ", ".join(sorted(set(lost))))

    mp.SetCurrentFolder(root)
    rate = resolve_rate(fps)
    if str(rp.GetSetting("timelineFrameRate")) != rate and not template and rp.GetTimelineCount() == 0:
        rp.SetSetting("timelineFrameRate", rate)  # only possible while the project has no timeline
    tlo = _from_template(rp, template, name) if template else mp.CreateEmptyTimeline(name)
    if not tlo:
        raise SystemExit(f"Resolve could not create timeline {name!r}")
    rp.SetCurrentTimeline(tlo)
    for k, v in (("useCustomSettings", "1"), ("timelineResolutionWidth", str(tl["width"])),
                 ("timelineResolutionHeight", str(tl["height"])), ("timelineFrameRate", rate)):
        tlo.SetSetting(k, v)
    got_rate = str(tlo.GetSetting("timelineFrameRate") or "")
    try:
        off = abs(float(got_rate) - float(rate)) > 0.001
    except ValueError:  # Resolve answered nothing readable: don't block the build on it
        off = False
    if off:
        raise SystemExit(f"Resolve timeline runs at {got_rate} fps, the edit at {rate}: every cut would drift. "
                         f"Set the project frame rate to {rate} (only possible before its first timeline) "
                         f"or build into a timeline template at {rate}.")
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

    luts = {_key(project.abs(k)): lut_for_resolve(project, v) for k, v in media_grade(project).items() if v.get("lut")}
    installed: dict[str, str | None] = {}
    gains, fades = [], 0
    for kind, tracks in (("video", vtracks), ("audio", atracks)):
        for ti, t in enumerate(tracks, 1):
            clips = sorted(t["clips"], key=lambda c: c["start"])
            # a clip that ends less than a frame from the next one butts it: rounding the two edges
            # separately left 1-frame holes (sub-frame cut times from a builder, 2026-10-08)
            butt = {id(a): round(b["start"] * fps) for a, b in zip(clips, clips[1:])
                    if abs(b["start"] - T.end(a)) < 1.0 / fps}
            for c in clips:
                p = _key(project.abs(c["media"]))
                m = catalog.get(c["media"]) or {}
                sp = c.get("speed", 1.0) if kind == "video" else 1.0
                item = speed_pool[(p, conform_rate(m.get("fps") or 0, sp, fps))] if sp != 1.0 else pool[p]
                # source frames count the file's own frames; a wav is counted at the clip's pool rate
                src_fps = m.get("fps") if m.get("has_video") else float(item.GetClipProperty("FPS") or fps)
                src_fps = exact_fps(src_fps or fps)
                # record frames from absolute times, the source span derived from the record length:
                # rounding both ends separately left 1-frame holes between clips (seen live, 21.0)
                rec, rec_end = round(c["start"] * fps), butt.get(id(c), round(T.end(c) * fps))
                play = exact_fps(conform_rate(m.get("fps") or 0, sp, fps)) if sp != 1.0 else src_fps
                first = round(c["in"] * src_fps)
                info = {"mediaPoolItem": item, "startFrame": first,
                        # ceil: a span like 37 rec frames x 2.5 (59.94 in 23.976) = 92.5 rounded to 92
                        # gave Resolve 36.8 frames, truncated to 36: a 1-frame hole (2026-10-08)
                        "endFrame": first + math.ceil((rec_end - rec) * play / fps - 1e-6), "trackIndex": ti,
                        "recordFrame": start0 + rec, "mediaType": 1 if kind == "video" else 2}
                res = mp.AppendToTimeline([info])
                if not res:
                    report["failed"].append(f"{kind} {t['name']} {Path(p).name} @{c['start']:.2f}s")
                    continue
                report["placed"] += 1
                it = res[0]
                lut = (c.get("color") or {}).get("lut")
                lut = str(project.abs(lut)) if lut else luts.get(p)
                if kind == "video" and lut:
                    ok = it.SetLUT(1, lut)
                    if not ok:  # outside Resolve's LUT folders: install a copy there, once per file
                        if lut not in installed:
                            installed[lut] = _install_lut(project, lut, rp)
                        ok = bool(installed[lut]) and it.SetLUT(1, installed[lut])
                    if ok:
                        report["luts"] += 1
                    else:
                        report["failed"].append(f"LUT {Path(lut).name} on {Path(p).name} @{c['start']:.2f}s")
                if kind == "video" and c.get("stabilize"):
                    if hasattr(it, "Stabilize") and it.Stabilize():
                        report["stabilized"] = report.get("stabilized", 0) + 1
                    else:
                        report["notes"].append(f"{Path(p).name} @{c['start']:.2f}s: stabilize by hand (Inspector)")
                z = c.get("zoom") if kind == "video" else None
                if z and z.get("scale", 1) != 1:
                    if z.get("ramp") or abs(z.get("x", .5) - .5) > .01 or abs(z.get("y", .5) - .5) > .01:
                        report["notes"].append(f"{Path(p).name} @{c['start']:.2f}s: push-in / off-centre zoom "
                                               f"{z} to set by hand (centred ZoomX/Y set)")
                    if it.SetProperty("ZoomX", float(z["scale"])) and it.SetProperty("ZoomY", float(z["scale"])):
                        report["zooms"] += 1
                if kind == "audio" and c.get("gain_db") and not it.SetProperty("Volume", c["gain_db"]):
                    gains.append(f"{t['name']} @{c['start']:.2f}s {c['gain_db']:+g} dB")
                if c.get("transition_in") or c.get("transition_out"):
                    fades += 1
    if srt and srt.exists():
        import hashlib
        import shutil

        # a pool .srt keeps the text it had when first imported: re-importing the same path after
        # editing captions gave the OLD cues. Each build imports a copy named by its content.
        digest = hashlib.sha1(srt.read_bytes()).hexdigest()[:8]
        fresh = project.path("work", "baked", f"{srt.stem} {digest}.srt")
        fresh.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(srt, fresh)
        mp.SetCurrentFolder(root)
        sub = (mp.ImportMedia([str(fresh)]) or [None])[0]
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
