"""transitions: dissolves, dips to black and fades, stored on the incoming clip (timeline.py)."""
from __future__ import annotations

from . import timeline as T
from .project import Project

TYPES = ("dissolve", "dip", "fade")


def set_at(project: Project, times: list[float] | None, kind: str = "dissolve", dur: float = 0.5,
           tracks: tuple[str, ...] = ("V1", "A1"), all_cuts: bool = False) -> dict:
    if kind not in TYPES:
        raise SystemExit(f"type must be one of {TYPES}")
    tl = T.load(project)
    cuts = T.cut_points(tl, tracks[0])
    targets = cuts if all_cuts else [min(cuts, key=lambda c: abs(c - t)) for t in (times or []) if cuts]
    n = 0
    for name in tracks:
        for c in T.track(tl, name)["clips"]:
            if any(abs(c["start"] - t) < 1.5 / tl["fps"] for t in targets):
                c["transition_in"] = {"type": kind, "dur": dur}
                n += 1
    T.save(project, tl)
    warn = []
    if kind == "dissolve":
        short = [c["start"] for c in T.track(tl, tracks[0])["clips"]
                 if c.get("transition_in") and c["in"] < dur]
        if short:
            warn.append(f"not enough head handle for a {dur}s dissolve at {short}: it will be shorter there")
    return {"set": n, "cuts": [round(t, 3) for t in targets], "warnings": warn}


def fades(project: Project, fade_in: float = 0.0, fade_out: float = 0.0) -> dict:
    """Fade from black at the start and/or to black at the end, picture and sound."""
    tl = T.load(project)
    for tr in tl["tracks"]:
        cl = sorted(tr["clips"], key=lambda c: c["start"])
        if not cl:
            continue
        if fade_in and cl[0]["start"] < 0.05:
            cl[0]["transition_in"] = {"type": "fade", "dur": fade_in}
        if fade_out:
            last = max(cl, key=T.end)
            if abs(T.end(last) - T.length(tl)) < 0.05:
                last["transition_out"] = {"type": "fade", "dur": fade_out}
    T.save(project, tl)
    return {"fade_in": fade_in, "fade_out": fade_out}


def clear(project: Project) -> dict:
    tl = T.load(project)
    n = 0
    for tr in tl["tracks"]:
        for c in tr["clips"]:
            n += bool(c.pop("transition_in", None)) + bool(c.pop("transition_out", None))
    T.save(project, tl)
    return {"cleared": n}
