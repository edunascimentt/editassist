"""chapters: YouTube-ready chapter list from timeline times, validated, also written as timeline
markers (they travel to the NLE). The model picks titles from output/<name>_transcript.txt."""
from __future__ import annotations

from . import timeline as T
from .project import Project


def _ts(t: float, hours: bool) -> str:
    t = int(t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if hours else f"{m:02d}:{s:02d}"


def chapters(project: Project, spec: list[dict]) -> dict:
    tl = T.load(project)
    total = T.length(tl)
    items = sorted(({"time": float(c["time"]), "title": c["title"].strip()} for c in spec), key=lambda c: c["time"])
    problems = []
    if not items or items[0]["time"] > 0.5:
        problems.append("YouTube needs the first chapter at 00:00")
        items.insert(0, {"time": 0.0, "title": "Intro"})
    items[0]["time"] = 0.0
    if len(items) < 3:
        problems.append("YouTube shows chapters only with 3 or more")
    for a, b in zip(items, items[1:] + [{"time": total}]):
        if b["time"] - a["time"] < 10:
            problems.append(f"chapter {a['title']!r} is {b['time'] - a['time']:.1f}s; YouTube needs >= 10s")
    if items[-1]["time"] >= total:
        problems.append("last chapter starts after the end of the video")
    hours = total >= 3600
    text = "\n".join(f"{_ts(c['time'], hours)} {c['title']}" for c in items)
    dst = project.path("output", f"{tl['name']}_chapters.txt")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text + "\n", encoding="utf-8")
    tl["markers"] = [m for m in tl.get("markers", []) if not str(m.get("note", "")).startswith("chapter: ")]
    tl["markers"] += [{"time": c["time"], "note": f"chapter: {c['title']}"} for c in items]
    T.save(project, tl)
    return {"file": project.rel(dst), "chapters": text.splitlines(), "problems": problems}
