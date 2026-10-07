"""Per-clip video filters shared by render (preview/delivery) and bake (files for NLE export).

Clip fields understood here (all optional, see timeline.py):
  crop        {"w","h","x","y"}             source-pixel crop (reformat)
  speed       1.0                           constant speed
  fit         "fill" | "fit"                fill frame (crop) or letterbox
  zoom        {"scale": 1.15, "x": .5, "y": .4, "ramp": 0}
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

import os
from pathlib import Path

from .project import Project, read_json


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
        f.append(f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2")
    z = c.get("zoom")
    if z and z.get("scale", 1) != 1:
        s, zx, zy, ramp = float(z["scale"]), float(z.get("x", 0.5)), float(z.get("y", 0.5)), float(z.get("ramp", 0))
        if ramp > 0:
            k = f"(1+{s - 1:.4f}*min(max(t-{t_offset:.3f},0)/{ramp:.3f},1))"
            f.append(f"scale=w='trunc({W}*{k}/2)*2':h='trunc({H}*{k}/2)*2':eval=frame")
        else:
            f.append(f"scale={round(W * s / 2) * 2}:{round(H * s / 2) * 2}")
        f.append(f"crop={W}:{H}:'(in_w-{W})*{zx}':'(in_h-{H})*{zy}'")
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
