"""timeline.json: the edit, in a format small enough for the model to read and write by hand.

{
  "name": "my-video", "fps": 30, "width": 1920, "height": 1080,
  "tracks": [
    {"kind": "video", "name": "V1", "clips": [
      {"media": "input/cam_a.mp4", "in": 12.40, "out": 18.90, "start": 0.0, "note": "hook"}
    ]},
    {"kind": "video", "name": "V2", "clips": [ ...b-roll / overlays, drawn above V1... ]},
    {"kind": "audio", "name": "A1", "clips": [ ...dialogue, usually mirrors V1... ]},
    {"kind": "audio", "name": "Music", "clips": [{"media": "work/music/bed.mp3", "in": 0, "out": 60,
                                                  "start": 0, "gain_db": -20, "duck": true}]}
  ],
  "markers": [{"time": 4.2, "note": "check this cut"}]
}

Times are seconds. `in`/`out` are source times, `start` is the record (timeline) time.
Paths are relative to the project dir. Video tracks listed later are drawn on top.

Optional clip fields:
  note, gain_db, speed (1.0, constant), opacity (0..1), fit ("fill" | "fit")
  crop  {"w","h","x","y"}                      reformat (source pixels)
  zoom  {"scale": 1.15, "x": .5, "y": .4, "ramp": 0}   punch-in / push-in (zoom-punch)
  color {"lut": "work/color/<id>.cube"}        per-clip grade (default: work/color.json per media)
  transition_in  {"type": "dissolve" | "dip" | "fade", "dur": 0.5}   at this clip's head
  transition_out {"type": "fade", "dur": 1.0}                         at its tail (to black)
  duck (music under dialogue), fade (audio fade in+out seconds)
  stabilize (true: handheld shake, set by `ea shake`), role ("dialogue"|"bed"|"music"|"sfx" for `ea level`),
  lufs (measured by `ea level`), channel ("L" | "R": use one side of a dual-mic stereo source, centred;
  set by `ea level` on dialogue, "stereo" keeps both)
"""
from __future__ import annotations

from .project import Project, media_kind, read_json, write_json

EPS = 1e-6


def load(project: Project) -> dict:
    tl = read_json(project.path("timeline.json"))
    if tl is None:
        raise SystemExit("no timeline.json yet: build one (rough-cut / silence-cut skills)")
    return tl


def save(project: Project, tl: dict) -> None:
    for tr in tl["tracks"]:
        tr["clips"].sort(key=lambda c: c["start"])
        for c in tr["clips"]:
            for k in ("in", "out", "start"):
                c[k] = round(float(c[k]), 3)
    write_json(project.path("timeline.json"), tl)


def new(project: Project) -> dict:
    s = project.settings
    return {"name": project.name, "fps": s["fps"], "width": s["width"], "height": s["height"],
            "tracks": [{"kind": "video", "name": "V1", "clips": []},
                       {"kind": "audio", "name": "A1", "clips": []}],
            "markers": []}


def dur(c: dict) -> float:
    return (c["out"] - c["in"]) / c.get("speed", 1.0)


def end(c: dict) -> float:
    return c["start"] + dur(c)


def channel_filter(c: dict) -> str:
    """ffmpeg filter (with trailing comma) for a clip's `channel`: one side of a stereo source played on
    both sides. Field recorders often put two mics on L and R (lavalier on one, camera or car mic on the
    other); played as stereo, the voice sits in one ear and the other mic's noise in the other."""
    ch = {"L": 0, "R": 1}.get(c.get("channel", ""))
    return "" if ch is None else f"pan=stereo|c0=c{ch}|c1=c{ch},"


def length(tl: dict) -> float:
    return max((end(c) for t in tl["tracks"] for c in t["clips"]), default=0.0)


def track(tl: dict, name: str, kind: str | None = None) -> dict:
    for t in tl["tracks"]:
        if t["name"] == name:
            return t
    t = {"kind": kind or ("audio" if name.upper().startswith("A") else "video"), "name": name, "clips": []}
    tl["tracks"].append(t)
    return t


def from_segments(project: Project, segments: list[dict], with_video: bool = True) -> dict:
    """Ripple-pack source segments [{media, in, out, note?}] into V1 + A1 back to back."""
    from .ingest import media_by_id

    catalog = media_by_id(project)
    by_path = {m["path"]: m for m in catalog.values()}
    tl = new(project)
    v1, a1 = track(tl, "V1"), track(tl, "A1")
    t = 0.0
    for seg in segments:
        media = seg["media"]
        if media in catalog:  # allow media ids as well as paths
            media = catalog[media]["path"]
        m = by_path.get(media, {})
        clip = {"media": media, "in": seg["in"], "out": seg["out"], "start": t}
        if seg.get("note"):
            clip["note"] = seg["note"]
        if with_video and m.get("has_video", True):
            v1["clips"].append(dict(clip))
        if m.get("has_audio", True):
            a1["clips"].append(dict(clip))
        t += seg["out"] - seg["in"]
    return tl


def normalize_media(project: Project, tl: dict) -> int:
    """Rewrite clip media paths to the form work/media.json uses (ingest stores resolved paths, so
    `input/clip.mp4` that is a symlink is catalogued as its target). Every command matches clips to
    the catalog by that exact string; a hand-written equivalent path silently lost its transcript,
    grade and duration checks. Returns how many clips changed."""
    catalog = read_json(project.path("work", "media.json"), {}) or {}
    by_real = {}
    for m in catalog.values():
        by_real.setdefault(project.abs(m["path"]).resolve().as_posix(), m["path"])
    changed = 0
    for tr in tl["tracks"]:
        for c in tr["clips"]:
            if "media" not in c:
                continue
            known = by_real.get(project.abs(c["media"]).resolve().as_posix())
            if known and known != c["media"]:
                c["media"] = known
                changed += 1
    return changed


def validate(project: Project, tl: dict) -> list[str]:

    problems = []
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    for tr in tl["tracks"]:
        clips = sorted(tr["clips"], key=lambda c: c["start"])
        for i, c in enumerate(clips):
            where = f"{tr['name']}[{i}] {c.get('media')}@{c.get('start')}"
            for k in ("media", "in", "out", "start"):
                if k not in c:
                    problems.append(f"{where}: missing `{k}`")
            if any(k not in c for k in ("media", "in", "out", "start")):
                continue
            p = project.abs(c["media"])
            if not p.exists():
                problems.append(f"{where}: media file not found ({p})")
            if c["out"] <= c["in"]:
                problems.append(f"{where}: out <= in")
            m = catalog.get(c["media"])
            if m and m.get("duration") and media_kind(p) != "image" and c["out"] > m["duration"] + 0.05:
                problems.append(f"{where}: out {c['out']} beyond media duration {m['duration']:.2f}")
            if i and c["start"] < end(clips[i - 1]) - 1 / tl["fps"]:
                problems.append(f"{where}: overlaps previous clip on same track (ends {end(clips[i-1]):.3f})")
    return problems


def gaps(tl: dict, track_name: str = "V1", min_gap: float = 0.04) -> list[tuple[float, float]]:
    out, t = [], 0.0
    for c in sorted(track(tl, track_name)["clips"], key=lambda c: c["start"]):
        if c["start"] - t > min_gap:
            out.append((round(t, 3), round(c["start"], 3)))
        t = max(t, end(c))
    return out


def remap(tl: dict, media: str, t: float, track_name: str = "A1") -> float | None:
    """Source time in `media` -> timeline time, or None if that moment was cut."""
    for c in track(tl, track_name)["clips"]:
        if c["media"] == media and c["in"] - EPS <= t <= c["out"] + EPS:
            return c["start"] + (t - c["in"]) / c.get("speed", 1.0)
    return None


def clip_at(tl: dict, track_name: str, t: float) -> int | None:
    for i, c in enumerate(track(tl, track_name)["clips"]):
        if c["start"] - EPS <= t < end(c) - EPS:
            return i
    return None


def split(tl: dict, t: float, tracks: tuple[str, ...] = ("V1", "A1")) -> int:
    """Cut every clip under timeline time t on the given tracks into two. Returns clips split."""
    n = 0
    for name in tracks:
        tr = track(tl, name)
        i = clip_at(tl, name, t)
        if i is None:
            continue
        c = tr["clips"][i]
        if t - c["start"] < 1 / tl["fps"] or end(c) - t < 1 / tl["fps"]:
            continue  # already a cut here
        src_t = c["in"] + (t - c["start"]) * c.get("speed", 1.0)
        a = {**c, "out": src_t}
        b = {**c, "in": src_t, "start": t}
        for k in ("transition_out",):
            a.pop(k, None)
        b.pop("transition_in", None)
        tr["clips"][i:i + 1] = [a, b]
        n += 1
    return n


def ripple(tl: dict, track_name: str = "V1", min_gap: float = 0.02) -> float:
    """Close gaps on `track_name` by pulling everything after each gap (all tracks) left."""
    closed = 0.0
    for a, b in reversed(gaps(tl, track_name, min_gap)):
        shift = b - a
        for tr in tl["tracks"]:
            for c in tr["clips"]:
                if c["start"] >= b - EPS:
                    c["start"] -= shift
        for mk in tl.get("markers", []):
            if mk["time"] >= b - EPS:
                mk["time"] -= shift
        closed += shift
    return round(closed, 3)


def cut_points(tl: dict, track_name: str = "V1") -> list[float]:
    cl = sorted(track(tl, track_name)["clips"], key=lambda c: c["start"])
    return [c["start"] for c in cl[1:]]


def expand_transitions(tl: dict) -> dict:
    """Render-time view: dissolves become overlaps (incoming clip starts `dur` earlier using its
    head handle, alpha/audio fade), dips/fades become fades to black. timeline.json keeps hard cut
    points; only render and bake see this."""
    import copy

    out = copy.deepcopy(tl)
    for tr in out["tracks"]:
        clips = sorted(tr["clips"], key=lambda c: c["start"])
        video = tr["kind"] == "video"
        for i, c in enumerate(clips):
            ti = c.pop("transition_in", None)
            to = c.pop("transition_out", None)
            if ti:
                d = float(ti.get("dur", 0.5))
                prev = clips[i - 1] if i else None
                adjacent = prev is not None and abs(end(prev) - c["start"]) < 1.5 / tl["fps"]
                kind = ti.get("type", "dissolve")
                if kind == "dissolve" and adjacent:
                    d = min(d, c["in"] / c.get("speed", 1.0))  # needs head handle in the source
                    if d > 0:
                        c["start"] -= d
                        c["in"] -= d * c.get("speed", 1.0)
                        if video:
                            c["dissolve_in"] = d
                        else:
                            c["afade_in"] = d
                            prev["afade_out"] = max(prev.get("afade_out", 0), d)
                elif kind == "dip" and adjacent:
                    key_in, key_out = ("fade_in", "fade_out") if video else ("afade_in", "afade_out")
                    c[key_in] = d / 2
                    prev[key_out] = d / 2
                else:  # fade from black (or a dissolve with nothing before it)
                    c["fade_in" if video else "afade_in"] = d
            if to:
                c["fade_out" if video else "afade_out"] = float(to.get("dur", 1.0))
        tr["clips"] = clips
    return out


def summary(tl: dict) -> str:
    lines = [f"{tl['name']}  {tl['width']}x{tl['height']} @ {tl['fps']}fps  length {length(tl):.2f}s"]
    for tr in tl["tracks"]:
        lines.append(f"  {tr['kind']:5s} {tr['name']:8s} {len(tr['clips'])} clips")
    g = gaps(tl)
    if g:
        lines.append(f"  V1 gaps: {g[:8]}{' ...' if len(g) > 8 else ''}")
    return "\n".join(lines)
