"""ingest: catalog input media into work/media.json and extract analysis audio."""
from __future__ import annotations

from .media import extract_audio, probe, run
from .project import Project, media_kind, read_json, slug, write_json


def ingest(project: Project, proxies: bool = False) -> dict:
    catalog = read_json(project.path("work", "media.json"), {})
    seen = set()
    for f in project.input_files():
        rel = project.rel(f)
        sid = slug(f)
        if sid in seen:  # same stem in two folders
            sid = slug(f.parent) + "__" + sid
        seen.add(sid)
        info = probe(f) if media_kind(f) != "image" else {"duration": 0, "has_video": True, "has_audio": False}
        entry = {"id": sid, "path": rel, "kind": media_kind(f), **info}
        if info.get("has_audio"):
            wav = project.path("work", "audio", f"{sid}.wav")
            if not wav.exists():
                extract_audio(f, wav)
            entry["analysis_audio"] = project.rel(wav)
        if proxies and info.get("has_video") and entry["kind"] == "video":
            px = project.path("work", "proxies", f"{sid}.mp4")
            if not px.exists():
                px.parent.mkdir(parents=True, exist_ok=True)
                run(["ffmpeg", "-y", "-v", "error", "-i", str(f), "-vf", "scale=-2:540", "-c:v", "libx264",
                     "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", str(px)])
            entry["proxy"] = project.rel(px)
        catalog[sid] = {**catalog.get(sid, {}), **entry}
    write_json(project.path("work", "media.json"), catalog)
    return catalog


def media_by_id(project: Project) -> dict:
    catalog = read_json(project.path("work", "media.json"))
    if catalog is None:
        raise SystemExit("no work/media.json yet: run `ea ingest <project>` first")
    return catalog
