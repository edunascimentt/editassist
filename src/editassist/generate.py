"""generate: ElevenLabs (voiceover, sfx, music) and b-roll search (Pexels) / generation (Higgsfield).

API keys live in .env at the repo root (see .env.example). Generated files land in
work/<kind>/ and are registered in media.json so they can be put on the timeline.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from .media import probe
from .project import ROOT, Project, media_kind, read_json, write_json

load_dotenv(ROOT / ".env")
EL = "https://api.elevenlabs.io/v1"


def _key(name: str, hint: str) -> str:
    k = os.environ.get(name)
    if not k:
        raise SystemExit(f"{name} is not set. Add it to {ROOT / '.env'} ({hint})")
    return k


def _fname(text: str, ext: str) -> str:
    base = re.sub(r"[^\w]+", "_", text.lower()).strip("_")[:40] or "clip"
    return f"{base}_{int(time.time())}.{ext}"


def _register(project: Project, path: Path, kind: str, meta: dict) -> dict:
    catalog = read_json(project.path("work", "media.json"), {}) or {}
    sid = f"{kind}__{path.stem}"
    entry = {"id": sid, "path": project.rel(path), "kind": media_kind(path),
             "derived": True, "generated": meta, **probe(path)}
    catalog[sid] = entry
    write_json(project.path("work", "media.json"), catalog)
    return entry


def _post_audio(url: str, body: dict, dst: Path) -> Path:
    r = requests.post(url, json=body, headers={"xi-api-key": _key("ELEVENLABS_API_KEY", "elevenlabs.io > API keys"),
                                                "accept": "audio/mpeg"}, timeout=600)
    if r.status_code != 200:
        raise SystemExit(f"ElevenLabs {r.status_code}: {r.text[:400]}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(r.content)
    return dst


def voiceover(project: Project, text: str, voice: str | None = None, model: str = "eleven_multilingual_v2") -> dict:
    voice = voice or os.environ.get("ELEVENLABS_VOICE_ID")
    if not voice:
        raise SystemExit("no voice id: pass --voice or set ELEVENLABS_VOICE_ID (`ea voices` lists them)")
    dst = project.path("work", "voiceover", _fname(text, "mp3"))
    _post_audio(f"{EL}/text-to-speech/{voice}", {"text": text, "model_id": model}, dst)
    return _register(project, dst, "voiceover", {"text": text, "voice": voice, "model": model})


def voices() -> list[dict]:
    r = requests.get(f"{EL}/voices", headers={"xi-api-key": _key("ELEVENLABS_API_KEY", "elevenlabs.io > API keys")}, timeout=60)
    r.raise_for_status()
    return [{"voice_id": v["voice_id"], "name": v["name"], "labels": v.get("labels", {})} for v in r.json()["voices"]]


def sfx(project: Project, prompt: str, seconds: float | None = None) -> dict:
    body = {"text": prompt}
    if seconds:
        body["duration_seconds"] = max(0.5, min(30.0, seconds))
    dst = project.path("work", "sfx", _fname(prompt, "mp3"))
    _post_audio(f"{EL}/sound-generation", body, dst)
    return _register(project, dst, "sfx", {"prompt": prompt, "seconds": seconds})


def music(project: Project, prompt: str, seconds: float = 60, instrumental: bool = True) -> dict:
    body = {"prompt": prompt, "music_length_ms": int(max(3, min(600, seconds)) * 1000),
            "force_instrumental": instrumental}
    dst = project.path("work", "music", _fname(prompt, "mp3"))
    _post_audio(f"{EL}/music", body, dst)
    return _register(project, dst, "music", {"prompt": prompt, "seconds": seconds})


def dub(project: Project, target_lang: str, source: str | None = None, source_lang: str | None = None,
        speakers: int = 0, timeout_min: float = 60) -> dict:
    """ElevenLabs Dubbing: translated voice track that keeps each speaker's voice and the timing.
    `source`: a rendered mix (default output/<name>_preview.mp4 is NOT used: render the dialogue-only
    file first, see the dub skill). Returns the dubbed audio registered in media.json."""
    key = _key("ELEVENLABS_API_KEY", "elevenlabs.io > API keys")
    src = project.abs(source) if source else None
    if not src or not src.exists():
        raise SystemExit("pass --source <file>: the dialogue-only render to dub (see the dub skill)")
    data = {"target_lang": target_lang, "num_speakers": str(speakers), "watermark": "false",
            "name": f"{project.name} {target_lang}"}
    if source_lang:
        data["source_lang"] = source_lang
    with open(src, "rb") as fh:
        r = requests.post(f"{EL}/dubbing", headers={"xi-api-key": key}, data=data,
                          files={"file": (src.name, fh, "video/mp4" if src.suffix == ".mp4" else "audio/wav")}, timeout=600)
    if r.status_code != 200:
        raise SystemExit(f"ElevenLabs dubbing {r.status_code}: {r.text[:400]}")
    job = r.json()
    did = job["dubbing_id"]
    print(f"dubbing {did}: expected ~{job.get('expected_duration_sec', '?')} s", flush=True)
    deadline, delay = time.time() + timeout_min * 60, 5.0
    while True:
        st = requests.get(f"{EL}/dubbing/{did}", headers={"xi-api-key": key}, timeout=60).json()
        if st.get("status") == "dubbed":
            break
        if st.get("status") == "failed":
            raise SystemExit(f"dubbing failed: {st.get('error')}")
        if time.time() > deadline:
            raise SystemExit(f"dubbing {did} still {st.get('status')}; check later in the ElevenLabs dashboard")
        time.sleep(delay)
        delay = min(delay * 1.3, 20)
    dst = project.path("work", "dub", f"{project.name}_{target_lang}.mp4" if src.suffix == ".mp4" else f"{project.name}_{target_lang}.mp3")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(f"{EL}/dubbing/{did}/audio/{target_lang}", headers={"xi-api-key": key}, stream=True, timeout=600) as resp:
        if resp.status_code != 200:
            raise SystemExit(f"download of dub failed: HTTP {resp.status_code}")
        with open(dst, "wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                fh.write(chunk)
    return _register(project, dst, "dub", {"dubbing_id": did, "target_lang": target_lang, "source": project.rel(src)})


def broll_search(project: Project, query: str, orientation: str | None = None, n: int = 5,
                 download: int = 0) -> list[dict]:
    """Stock footage from Pexels (free key at pexels.com/api)."""
    params = {"query": query, "per_page": n}
    if orientation:
        params["orientation"] = orientation  # landscape | portrait | square
    r = requests.get("https://api.pexels.com/videos/search", params=params,
                     headers={"Authorization": _key("PEXELS_API_KEY", "free at pexels.com/api")}, timeout=60)
    r.raise_for_status()
    results = []
    for v in r.json().get("videos", []):
        files = sorted((f for f in v["video_files"] if f.get("height")), key=lambda f: f["height"])
        best = next((f for f in files if f["height"] >= 1080), files[-1] if files else None)
        if best:
            results.append({"id": v["id"], "url": v["url"], "duration": v["duration"], "preview": v["image"],
                            "file": best["link"], "size": f"{best['width']}x{best['height']}",
                            "credit": v["user"]["name"]})
    for item in results[:download]:
        dst = project.path("work", "broll", f"pexels_{item['id']}.mp4")
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(item["file"], stream=True, timeout=600) as resp:
                resp.raise_for_status()
                with open(dst, "wb") as fh:
                    for chunk in resp.iter_content(1 << 20):
                        fh.write(chunk)
        item["local"] = _register(project, dst, "broll", {"source": "pexels", "query": query,
                                                           "credit": item["credit"], "url": item["url"]})["path"]
    return results


def register_file(project: Project, path: str, kind: str = "broll", note: str = "") -> dict:
    """Bring in a file produced elsewhere (Higgsfield download, Remotion render, manual asset)."""
    p = Path(path).resolve()
    if not p.exists():
        raise SystemExit(f"file not found: {p}")
    return _register(project, p, kind, {"source": "manual", "note": note})
