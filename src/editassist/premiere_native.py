"""premiere_native: build timeline.json LIVE in a running Premiere Pro through the bridge
(premiere_bridge + the editassist UXP panel). The Premiere counterpart of resolve_native.

`plan()` turns the timeline into a spec of exact ticks the panel executes with lib.js `build`:
- a new sequence from a generated .sqpreset (frame size, fps, enough V/A tracks; the 26.x API
  cannot add tracks), filed in bin `editassist`
- clips placed by overwrite edits, one undo step each, in track order, so the user watches it fill
- V clips whose audio mirrors an A clip go down linked; unused halves land on a scratch track and
  are deleted at the end
- framing (fill/fit, crop from `ea reformat`, punch-ins, push-in ramps) as Motion Scale + Position
- dissolves / dips / fades as real transitions, opacity, Warp Stabilizer on `stabilize` clips,
  sequence markers
- what the 26.x API can't set plays from rendered files (rendered_copies): speed and whip zooms (baked
  like `ea bake`), LUT grades (the segment with the LUT; Input LUT takes registered GUIDs only), audio
  with gain / fades / one-channel picks (bake.gain_copies), ducked music as a stem (bake.duck_stem)
- captions as a transparent picture layer styled like the preview, plus the .srt in the bin (the API
  can import it but not create a caption track)
"""
from __future__ import annotations

from pathlib import Path

from . import timeline as T
from .export import exact_fps, next_timeline_name
from .project import Project, read_json

TPS = 254016000000  # Premiere ticks per second
STILL = {"image"}


def ticks_per_frame(fps: float) -> int:
    return round(TPS / exact_fps(fps))


def frames(sec: float, fps: float) -> int:
    return round(sec * exact_fps(fps))


def src_ticks(sec: float) -> str:
    return str(round(sec * TPS))


# --- sequence preset --------------------------------------------------------------------------

AUDIO_TRACK = ('{"mAssign":0,"mAudioSends":[],"mChannelType":1,"mIsOpen":false,"mIsSubmix":false,'
               '"mKeyframeMode":true,"mLocked":false,"mMatrix":[],"mMute":false,"mName":"","mPan":0,'
               '"mPannerAssignments":[],"mSolo":false,"mSyncLock":true,"mTargeted":false,"mTrackID":-1,'
               '"mVolume":1}')


def sqpreset(name: str, width: int, height: int, fps: float, video_tracks: int, audio_tracks: int) -> str:
    """Premiere sequence preset (the format of Settings/SequencePresets/*.sqpreset in 26.x)."""
    from xml.sax.saxutils import escape

    tpf = ticks_per_frame(fps)
    audio = "[" + ",".join([AUDIO_TRACK] * audio_tracks) + "]"
    n = escape(name)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<PremiereData Version="3">
	<SequencePreset ObjectRef="1"/>
	<SequencePreset ObjectID="1" ClassID="5e73dd7e-4f86-4917-80eb-08ddb2f4a5f3" Version="9">
		<VideoTimeDisplay>{_time_display(fps)}</VideoTimeDisplay>
		<AudioTimeDisplay>200</AudioTimeDisplay>
		<VideoFrameRate>{tpf}</VideoFrameRate>
		<VideoFrameSize>0,0,{width},{height}</VideoFrameSize>
		<AudioFrameRate>5292000</AudioFrameRate>
		<AudioChannelType>1</AudioChannelType>
		<VideoFieldType>0</VideoFieldType>
		<Names Version="1">
			<NameItem Version="1" Index="0">
				<First>en_US</First>
				<Second>{n}</Second>
			</NameItem>
		</Names>
		<Descriptions Version="1">
			<DescriptionItem Version="1" Index="0">
				<First>en_US</First>
				<Second>editassist: {width}x{height} {exact_fps(fps):.3f} fps</Second>
			</DescriptionItem>
		</Descriptions>
		<EditingModeGUID.Mac>795454d9-d3c2-429d-9474-923ab13b7018</EditingModeGUID.Mac>
		<EditingModeGUID.Win>9678AF98-A7B7-4bdb-B477-7AC9C8DF4A4E</EditingModeGUID.Win>
		<PreviewPresetFileName.Mac>QuickTime</PreviewPresetFileName.Mac>
		<PreviewPresetVideoCodec.Mac>1634755443</PreviewPresetVideoCodec.Mac>
		<PreviewPresetFileName.Win>QuickTime</PreviewPresetFileName.Win>
		<PreviewPresetVideoCodec.Win>1634755443</PreviewPresetVideoCodec.Win>
		<VideoPixelAspectRatio>1,1</VideoPixelAspectRatio>
		<VideoUseMaxBitDepth>false</VideoUseMaxBitDepth>
		<VideoUseMaxRenderQuality>false</VideoUseMaxRenderQuality>
		<VideoAllowLinearCompositing>true</VideoAllowLinearCompositing>
		<AdaptiveNumChannels>2</AdaptiveNumChannels>
		<InitialNumberOfVideoTracks>{video_tracks}</InitialNumberOfVideoTracks>
		<AudioTracks>{audio}</AudioTracks>
		<VideoTracks>[]</VideoTracks>
		<PreviewVideoFrameSize>0,0,{width},{height}</PreviewVideoFrameSize>
	</SequencePreset>
</PremiereData>
"""


def _time_display(fps: float) -> int:
    """Timecode display id Premiere's own presets pair with each rate (Settings/SequencePresets, 26.x)."""
    return {23.976: 110, 24: 100, 25: 101, 29.97: 102, 30: 104, 48: 113, 50: 105, 59.94: 106,
            60: 108}.get(round(exact_fps(fps), 3), 102)


# --- framing ------------------------------------------------------------------------------------

def motion(c: dict, sw: int, sh: int, W: int, H: int, fps: float, prescaled: bool = False) -> dict | None:
    """Motion (scale % of source pixels, centre in sequence pixels) showing what `ea render` shows.
    `prescaled`: Premiere's "Scale to frame size" default is on, so 100 % is the clip fitted in the frame.
    A push-in (`zoom.ramp`) animates Scale AND Position: the render crops the growing frame at a fixed
    fraction, so an off-centre focus drifts with the scale (both are linear in time, two keyframes each)."""
    from .resolve_native import zoom_offset

    crop, z = c.get("crop"), c.get("zoom") or {}
    s = float(z.get("scale", 1))
    if crop:
        k = max(W / crop["w"], H / crop["h"])
        pan = -(crop["x"] + crop["w"] / 2 - sw / 2) * k
        tilt = (crop["y"] + crop["h"] / 2 - sh / 2) * k
    else:
        k = (max if c.get("fit", "fill") == "fill" else min)(W / sw, H / sh)
        pan = tilt = 0.0
    f = min(W / sw, H / sh) if prescaled else 1.0

    def centre(scale: float) -> list[float]:
        zp, zt = zoom_offset({**z, "scale": scale}, W, H) if scale != 1 else (0.0, 0.0)
        return [round(W / 2 + pan * scale + zp, 2), round(H / 2 - (tilt * scale + zt), 2)]

    if abs(k / f - 1) < 1e-6 and s == 1 and not crop:
        return None  # Premiere already shows the source this way
    m = {"scale": round(k * s * 100 / f, 3), "center": centre(s)}
    ramp = float(z.get("ramp", 0) or 0)
    if ramp > 0 and s != 1:  # push-in: from fill to the zoom over `ramp` seconds
        m["ramp"] = [[0, round(k * 100 / f, 3)], [round(ramp, 3), m["scale"]]]
        m["center_ramp"] = [[0, centre(1.0)], [round(ramp, 3), m["center"]]]
    return m


def scale_to_frame_default() -> dict:
    """Premiere's import scaling preferences (newest profile): with "Scale to frame size" on, clips are
    rasterised to fit the frame and Motion scale is relative to that. {"video": bool, "image": bool}"""
    import re

    import os

    homes = [Path.home() / "Documents", Path.home() / "OneDrive" / "Documents"]  # Windows often moves Documents
    if os.environ.get("OneDrive"):
        homes.append(Path(os.environ["OneDrive"]) / "Documents")
    prefs = sorted((p for h in homes for p in (h / "Adobe" / "Premiere Pro").glob("*/Profile-*/Adobe Premiere Pro Prefs")),
                   key=lambda p: p.stat().st_mtime)
    if not prefs:
        return {"video": False, "image": False}
    try:
        text = prefs[-1].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"video": False, "image": False}

    def on(tag: str) -> bool:
        m = re.search(rf"<{re.escape(tag)}>\s*(\w+)", text)
        return bool(m) and m.group(1).lower() == "true"

    return {"video": on("BE.Prefs.General.DefaultScaleToFrameSize"),
            "image": on("BE.Prefs.General.DefaultScaleToFrameSize") or on("BE.Prefs.StillImages.ScaleToProject")}


# --- plan -----------------------------------------------------------------------------------------

def _mirrors(v: dict, a: dict) -> bool:
    return (v["media"] == a["media"] and abs(v["in"] - a["in"]) < 1e-3 and abs(v["out"] - a["out"]) < 1e-3
            and abs(v["start"] - a["start"]) < 1e-3 and v.get("speed", 1.0) == a.get("speed", 1.0))


def rendered_copies(project: Project, tl: dict) -> tuple[dict, dict, list[str]]:
    """Copy of `tl` where what Premiere's 26.x API can't express plays from rendered files:
    - speed and whip zooms: the clip baked like `ea bake` (picture at sequence size, grade included)
    - a LUT grade: the segment with just the LUT, at source size (Input LUT takes registered GUIDs only;
      a .cube path is silently ignored), so framing stays editable in Premiere
    - audio at a speed: the segment time-stretched
    An audio clip mirroring a replaced video clip follows it to the same file, so the pair stays linked.
    Returns (timeline copy, catalog entries of the copies by path, notes)."""
    import copy

    from .bake import bake_clip, graded_copy
    from .videofx import media_grade

    tl = copy.deepcopy(tl)
    media = read_json(project.path("work", "media.json"), {}) or {}
    catalog = dict(media)
    by_path = {m["path"]: m for m in media.values()}
    grades = media_grade(project)
    out_dir = project.path("work", "baked")
    out_dir.mkdir(parents=True, exist_ok=True)
    W, H, fps = tl["width"], tl["height"], tl["fps"]
    notes: list[str] = []
    atracks = [t for t in tl["tracks"] if t["kind"] == "audio"]
    for tr in tl["tracks"]:
        if tr["kind"] != "video":
            continue
        for c in tr["clips"]:
            m = by_path.get(c["media"])
            if not m:
                continue
            sp = float(c.get("speed", 1.0))
            grade = c.get("color") or grades.get(c["media"]) or {}
            lut = grade.get("lut") if grade.get("lut") and not c.get("graded") else None
            if lut and not project.abs(lut).exists():
                notes.append(f"{tr['name']} {Path(c['media']).name}: LUT {lut} not found, left ungraded")
                lut = None
            twins = [a for at in atracks for a in at["clips"] if _mirrors(c, a)]
            before = (Path(c["media"]).name, c["start"])
            if (sp != 1.0 or c.get("whip")) and m.get("kind") == "video":
                bake_clip(project, c, m, True, grade or None, W, H, fps, out_dir, 1.0, grades, catalog, by_path)
                what = "speed" if sp != 1.0 else "whip zoom"
                notes.append(f"{tr['name']} {before[0]} @{before[1]:.2f}s: {what} rendered into {Path(c['media']).name}")
            elif lut:
                entry = graded_copy(project, c, m, lut, out_dir)
                by_path[entry["path"]] = entry
                notes.append(f"{tr['name']} {before[0]} @{before[1]:.2f}s: LUT {Path(lut).name} rendered into "
                             f"{Path(c['media']).name} (Lumetri on the original works too)")
            else:
                continue
            for a in twins:
                a.update({k: c[k] for k in ("media", "in", "out")})
                a.pop("speed", None)
    for tr in atracks:
        for c in tr["clips"]:
            m = by_path.get(c["media"])
            if m and float(c.get("speed", 1.0)) != 1.0:
                bake_clip(project, c, m, False, None, W, H, fps, out_dir, 1.0, grades, catalog, by_path)
    return tl, by_path, notes


def captions_overlay(project: Project, tl: dict) -> Path | None:
    """The timeline's captions (work/captions.json, styled like `ea render`) as a transparent ProRes 4444
    clip for the top video track. Premiere's UXP API can import an .srt but not put it on a caption track."""
    from .bake import _key
    from .caption_frames import build as caption_frames, caption_look
    from .media import run

    caps = T.captions(project, tl)
    if not caps or not caps.get("lines"):
        return None
    W, H, fps = tl["width"], tl["height"], tl["fps"]
    total = T.length(tl)
    out = project.path("work", "premiere", f"captions_{_key(caps, caption_look(project), W, H, fps, total)}.mov")
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        lst = caption_frames(project, W, H)
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-vf", f"fps={exact_fps(fps)},format=yuva444p10le", "-t", f"{total:.3f}",
             "-c:v", "prores_ks", "-profile:v", "4444", "-vendor", "apl0", str(out)])
    return out


def plan(project: Project, tl: dict, name: str | None = None, into_current: bool = False) -> dict:
    """Spec for lib.js `build`. Also returns what was rendered or cannot be carried (`warnings`, `skipped`)."""
    from .bake import duck_stem, gain_copies
    from .ingest import image_size

    srt_tl = tl
    tl, by_path, notes = rendered_copies(project, tl)
    tl, stem = duck_stem(project, tl)
    tl, gained = gain_copies(project, tl)
    fps, W, H = tl["fps"], tl["width"], tl["height"]
    tpf = ticks_per_frame(fps)
    rec = lambda sec: str(frames(sec, fps) * tpf)
    prescaled = scale_to_frame_default()
    vtracks = [t for t in tl["tracks"] if t["kind"] == "video"]
    atracks = [t for t in tl["tracks"] if t["kind"] == "audio"]
    overlay = captions_overlay(project, srt_tl)
    # past the edit's own tracks: the captions layer, then one scratch track of each kind for halves of
    # linked items the edit doesn't use
    cap_v = max(len(vtracks), 1)
    nv, na = cap_v + (1 if overlay else 0) + 1, max(len(atracks), 1) + 1
    scratch_v, scratch_a = nv - 1, na - 1
    clips, skipped, warnings = [], [], list(notes)
    linked = set()  # id() of audio clips already placed with their video

    def media_info(c):
        m = by_path.get(c["media"], {})
        if m.get("kind") == "image" and not m.get("width"):
            m = {**m, **image_size(project.abs(c["media"]))}
        return m

    for vi, tr in enumerate(vtracks):
        for c in sorted(tr["clips"], key=lambda c: c["start"]):
            m = media_info(c)
            partner = next(((ai, a) for ai, at in enumerate(atracks) for a in at["clips"]
                            if id(a) not in linked and _mirrors(c, a)), None)
            entry = _clip_entry(project, c, "video", f"{tr['name']}", rec, W, H, fps, m,
                                prescaled["image" if m.get("kind") == "image" else "video"])
            entry["video_track"] = vi
            if partner:
                ai, a = partner
                linked.add(id(a))
                entry["audio_track"] = ai
                entry["find"] = ["video", "audio"]
            elif m.get("has_audio") and m.get("kind") != "image":
                entry["audio_track"] = scratch_a
                entry["find"] = ["video", "audio"]
                entry["drop_audio"] = True
            else:
                entry["audio_track"] = scratch_a
                entry["find"] = ["video"]
            clips.append(entry)
    for ai, tr in enumerate(atracks):
        for c in sorted(tr["clips"], key=lambda c: c["start"]):
            if id(c) in linked:
                continue
            m = media_info(c)
            entry = _clip_entry(project, c, "audio", tr["name"], rec, W, H, fps, m, False)
            entry["audio_track"] = ai
            entry["video_track"] = scratch_v
            if m.get("has_video") and m.get("kind") == "video":
                entry["find"] = ["video", "audio"]
                entry["drop_video"] = True
            else:
                entry["find"] = ["audio"]
            clips.append(entry)
    if overlay:
        clips.append({"kind": "video", "track": "Captions", "name": overlay.name, "path": str(overlay),
                      "start": {"ticks": "0"}, "end": {"ticks": rec(T.length(srt_tl))}, "start_s": 0.0,
                      "in": {"ticks": "0"}, "out": {"ticks": src_ticks(T.length(srt_tl))},
                      "video_track": cap_v, "audio_track": scratch_a, "find": ["video"], "rename": "Captions"})
    clips.sort(key=lambda e: (e["kind"] != "video", e["track"], int(e["start"]["ticks"])))

    markers = [{"time": round(mk["time"], 3), "name": mk.get("note", ""), "comment": mk.get("note", "")}
               for mk in tl.get("markers", [])]
    out_dir = project.path("work", "premiere")
    out_dir.mkdir(parents=True, exist_ok=True)
    name = name or tl["name"]
    preset = out_dir / f"{tl['width']}x{tl['height']}_{exact_fps(fps):.3f}_{nv}v{na}a.sqpreset"
    preset.write_text(sqpreset(f"editassist {W}x{H}", W, H, fps, nv, na), encoding="utf-8")
    srt = project.path("output", f"{tl['name']}.srt")
    if overlay:
        warnings.append("captions placed as a picture layer (track 'Captions', styled like the preview); for "
                        f"editable captions drag {srt.name} from bin editassist onto the sequence and delete "
                        "that layer (Premiere's API can't create caption tracks)")
    elif srt.exists():
        warnings.append(f"{srt.name} imported into bin editassist: drag it onto the sequence for a caption "
                        "track (Premiere's API can't create caption tracks)")
    if stem:
        warnings.append(f"music ducking baked into {stem} (re-export after changing dialogue or music)")
    if gained:
        warnings.append(f"{gained} audio clips carry gain/fades/one-channel: placed as rendered copies "
                        "(work/baked/gain_*.wav) so they play at the preview's level")
    if prescaled["video"] or prescaled["image"]:
        warnings.append("Premiere's 'Scale to frame size' import default is on: framing was computed for it")
    return {
        "spec": {"name": name, "preset": str(preset), "width": W, "height": H, "fps": exact_fps(fps),
                 "ticks_per_frame": tpf, "video_tracks": nv, "audio_tracks": na, "bin": "editassist",
                 "into_current": into_current, "clips": clips, "markers": markers,
                 "srt": str(srt) if srt.exists() else None},
        "skipped": skipped, "warnings": warnings,
    }


def _clip_entry(project: Project, c: dict, kind: str, track: str, rec, W: int, H: int, fps: float,
                m: dict, prescaled: bool) -> dict:
    path = str(project.abs(c["media"]))
    e = {"kind": kind, "track": track, "name": Path(path).name, "path": path,
         "start": {"ticks": rec(c["start"])}, "end": {"ticks": rec(T.end(c))}, "start_s": round(c["start"], 3)}
    if m.get("kind") not in STILL:
        e["in"] = {"ticks": src_ticks(c["in"])}
        e["out"] = {"ticks": src_ticks(c["out"])}
    if kind == "video":
        if m.get("width") and m.get("height"):
            mo = motion(c, int(m["width"]), int(m["height"]), W, H, fps, prescaled)
            if mo:
                e["motion"] = mo
        if "opacity" in c and c["opacity"] != 1:
            e["opacity"] = float(c["opacity"])
        tr = []
        ti, to = c.get("transition_in") or {}, c.get("transition_out") or {}
        # fades = Cross Dissolve on the clip's open edge (linear, like `ea render`). A single-sided Dip to
        # Black holds black for half its length (checked on 26.3), so a dip OUT of a clip (= to black, the
        # render fades it) is a dissolve too. Dips between two clips stay Dip to Black.
        if ti.get("type") in ("dissolve", "dip"):
            tr.append({"type": ti["type"], "duration": float(ti.get("dur", 0.5)), "at": "start", "alignment": 0.5})
        elif ti.get("type") == "fade":
            tr.append({"type": "dissolve", "duration": float(ti.get("dur", 0.5)), "at": "start", "single": True})
        if to.get("type") in ("fade", "dissolve", "dip"):
            tr.append({"type": "dissolve", "duration": float(to.get("dur", 1.0)), "at": "end", "single": True})
        if tr:
            e["transitions"] = tr
        if c.get("stabilize"):
            e["effects"] = ["Warp Stabilizer"]
    return e


# --- build ----------------------------------------------------------------------------------------

def build(project: Project, name: str | None = None, into_current: bool = False, save: bool = True,
          on_progress=None) -> dict:
    """Build timeline.json as a new sequence in the project open in Premiere (or into its active one)."""
    from . import premiere_bridge as B

    tl = T.load(project)
    problems = T.validate(project, tl)
    if problems:
        raise SystemExit("timeline has problems, fix before building:\n  " + "\n  ".join(problems))
    info = B.call("info", wait=20)
    if not info.get("project"):
        raise SystemExit("no project open in Premiere: open (or create) one first, then retry")
    existing = {s["name"] for s in info.get("sequences", [])}
    if not into_current:
        name = name or tl["name"]
        if name in existing:
            name = next_timeline_name(name, existing)
    p = plan(project, tl, name, into_current)
    rep = B.call("build", {"spec": p["spec"], "label": name}, timeout=1800,
                 on_event=on_progress)
    if save:
        B.call("save")
    rep["skipped"] = p["skipped"]
    rep["warnings"] = p["warnings"]
    rep["premiere_project"] = info["project"]
    rep["expected_end"] = round(T.length(tl), 3)
    return rep
