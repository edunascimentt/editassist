"""zoom-punch: punch-ins that hide jump cuts and add emphasis, centred on the speaker's face."""
from __future__ import annotations

from . import timeline as T
from .project import Project, read_json
from .reformat import face_center


def _focus(project: Project, c: dict, m: dict) -> tuple[float, float]:
    """Face position as 0..1 of the FITTED frame (accounts for an existing crop)."""
    fc = face_center(str(project.abs(c["media"])), c["in"], c["out"], samples=4)
    if not fc:
        return 0.5, 0.4
    x, y = fc[0] * m["width"], fc[1] * m["height"]
    crop = c.get("crop")
    if crop:
        x, y = (x - crop["x"]) / crop["w"], (y - crop["y"]) / crop["h"]
    else:
        x, y = x / m["width"], y / m["height"]
    return min(max(x, 0.0), 1.0), min(max(y - 0.05, 0.0), 1.0)  # keep a little headroom


def punch(project: Project, scale: float = 1.12, every: int = 2, track: str = "V1") -> dict:
    """Alternate framing on consecutive clips (wide, punched, wide...), the classic way to make
    jump cuts read as intentional. every=2: every second clip; every=3: one in three."""
    tl = T.load(project)
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    n = 0
    for i, c in enumerate(sorted(T.track(tl, track)["clips"], key=lambda c: c["start"])):
        m = catalog.get(c["media"])
        if not m or m.get("kind") != "video":
            continue
        if i % every == every - 1:
            x, y = _focus(project, c, m)
            c["zoom"] = {"scale": scale, "x": round(x, 3), "y": round(y, 3)}
            n += 1
        else:
            c.pop("zoom", None)
    T.save(project, tl)
    return {"punched": n}


def at(project: Project, t: float, dur: float, scale: float = 1.2, ramp: float = 0.0,
       track: str = "V1") -> dict:
    """Emphasis zoom on [t, t+dur] (timeline seconds): splits V1/A1 there and zooms the middle part.
    ramp > 0 makes it a push-in over `ramp` seconds instead of a hard punch."""
    tl = T.load(project)
    T.split(tl, t, (track,))  # picture only: the audio keeps playing untouched
    T.split(tl, t + dur, (track,))
    i = T.clip_at(tl, track, t + 0.01)
    if i is None:
        raise SystemExit(f"no clip on {track} at {t}s")
    c = T.track(tl, track)["clips"][i]
    catalog = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    m = catalog.get(c["media"])
    x, y = _focus(project, c, m) if m and m.get("kind") == "video" else (0.5, 0.4)
    c["zoom"] = {"scale": scale, "x": round(x, 3), "y": round(y, 3), **({"ramp": ramp} if ramp else {})}
    T.save(project, tl)
    return {"zoomed": {"start": c["start"], "end": round(T.end(c), 3), **c["zoom"]}}


def clear(project: Project) -> dict:
    tl = T.load(project)
    n = sum(1 for tr in tl["tracks"] for c in tr["clips"] if c.pop("zoom", None))
    T.save(project, tl)
    return {"cleared": n}
