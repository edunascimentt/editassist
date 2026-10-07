"""export: timeline.json -> editable projects for DaVinci Resolve, Premiere Pro, After Effects.

  resolve      output/<name>.otio  (File > Import > Timeline)  + optional auto-import via the
               Resolve scripting API (`--open`), which creates the project and timeline for you
  premiere     output/<name>.xml   FCP7 XML (File > Import)
  fcpx         output/<name>.fcpxml
  aftereffects output/<name>.jsx   (File > Scripts > Run Script File) builds the comp, layers,
               crops and caption text layers
SRT captions are written next to the exports when they exist (import as a subtitle track).
"""
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

from . import timeline as T
from .project import Project, media_kind, read_json

TARGETS = ("resolve", "premiere", "fcpx", "aftereffects")


def exact_fps(fps: float) -> float:
    """23.976 / 29.97 / 59.94 written to json are NTSC rates: use the exact n*1000/1001 so frame counts
    and FCPXML frame durations (1001/24000s) line up instead of drifting."""
    n = round(fps * 1.001)
    if abs(fps - round(fps)) > 0.01 and abs(fps - n * 1000 / 1001) < 0.01:
        return n * 1000 / 1001
    return float(fps)


def _fcpx_rates() -> None:
    """otio_fcpx_xml_adapter looks rates up by literal key (23.98, 29.97, 59.94): exact NTSC floats
    miss and every format gets an empty frameDuration (ValueError on export)."""
    import opentimelineio as otio

    # the plugin loader imports its own copy of the module: patch that one, not `import otio_fcpx_xml_adapter`
    table = otio.adapters.from_name("fcpx_xml").module().FRAMERATE_FRAMEDURATION
    for n in (24, 30, 48, 60, 120):
        table.setdefault(n * 1000 / 1001, f"1001/{n * 1000}s")


def to_otio(project: Project, tl: dict):
    import opentimelineio as otio

    fps = exact_fps(tl["fps"])
    rt = lambda sec: otio.opentime.RationalTime(round(sec * fps), fps)
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    timeline = otio.schema.Timeline(name=tl["name"], global_start_time=otio.opentime.RationalTime(0, fps))
    timeline.metadata["editassist"] = {"width": tl["width"], "height": tl["height"]}
    refs = {}
    for tr in tl["tracks"]:
        kind = otio.schema.TrackKind.Video if tr["kind"] == "video" else otio.schema.TrackKind.Audio
        track = otio.schema.Track(name=tr["name"], kind=kind)
        cursor = 0  # frames; record positions come from absolute times so rounding never drifts
        for c in sorted(tr["clips"], key=lambda c: c["start"]):
            start_f = round(c["start"] * fps)
            end_f = max(start_f + 1, round(T.end(c) * fps))
            if start_f > cursor:
                track.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(
                    duration=otio.opentime.RationalTime(start_f - cursor, fps))))
            elif start_f < cursor:  # overlap of a frame from rounding: trim the head
                start_f = cursor
            src = project.abs(c["media"])
            m = catalog.get(c["media"], {})
            if c["media"] not in refs:
                avail = None
                if m.get("duration"):
                    avail = otio.opentime.TimeRange(rt(0), rt(m["duration"]))
                refs[c["media"]] = (str(src), avail)
            url, avail = refs[c["media"]]
            ref = otio.schema.ExternalReference(target_url=otio.url_utils.url_from_filepath(url), available_range=avail)
            in_f = round(c["in"] * fps)
            dur_f = end_f - start_f
            clip = otio.schema.Clip(name=src.name, media_reference=ref,
                                    source_range=otio.opentime.TimeRange(
                                        otio.opentime.RationalTime(in_f, fps), otio.opentime.RationalTime(dur_f, fps)))
            meta = {k: c[k] for k in ("gain_db", "crop", "zoom", "color", "note", "speed", "opacity",
                                      "transition_in", "transition_out", "source") if k in c}
            if meta:
                clip.metadata["editassist"] = meta
            sp = c.get("speed", 1.0)
            if sp != 1.0:  # OTIO: source_range is the record length; the warp says how fast media plays
                clip.effects.append(otio.schema.LinearTimeWarp(name="speed", time_scalar=sp))
            ti = c.get("transition_in") or {}
            prev = track[-1] if len(track) else None
            if ti.get("type") == "dissolve" and isinstance(prev, otio.schema.Clip) and start_f == cursor:
                # centred dissolve: needs half its length of unused media (handle) on both sides of the cut
                half = int(round(ti.get("dur", 0.5) * fps / 2))
                head = in_f
                pa = prev.media_reference.available_range
                tail = (pa.end_time_exclusive().value - prev.source_range.end_time_exclusive().value) if pa else half
                half = max(0, min(half, head, tail))
                if half:
                    track.append(otio.schema.Transition(
                        name="Cross Dissolve", transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
                        in_offset=otio.opentime.RationalTime(half, fps), out_offset=otio.opentime.RationalTime(half, fps)))
            if c.get("note"):
                clip.markers.append(otio.schema.Marker(name=c["note"], marked_range=otio.opentime.TimeRange(
                    otio.opentime.RationalTime(in_f, fps), otio.opentime.RationalTime(1, fps))))
            track.append(clip)
            cursor = end_f
        timeline.tracks.append(track)
    for mk in tl.get("markers", []):
        timeline.tracks.markers.append(otio.schema.Marker(
            name=mk.get("note", ""), marked_range=otio.opentime.TimeRange(rt(mk["time"]), rt(1 / fps))))
    return timeline


def export(project: Project, targets: list[str], open_resolve: bool = False, into_current: bool = False,
           template: str | None = None) -> dict:
    import opentimelineio as otio

    tl = T.load(project)
    problems = T.validate(project, tl)
    if problems:
        raise SystemExit("timeline has problems, fix before exporting:\n  " + "\n  ".join(problems))
    crops = [c for tr in tl["tracks"] for c in tr["clips"]
             if c.get("crop") or c.get("zoom") or c.get("speed", 1.0) != 1.0]
    out_dir = project.path("output")
    out_dir.mkdir(exist_ok=True)
    name = tl["name"]
    written, warnings = {}, []
    if crops and any(t in targets for t in ("resolve", "premiere", "fcpx")):
        warnings.append(f"{len(crops)} clips carry crop/zoom/speed that XML/OTIO can't carry reliably; "
                        "run `ea bake <project>` before exporting to an NLE "
                        "(After Effects applies crops and zooms natively)")
    fades = [c for tr in tl["tracks"] for c in tr["clips"]
             if (c.get("transition_in") or {}).get("type") in ("fade", "dip") or c.get("transition_out")]
    if fades and any(t in targets for t in ("resolve", "premiere", "fcpx")):
        warnings.append(f"{len(fades)} fades/dips to black are not carried by XML/OTIO (dissolves are): "
                        "add them in the NLE (Resolve: Video Transitions > Dip to Color; Premiere: Dip to Black)")
    from .videofx import media_grade

    grades = media_grade(project)
    graded = sorted({g["lut"] for tr in tl["tracks"] if tr["kind"] == "video" for c in tr["clips"]
                     for g in [c.get("color") or grades.get(c["media"]) or {}] if g.get("lut") and not c.get("graded")})
    if graded:
        warnings.append("colour grades are LUTs: Resolve gets them applied with --open; in Premiere add them in "
                        "Lumetri > Basic > Input LUT, in AE with Effect > Utility > Apply Color LUT: " + ", ".join(graded))
    from .bake import duck_stem

    tl, stem = duck_stem(project, tl)  # NLEs keep gains but not the render's sidechain ducking
    if stem:
        written["music_stem"] = stem
        warnings.append(f"music ducking baked into {stem} (re-export after changing dialogue or music)")
    ot = to_otio(project, tl)
    if "resolve" in targets:
        p = out_dir / f"{name}.otio"
        otio.adapters.write_to_file(ot, str(p))
        written["resolve"] = project.rel(p)
        if open_resolve:
            written["resolve_import"] = resolve_import(project, tl, p, into_current, template)
    if "premiere" in targets:
        p = out_dir / f"{name}.xml"
        otio.adapters.write_to_file(ot, str(p), adapter_name="fcp_xml")
        written["premiere"] = project.rel(p)
    if "fcpx" in targets:
        p = out_dir / f"{name}.fcpxml"
        _fcpx_rates()
        try:  # third-party adapter: one odd timeline must not cost the user the other formats
            otio.adapters.write_to_file(ot, str(p), adapter_name="fcpx_xml")
            written["fcpx"] = project.rel(p)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"fcpx export failed in otio_fcpx_xml_adapter ({type(e).__name__}: {e}); "
                            "FCP needs a video clip under every connected clip. Import the Premiere XML instead.")
    if "aftereffects" in targets:
        p = out_dir / f"{name}.jsx"
        p.write_text(ae_script(project, tl), encoding="utf-8-sig")
        written["aftereffects"] = project.rel(p)
    srt = out_dir / f"{name}.srt"
    if srt.exists():
        written["captions"] = project.rel(srt)
    return {"written": written, "warnings": warnings}


# --- After Effects ---------------------------------------------------------------------------

def ae_script(project: Project, tl: dict) -> str:
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    W, H, fps, total = tl["width"], tl["height"], tl["fps"], max(T.length(tl), 1 / tl["fps"])
    v_media = {c["media"] for tr in tl["tracks"] if tr["kind"] == "video" for c in tr["clips"]}
    layers = []
    for tr in T.expand_transitions(tl)["tracks"]:
        for c in tr["clips"]:
            src = project.abs(c["media"])
            m = catalog.get(c["media"], {})
            layers.append({
                "file": src.as_posix(), "track": tr["name"], "kind": tr["kind"],
                "start": c["start"], "in": c["in"], "dur": T.dur(c), "speed": c.get("speed", 1.0),
                "gain": c.get("gain_db", 0), "crop": c.get("crop"), "opacity": c.get("opacity"),
                "zoom": c.get("zoom"), "fit": c.get("fit", "fill"),
                "fadeIn": c.get("dissolve_in") or c.get("fade_in") or 0, "fadeOut": c.get("fade_out") or 0,
                "afadeIn": c.get("afade_in") or 0, "afadeOut": c.get("afade_out") or 0,
                "still": media_kind(src) == "image",
                # dialogue lives on A-tracks; mute the copy embedded in the picture layer
                "mute": tr["kind"] == "video" and c["media"] in v_media,
                "srcw": m.get("width"), "srch": m.get("height"),
            })
    captions = (read_json(project.path("work", "captions.json"), {}) or {}).get("lines", [])
    caps = [{"t": " ".join(w["word"] for w in l["words"]), "a": l["start"], "b": l["end"]} for l in captions]
    data = {"name": tl["name"], "W": W, "H": H, "fps": fps, "total": total, "layers": layers, "captions": caps}
    return AE_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))


AE_TEMPLATE = r"""// Generated by editassist. In After Effects: File > Scripts > Run Script File...
(function () {
  var D = __DATA__;
  app.beginUndoGroup("editassist import");
  var proj = app.project || app.newProject();
  var bin = proj.items.addFolder(D.name + " media");
  var cache = {};
  function item(path, still) {
    if (cache[path]) return cache[path];
    var f = new File(path);
    if (!f.exists) { alert("editassist: missing media " + path); return null; }
    var io = new ImportOptions(f);
    if (still) io.sequence = false;
    var it = proj.importFile(io);
    it.parentFolder = bin;
    cache[path] = it;
    return it;
  }
  var comp = proj.items.addComp(D.name, D.W, D.H, 1, D.total, D.fps);
  // layers.add puts each new layer on top, so add bottom tracks first (tracks are listed bottom-up)
  for (var i = 0; i < D.layers.length; i++) {
    var c = D.layers[i];
    var it = item(c.file, c.still);
    if (!it) continue;
    var L = comp.layers.add(it);
    L.name = c.track + " " + it.name;
    if (c.still) { L.startTime = c.start; L.outPoint = c.start + c.dur; }
    else {
      if (c.speed !== 1) L.stretch = 100 / c.speed;
      L.startTime = c.start - c["in"] / c.speed;
      L.inPoint = c.start;
      L.outPoint = c.start + c.dur;
    }
    if (c.kind === "audio") { if (L.hasVideo) L.enabled = false; }
    else if (c.mute && L.hasAudio) L.audioEnabled = false;
    if (c.gain && L.hasAudio) L.property("ADBE Audio Group").property("ADBE Audio Levels").setValue([c.gain, c.gain]);
    if (c.opacity !== null && c.opacity !== undefined) L.property("ADBE Transform Group").property("ADBE Opacity").setValue(c.opacity * 100);
    if (c.kind === "video") {
      var tf = L.property("ADBE Transform Group");
      var base = 100, ax = null, ay = null;
      if (c.crop) {
        base = Math.max(D.W / c.crop.w, D.H / c.crop.h) * 100;
        ax = c.crop.x + c.crop.w / 2; ay = c.crop.y + c.crop.h / 2;
      } else if (L.source && L.source.width) {
        base = (c.fit === "fit" ? Math.min : Math.max)(D.W / L.source.width, D.H / L.source.height) * 100;
      }
      if (ax !== null) tf.property("ADBE Anchor Point").setValue([ax, ay]);
      var center = [D.W / 2, D.H / 2];
      tf.property("ADBE Position").setValue(center);
      tf.property("ADBE Scale").setValue([base, base]);
      if (c.zoom && c.zoom.scale && c.zoom.scale !== 1) {
        var s = c.zoom.scale, zx = c.zoom.x === undefined ? 0.5 : c.zoom.x, zy = c.zoom.y === undefined ? 0.5 : c.zoom.y;
        var pos = [D.W / 2 + D.W * (s - 1) * (0.5 - zx), D.H / 2 + D.H * (s - 1) * (0.5 - zy)];
        if (c.zoom.ramp) {  // push-in
          tf.property("ADBE Scale").setValueAtTime(c.start, [base, base]);
          tf.property("ADBE Scale").setValueAtTime(c.start + c.zoom.ramp, [base * s, base * s]);
          tf.property("ADBE Position").setValueAtTime(c.start, center);
          tf.property("ADBE Position").setValueAtTime(c.start + c.zoom.ramp, pos);
        } else {
          tf.property("ADBE Scale").setValue([base * s, base * s]);
          tf.property("ADBE Position").setValue(pos);
        }
      }
      var op = tf.property("ADBE Opacity"), full = (c.opacity === null || c.opacity === undefined) ? 100 : c.opacity * 100;
      if (c.fadeIn) { op.setValueAtTime(c.start, 0); op.setValueAtTime(c.start + c.fadeIn, full); }
      if (c.fadeOut) { op.setValueAtTime(c.start + c.dur - c.fadeOut, full); op.setValueAtTime(c.start + c.dur, 0); }
    }
    if (L.hasAudio && L.audioEnabled && (c.afadeIn || c.afadeOut)) {
      var lv = L.property("ADBE Audio Group").property("ADBE Audio Levels"), g = c.gain || 0;
      if (c.afadeIn) { lv.setValueAtTime(c.start, [-48, -48]); lv.setValueAtTime(c.start + c.afadeIn, [g, g]); }
      if (c.afadeOut) { lv.setValueAtTime(c.start + c.dur - c.afadeOut, [g, g]); lv.setValueAtTime(c.start + c.dur, [-48, -48]); }
    }
  }
  for (var k = 0; k < D.captions.length; k++) {
    var cap = D.captions[k];
    var T = comp.layers.addText(cap.t);
    T.name = "caption " + (k + 1);
    T.inPoint = cap.a; T.outPoint = Math.max(cap.b, cap.a + 1 / D.fps);
    var td = T.property("ADBE Text Properties").property("ADBE Text Document");
    var doc = td.value;
    doc.fontSize = Math.round(D.H * 0.055); doc.fillColor = [1, 1, 1];
    doc.applyStroke = true; doc.strokeColor = [0, 0, 0]; doc.strokeWidth = Math.round(D.H * 0.004);
    doc.strokeOverFill = false; doc.justification = ParagraphJustification.CENTER_JUSTIFY;
    td.setValue(doc);
    T.property("ADBE Transform Group").property("ADBE Position").setValue([D.W / 2, D.H * 0.82]);
  }
  comp.openInViewer();
  app.endUndoGroup();
})();
"""


# --- DaVinci Resolve scripting ---------------------------------------------------------------

def _resolve_paths() -> tuple[str, str]:
    system = platform.system()
    if system == "Darwin":
        return ("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
                "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so")
    if system == "Windows":
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        return (rf"{pd}\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
                rf"{pf}\Blackmagic Design\DaVinci Resolve\fusionscript.dll")
    return ("/opt/resolve/Developer/Scripting/Modules", "/opt/resolve/libs/Fusion/fusionscript.so")


def resolve_import(project: Project, tl: dict, otio_path: Path, into_current: bool = False,
                   template: str | None = None) -> str:
    """Create (or reuse) a Resolve project and import the timeline. Resolve must be running, and
    Preferences > System > General > External scripting using must be set to Local.
    into_current: add the timeline to the project open in Resolve instead of one named after it.
    If Resolve rejects the OTIO, the timeline is built natively clip by clip (resolve_native)."""
    mod_dir, lib = _resolve_paths()
    os.environ.setdefault("RESOLVE_SCRIPT_API", str(Path(mod_dir).parent))
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", lib)
    sys.path.append(mod_dir)
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except Exception as e:  # noqa: BLE001
        return f"skipped: Resolve scripting module not loadable ({e}). Import {otio_path.name} manually."
    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        return ("skipped: Resolve not reachable. Open Resolve and set Preferences > System > General > "
                f"External scripting using: Local, then retry. Or import {otio_path.name} manually.")
    pm = resolve.GetProjectManager()
    pm.SaveProject()  # loading another project closes the current one; never lose the user's work
    if into_current:
        rp = pm.GetCurrentProject()
        if not rp:
            return "failed: no project open in Resolve"
        if abs(float(rp.GetSetting("timelineFrameRate") or 0) - tl["fps"]) > 0.01 and not rp.GetTimelineCount():
            rp.SetSetting("timelineFrameRate", str(tl["fps"]))
    else:
        rp = pm.LoadProject(tl["name"]) or pm.CreateProject(tl["name"])
        if not rp:
            return "failed: could not create or open the Resolve project"
        if not rp.GetTimelineCount():
            rp.SetSetting("timelineFrameRate", str(tl["fps"]))
            rp.SetSetting("timelineResolutionWidth", str(tl["width"]))
            rp.SetSetting("timelineResolutionHeight", str(tl["height"]))
    mp = rp.GetMediaPool()
    existing = {rp.GetTimelineByIndex(i + 1).GetName() for i in range(rp.GetTimelineCount())}
    n = rp.GetTimelineCount() + 1
    while f"{tl['name']} v{n}" in existing:
        n += 1
    name = f"{tl['name']} v{n}"
    srt = otio_path.with_suffix(".srt")
    # a template (the user's styled timeline) can only be honoured by the native build
    timeline = None if template else mp.ImportTimelineFromFile(str(otio_path), {"timelineName": name,
                                                                                "importSourceClips": True})
    if not timeline:  # seen on Studio 21.0.0 for every OTIO/XML: build it clip by clip instead
        from .resolve_native import build

        rep = build(project, tl, rp, name, srt=srt, template=template)
        pm.SaveProject()
        notes = ("; " + "; ".join(rep["notes"])) if rep["notes"] else ""
        failed = f", {len(rep['failed'])} clips FAILED: {rep['failed']}" if rep["failed"] else ""
        how = f"inside a copy of '{template}'" if template else "Resolve rejected the OTIO"
        return (f"ok (built natively, {how}): project '{rp.GetName()}', timeline '{name}', "
                f"{rep['placed']} clips, LUT on {rep['luts']}, {rep['speed_conformed']} speed copies conformed, {rep['zooms']} zooms, "
                f"{rep.get('stabilized', 0)} stabilized, {rep.get('gain_baked', 0)} audio clips at their level"
                f"{', subtitles placed' if rep.get('subtitles') else ''}{failed}{notes}")
    rp.SetCurrentTimeline(timeline)
    # colour: apply each media's LUT (work/color.json) on node 1 of every clip from that media
    from .videofx import media_grade

    luts = {str(project.abs(k)): str(project.abs(v["lut"])) for k, v in media_grade(project).items() if v.get("lut")}
    applied = 0
    if luts:
        for ti in range(1, (timeline.GetTrackCount("video") or 0) + 1):
            for item in timeline.GetItemListInTrack("video", ti) or []:
                mpi = item.GetMediaPoolItem()
                path = mpi.GetClipProperty("File Path") if mpi else None
                if path and str(Path(path).resolve()) in luts and item.SetLUT(1, luts[str(Path(path).resolve())]):
                    applied += 1
    placed = False
    if srt.exists():
        sub = (mp.ImportMedia([str(srt)]) or [None])[0]
        if sub:  # a .srt pool item lands cue by cue on a subtitle track
            if not timeline.GetTrackCount("subtitle"):
                timeline.AddTrack("subtitle")
            placed = bool(mp.AppendToTimeline([sub]))
    pm.SaveProject()
    return (f"ok: project '{rp.GetName()}', timeline '{name}'"
            + ((" (subtitles placed)" if placed else " (SRT in media pool)") if srt.exists() else "")
            + (f", LUT applied to {applied} clips" if applied else ""))
