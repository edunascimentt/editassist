"""ingest: catalog input media into work/media.json and extract analysis audio."""
from __future__ import annotations

from .media import extract_audio, probe, run
from .project import Project, media_kind, read_json, slug, write_json


def camera_meta(path) -> dict:
    """Sony XAVC (and other cameras writing NonRealTimeMeta XML) store the capture gamma, gamut and
    S&Q frame rate in an XML block near the END of the file: log footage needs a conversion LUT."""
    import re

    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 512 * 1024))
            tail = f.read().decode("latin-1")
    except OSError:
        return {}
    out = {}
    for key, name in (("gamma", "CaptureGammaEquation"), ("primaries", "CaptureColorPrimaries")):
        m = re.search(rf'name="{name}" value="([^"]+)"', tail)
        if m:
            out[key] = m.group(1)
    m = re.search(r'captureFps="([\d.]+)p?"', tail)
    if m:
        out["capture_fps"] = float(m.group(1))
    if "log" in out.get("gamma", "").lower():
        out["log"] = True
    return out


def make_proxy(src, px) -> None:
    """540p H.264 proxy, written to a .part file first so an interrupted run never leaves a truncated
    proxy that the next ingest would take as done."""
    px.parent.mkdir(parents=True, exist_ok=True)
    part = px.with_name(px.stem + ".part.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "scale=-2:540", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", str(part)])
    part.replace(px)


def ingest(project: Project, proxies: bool = False) -> dict:
    """Catalog first (written before any proxy, so transcription can start), then proxies in parallel:
    decoding 4K 10-bit 4:2:2 is software-only and one ffmpeg uses ~4 cores."""
    import os
    from concurrent.futures import ThreadPoolExecutor

    catalog = read_json(project.path("work", "media.json"), {})
    seen = set()
    todo = []
    for f in project.input_files():
        rel = project.rel(f)
        sid = slug(f)
        if sid in seen:  # same stem in two folders
            sid = slug(f.parent) + "__" + sid
        seen.add(sid)
        info = probe(f) if media_kind(f) != "image" else {"duration": 0, "has_video": True, "has_audio": False}
        entry = {"id": sid, "path": rel, "kind": media_kind(f), **info}
        if entry["kind"] == "video":
            entry.update(camera_meta(f))
        if info.get("has_audio"):
            wav = project.path("work", "audio", f"{sid}.wav")
            if not wav.exists():
                extract_audio(f, wav)
            entry["analysis_audio"] = project.rel(wav)
        if proxies and info.get("has_video") and entry["kind"] == "video":
            px = project.path("work", "proxies", f"{sid}.mp4")
            if px.exists():
                entry["proxy"] = project.rel(px)
            else:
                todo.append((sid, f, px))
        catalog[sid] = {**catalog.get(sid, {}), **entry}
    write_json(project.path("work", "media.json"), catalog)
    if todo:
        def one(job):
            sid, f, px = job
            make_proxy(f, px)
            return sid, px

        workers = max(1, min(len(todo), (os.cpu_count() or 4) // 4))
        with ThreadPoolExecutor(workers) as pool:
            done = dict(pool.map(one, todo))
        # other commands may have written media.json meanwhile: merge only the proxy field
        catalog = read_json(project.path("work", "media.json"), {})
        for sid, px in done.items():
            catalog[sid]["proxy"] = project.rel(px)
        write_json(project.path("work", "media.json"), catalog)
    return catalog


def media_by_id(project: Project) -> dict:
    catalog = read_json(project.path("work", "media.json"))
    if catalog is None:
        raise SystemExit("no work/media.json yet: run `ea ingest <project>` first")
    return catalog
