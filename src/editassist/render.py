"""render: timeline.json -> mp4 with ffmpeg. Used for quick previews and for final delivery
when the user doesn't need an NLE project."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import timeline as T
from .media import filter_script_args, need
from .videofx import clip_vfilter, media_grade, rel_for_filter
from .project import ROOT, Project, media_kind, read_json

PRESETS = {
    # name: (target LUFS, true peak, scale_height or None)
    "preview": (-16, -1.5, 540),
    "youtube": (-14, -1.0, None),
    "instagram": (-14, -1.0, None),
    "tiktok": (-14, -1.0, None),
    "podcast": (-16, -1.0, None),
    "broadcast": (-23, -2.0, None),
}


def build_cmd(project: Project, tl: dict, out: Path, preset: str = "preview",
              subtitles: Path | None = None) -> list[str]:
    """ffmpeg command for the whole timeline. Run it with cwd=project.dir (see videofx)."""
    lufs, tp, scale_h = PRESETS[preset]
    tl = T.expand_transitions(tl)
    W, H, fps = tl["width"], tl["height"], tl["fps"]
    total = max(T.length(tl), 0.1)
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    grades = media_grade(project)
    args, fc, vlabels, alabels = [], [], [], []
    idx = 0
    fc.append(f"color=c=black:s={W}x{H}:r={fps}:d={total:.3f}[base]")
    for tr in tl["tracks"]:
        for c in tr["clips"]:
            src = project.abs(c["media"])
            kind = media_kind(src)
            m = catalog.get(c["media"]) or {}
            if preset == "preview" and tr["kind"] == "video" and m.get("proxy") and not c.get("crop"):
                src = project.abs(m["proxy"])  # same picture, 540p: previews of 4K footage render many times faster
            d = T.dur(c)
            sp = c.get("speed", 1.0)
            if tr["kind"] == "audio":
                m = catalog.get(c["media"])
                if (m is not None and not m.get("has_audio", True)) or kind == "image":
                    continue
            if kind == "image":
                args += ["-loop", "1", "-framerate", str(fps), "-t", f"{d:.3f}", "-i", str(src)]
            else:
                args += ["-ss", f"{c['in']:.3f}", "-t", f"{c['out'] - c['in']:.3f}", "-i", str(src)]
            if tr["kind"] == "video":
                chain = ",".join(clip_vfilter(project, c, W, H, fps, grades=grades))
                fc.append(f"[{idx}:v]{chain},setpts=PTS+{c['start']:.3f}/TB[v{idx}]")
                vlabels.append((f"v{idx}", c["start"], c["start"] + d))
            else:
                gain = c.get("gain_db", 0)
                tempo = f"atempo={sp}," if sp != 1.0 else ""
                fi = c.get("afade_in", c.get("fade", 0.0))
                fo = c.get("afade_out", c.get("fade", 0.0))
                fades = (f",afade=t=in:d={fi:.3f}" if fi else "") + \
                        (f",afade=t=out:st={max(0, d - fo):.3f}:d={fo:.3f}" if fo else "")
                ms = int(round(c["start"] * 1000))
                fc.append(f"[{idx}:a]asetpts=PTS-STARTPTS,{tempo}aresample=48000,"
                          f"aformat=channel_layouts=stereo,volume={gain}dB{fades},adelay={ms}:all=1"
                          f"[a{idx}]")
                alabels.append((f"a{idx}", tr["name"], c.get("duck", False)))
            idx += 1
    last = "base"
    for i, (lbl, a, b) in enumerate(vlabels):
        nxt = f"o{i}"
        fc.append(f"[{last}][{lbl}]overlay=eof_action=pass:enable='between(t,{a:.3f},{b:.3f})'[{nxt}]")
        last = nxt
    vf_tail = []
    if subtitles:
        from .caption_frames import build as caption_frames, has_libass

        rel_sub = rel_for_filter(project, subtitles)
        if has_libass() and subtitles.suffix.lower() in (".ass", ".srt") and rel_sub:
            flt = f"{'ass' if subtitles.suffix.lower() == '.ass' else 'subtitles'}='{rel_sub}'"
            fonts = rel_for_filter(project, ROOT / "assets" / "fonts")
            if fonts:  # bundled fonts so captions match on every machine
                flt += f":fontsdir='{fonts}'"
            vf_tail.append(flt)
        else:
            # translated captions (output/<name>_<lang>.ass) have their own captions_<stem>.json
            alt = f"work/captions_{subtitles.stem}.json"
            lst = caption_frames(project, W, H, alt if project.path(*alt.split("/")).exists() else "work/captions.json")
            args += ["-f", "concat", "-safe", "0", "-i", str(lst)]
            fc.append(f"[{idx}:v]format=rgba,setpts=PTS-STARTPTS[caps]")
            fc.append(f"[{last}][caps]overlay=eof_action=pass:format=auto[ocaps]")
            last = "ocaps"
            idx += 1
    if scale_h:
        vf_tail.append(f"scale=-2:{scale_h}")
    fc.append(f"[{last}]{','.join(vf_tail) or 'null'},format=yuv420p[vout]")
    if alabels:
        dialog = [l for l, _, duck in alabels if not duck]
        ducked = [l for l, _, duck in alabels if duck]
        if ducked and dialog:
            fc.append("".join(f"[{l}]" for l in dialog) + f"amix=inputs={len(dialog)}:normalize=0:duration=longest,asplit=2[dlg][key]")
            fc.append("".join(f"[{l}]" for l in ducked) + f"amix=inputs={len(ducked)}:normalize=0:duration=longest[bed]")
            # sidechaincompress ends at the KEY's end: unpadded, the music died after the last spoken word
            fc.append(f"[bed]apad[bedp];[key]apad[keyp];[bedp][keyp]sidechaincompress=threshold=0.03:ratio=8:attack=20:"
                      f"release=400,atrim=0:{total:.3f}[ducked]")
            fc.append("[dlg][ducked]amix=inputs=2:normalize=0:duration=longest[mix]")
        else:
            fc.append("".join(f"[{l}]" for l, _, _ in alabels) +
                      f"amix=inputs={len(alabels)}:normalize=0:duration=longest[mix]")
        fc.append(f"[mix]loudnorm=I={lufs}:TP={tp}:LRA=11,aresample=48000,atrim=0:{total:.3f}[aout]")
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    fc_file = project.path("work", "render_filter.txt")
    fc_file.write_text(";\n".join(fc), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats", *args, *filter_script_args(fc_file.resolve()),
           "-map", "[vout]"]
    if alabels:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    crf = "28" if preset == "preview" else "18"
    cmd += ["-c:v", "libx264", "-preset", "veryfast" if preset == "preview" else "medium", "-crf", crf,
            "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    return cmd


def render(project: Project, preset: str = "preview", out: str | None = None, subtitles: str | None = None) -> Path:
    need("ffmpeg")
    tl = T.load(project)
    problems = T.validate(project, tl)
    if problems:
        raise SystemExit("timeline has problems, fix before rendering:\n  " + "\n  ".join(problems))
    dst = project.abs(out) if out else project.path("output", f"{tl['name']}_{preset}.mp4")  # project-relative, like --subs
    sub = project.abs(subtitles) if subtitles else None
    cmd = build_cmd(project, tl, dst, preset, sub)
    res = subprocess.run(cmd, cwd=str(project.dir), capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit("render failed:\n" + "\n".join(res.stderr.strip().splitlines()[-20:]))
    return dst
