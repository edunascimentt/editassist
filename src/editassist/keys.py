"""keys: API keys in .env. Status (masked), validation against free endpoints, and writing.

Values are never printed: only "set / valid / invalid" plus the last 4 characters.
Validation never spends credits: account or listing endpoints only.
"""
from __future__ import annotations

import os
import platform
import uuid

import requests
from dotenv import dotenv_values

from .project import ROOT

ENV = ROOT / ".env"

KEYS = {
    "ELEVENLABS_API_KEY": {"for": "voiceover, sound effects, music, dubbing", "where": "https://elevenlabs.io/app/settings/api-keys"},
    "ELEVENLABS_VOICE_ID": {"for": "default narration voice (optional; `ea voices` lists them)", "where": "uv run ea voices"},
    "HF_API_KEY_ID": {"for": "Higgsfield generated shots/images (with HF_API_KEY_SECRET)", "where": "https://console.higgsfield.ai"},
    "HF_API_KEY_SECRET": {"for": "Higgsfield (pair of HF_API_KEY_ID)", "where": "https://console.higgsfield.ai"},
    "PEXELS_API_KEY": {"for": "free stock b-roll search", "where": "https://www.pexels.com/api/"},
    "HF_TOKEN": {"for": "automatic speaker detection (optional diarize extra)", "where": "https://huggingface.co/settings/tokens"},
}


def _values() -> dict[str, tuple[str | None, str]]:
    """name -> (value, source). .env wins over the process environment, like python-dotenv does here."""
    file = dotenv_values(ENV) if ENV.exists() else {}
    out = {}
    for k in KEYS:
        if file.get(k):
            out[k] = (file[k], ".env")
        elif os.environ.get(k):
            out[k] = (os.environ[k], "environment")
        else:
            out[k] = (None, "-")
    return out


def _mask(v: str | None) -> str:
    return "" if not v else ("…" + v[-4:] if len(v) > 8 else "set")


def _check(name: str, v: str, vals: dict) -> tuple[bool | None, str]:
    try:
        if name == "ELEVENLABS_API_KEY":
            r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": v}, timeout=20)
            if r.status_code == 200:
                d = r.json()
                left = d.get("character_limit", 0) - d.get("character_count", 0)
                return True, f"plan {d.get('tier', '?')}, ~{left:,} credits left this period"
            if r.status_code in (401, 403):
                # restricted keys may lack the user scope: fall back to a scope TTS keys have
                r2 = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": v}, timeout=20)
                if r2.status_code == 200:
                    return True, "valid (restricted key: no account scope, voices OK)"
            return False, f"HTTP {r.status_code}: {r.text[:120]}"
        if name == "ELEVENLABS_VOICE_ID":
            key = vals["ELEVENLABS_API_KEY"][0]
            if not key:
                return None, "needs ELEVENLABS_API_KEY to check"
            r = requests.get(f"https://api.elevenlabs.io/v1/voices/{v}", headers={"xi-api-key": key}, timeout=20)
            return (True, f"voice '{r.json().get('name')}'") if r.status_code == 200 else (False, f"HTTP {r.status_code}")
        if name in ("HF_API_KEY_ID", "HF_API_KEY_SECRET"):
            kid, sec = vals["HF_API_KEY_ID"][0], vals["HF_API_KEY_SECRET"][0]
            if not (kid and sec):
                return None, "needs both HF_API_KEY_ID and HF_API_KEY_SECRET"
            # status of a request that can't exist: 404 = credentials accepted, 401 = rejected. Free.
            r = requests.get(f"https://api.higgsfield.ai/requests/{uuid.uuid4()}/status",
                             headers={"Authorization": f"Key {kid}:{sec}"}, timeout=20)
            if r.status_code == 404:
                return True, "credentials accepted"
            return False, f"HTTP {r.status_code}: {r.text[:120]}"
        if name == "PEXELS_API_KEY":
            r = requests.get("https://api.pexels.com/videos/search", params={"query": "city", "per_page": 1},
                             headers={"Authorization": v}, timeout=20)
            return (True, "search OK") if r.status_code == 200 else (False, f"HTTP {r.status_code}")
        if name == "HF_TOKEN":
            r = requests.get("https://huggingface.co/api/whoami-v2", headers={"Authorization": f"Bearer {v}"}, timeout=20)
            return (True, f"user {r.json().get('name')}") if r.status_code == 200 else (False, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        return None, f"network error: {e.__class__.__name__}"
    return None, "no check"


def status(check: bool = False, only: list[str] | None = None) -> list[dict]:
    vals = _values()
    rows = []
    for k, meta in KEYS.items():
        if only and k not in only:
            continue
        v, src = vals[k]
        row = {"key": k, "set": bool(v), "source": src, "value": _mask(v), "for": meta["for"], "get_it_at": meta["where"]}
        if check and v:
            ok, note = _check(k, v, vals)
            row.update(valid=ok, note=note)
        rows.append(row)
    return rows


def set_key(name: str, value: str) -> dict:
    """Write/replace one key in .env, keeping every other line and comment. Never echoes the value."""
    if name not in KEYS and not name.isupper():
        raise SystemExit(f"unknown key {name!r}; known: {', '.join(KEYS)}")
    value = value.strip().strip('"').strip("'")
    if not value or "\n" in value:
        raise SystemExit("empty or multi-line value")
    if not ENV.exists():
        example = ROOT / ".env.example"
        ENV.write_text(example.read_text(encoding="utf-8") if example.exists() else "", encoding="utf-8")
    lines = ENV.read_text(encoding="utf-8").splitlines()
    done = False
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == name:
            lines[i] = f"{name}={value}"
            done = True
    if not done:
        lines.append(f"{name}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if platform.system() != "Windows":
        os.chmod(ENV, 0o600)  # keys: owner-only
    os.environ[name] = value
    return {"key": name, "written_to": ".env", "value": _mask(value)}


def is_gitignored() -> bool:
    gi = ROOT / ".gitignore"
    return gi.exists() and any(l.strip() in (".env", "/.env") for l in gi.read_text(encoding="utf-8").splitlines())
