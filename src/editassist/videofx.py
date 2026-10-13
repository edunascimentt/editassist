"""Per-clip video filters shared by render (preview/delivery) and bake (files for NLE export).

Clip fields understood here (all optional, see timeline.py):
  crop        {"w","h","x","y"}             source-pixel crop (reformat)
  speed       1.0                           constant speed
  fit         "fill" | "fit"                fill frame (crop) or letterbox
  zoom        {"scale": 1.15, "x": .5, "y": .4, "ramp": 0}
  whip        {"in": 0.2, "out": 0.2, "amp": 0.35}  zoom-through transition (ea transition --type zoom):
              the outgoing clip accelerates into a zoom over its last `out` s, the incoming one lands from
              it over its first `in` s, blurred on the fastest frames; baked like zoom (no NLE keyframes)
  visible     record seconds the clip shows (bake passes it: its decoded segment carries handles)
              punch-in after fitting; x/y = focus point 0..1; ramp > 0 animates 1.0 -> scale over
              `ramp` seconds (slow push-in)
  color       {"lut": "work/color/<id>.cube"}  (else the media's grade from work/color.json)
  opacity     0..1
  fade_in / fade_out   seconds, from/to black (transitions)
  dissolve_in seconds, alpha fade over the clip underneath (set by timeline.expand_transitions)

Filter strings reference files RELATIVE to the project dir: ffmpeg runs with cwd=project, which
keeps Windows drive letters ("C:") out of filter arguments, where ':' is a separator.
"""
from __future__ import annotations

import itertools
import os
from pathlib import Path

from .project import Project, read_json


WHIP_AMP = 0.35
_labels = itertools.count(1)  # unique filtergraph labels for the push-in overlay


def rel_for_filter(project: Project, path: Path) -> str | None:
    try:
        return os.path.relpath(Path(path).resolve(), project.dir).replace("\\", "/")
    except ValueError:  # other Windows drive
        return None


def media_grade(project: Project) -> dict:
    return read_json(project.path("work", "color.json"), {}) or {}


def clip_vfilter(project: Project, c: dict, W: int, H: int, fps: float, t_offset: float = 0.0,
                 apply_color: bool = True, grades: dict | None = None) -> list[str]:
    """Filter chain (list of filters) from a decoded source segment to a WxH frame.
    `t_offset`: seconds of handle before the clip's `in` in the decoded segment (bake), so that
    ramps and fades start at the clip's first visible frame."""
    f = []
    crop = c.get("crop")
    if crop:
        f.append(f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}")
    if c.get("stabilize"):  # handheld shake (ea shake); Resolve gets Stabilize() on the item instead
        f.append("deshake=rx=32:ry=32:edge=mirror")
    sp = c.get("speed", 1.0)
    f.append(f"setpts=(PTS-STARTPTS)/{sp}" if sp != 1.0 else "setpts=PTS-STARTPTS")
    f.append(f"fps={fps}")
    if c.get("fit", "fill") == "fill":
        f.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    else:
        # transparent bars: on an upper track the tracks below show around it, as in every NLE (opaque
        # black hid them in the preview only); over the black base, or baked to a file, they are black
        f.append(f"scale={W}:{H}:force_original_aspect_ratio=decrease,format=yuva420p,"
                 f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black@0")
    z = c.get("zoom") or {}
    wh = c.get("whip") or {}
    s, zx, zy, ramp = (float(z.get("scale", 1)), float(z.get("x", 0.5)), float(z.get("y", 0.45 if wh else 0.5)),
                       float(z.get("ramp", 0)))
    vis = c.get("visible", (c["out"] - c["in"]) / c.get("speed", 1.0))  # record seconds the clip shows
    if s != 1 or wh:
        k = f"(1+{s - 1:.4f}*min(max(t-{t_offset:.3f},0)/{ramp:.3f},1))" if ramp > 0 and s != 1 else f"{s:.4f}"
        amp = float(wh.get("amp", WHIP_AMP))
        if wh.get("in"):  # arrives zoomed in, settles (ease-out)
            k += f"*(1+{amp:.3f}*pow(1-min(max(t-{t_offset:.3f},0)/{wh['in']:.3f},1),2))"
        if wh.get("out"):  # accelerates into the cut (ease-in)
            k += f"*(1+{amp:.3f}*pow(min(max(t-{t_offset + vis - wh['out']:.3f},0)/{wh['out']:.3f},1),2))"
        if ramp > 0 or wh:
            # A frame size that changes per frame can't go through crop: it keeps the size it saw first, so
            # the window stuck to the top-left corner (push-ins drifted off their focus point). Overlay the
            # growing frame on a copy of the WxH one instead: overlay re-reads its size every frame.
            n = next(_labels)
            f.append(f"split[zc{n}][zs{n}];[zs{n}]scale=w='trunc({W}*{k}/2)*2':h='trunc({H}*{k}/2)*2':eval=frame"
                     f"[zz{n}];[zc{n}][zz{n}]overlay=x='-(overlay_w-{W})*{zx}':y='-(overlay_h-{H})*{zy}':eval=frame")
        else:
            f.append(f"scale={round(W * s / 2) * 2}:{round(H * s / 2) * 2}")
            f.append(f"crop={W}:{H}:'(in_w-{W})*{zx}':'(in_h-{H})*{zy}'")
        if wh:  # motion blur on the fastest frames either side of the cut
            on = []
            if wh.get("in"):
                on.append(f"lt(t-{t_offset:.3f},{wh['in'] * 0.6:.3f})")
            if wh.get("out"):
                on.append(f"gt(t-{t_offset:.3f},{vis - wh['out'] * 0.6:.3f})")
            f.append(f"gblur=sigma=14:enable='{'+'.join(on)}'")
    f.append("setsar=1")
    if apply_color:
        lut = (c.get("color") or {}).get("lut") or (grades if grades is not None else media_grade(project)).get(
            c["media"], {}).get("lut")
        if lut and project.abs(lut).exists():
            r = rel_for_filter(project, project.abs(lut))
            if r:
                f.append(f"lut3d=file='{r}'")
    d = (c["out"] - c["in"]) / sp
    if c.get("fade_in"):
        f.append(f"fade=t=in:st={t_offset:.3f}:d={c['fade_in']:.3f}")
    if c.get("fade_out"):
        f.append(f"fade=t=out:st={t_offset + d - c['fade_out']:.3f}:d={c['fade_out']:.3f}")
    alpha = "opacity" in c or c.get("dissolve_in")
    if alpha:
        f.append("format=yuva420p")
        if "opacity" in c:
            f.append(f"colorchannelmixer=aa={c['opacity']}")
        if c.get("dissolve_in"):
            f.append(f"fade=t=in:st={t_offset:.3f}:d={c['dissolve_in']:.3f}:alpha=1")
    return f
