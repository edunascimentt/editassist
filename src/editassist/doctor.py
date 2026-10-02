"""doctor: one command that tells a new user what is missing."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess

from .project import MEMORY, ROOT


def doctor() -> bool:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    ok = True
    rows = []

    def row(name, good, detail, required=True):
        nonlocal ok
        ok &= good or not required
        rows.append(f"  [{'ok' if good else ('!!' if required else '--')}] {name}: {detail}")

    for b in ("ffmpeg", "ffprobe"):
        p = shutil.which(b)
        ver = subprocess.run([p, "-version"], capture_output=True, text=True).stdout.split("\n")[0] if p else "missing"
        row(b, bool(p), ver)
    node = shutil.which("node")
    row("node (Remotion)", bool(node), subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        if node else "missing: needed only for motion graphics", required=False)
    row("remotion deps", (ROOT / "remotion" / "node_modules").exists(), "npm install inside remotion/", required=False)
    try:
        import faster_whisper  # noqa: F401
        row("faster-whisper", True, "installed (model downloads on first transcribe)")
    except Exception as e:  # noqa: BLE001
        row("faster-whisper", False, str(e))
    row("memory/", MEMORY.exists(), "personal preferences (created by setup from memory.template/)")
    for k, why in (("ELEVENLABS_API_KEY", "voiceover / sfx / music"), ("PEXELS_API_KEY", "stock b-roll search")):
        row(k, bool(os.environ.get(k)), why, required=False)
    hf = bool(os.environ.get("HF_API_KEY_ID") and os.environ.get("HF_API_KEY_SECRET")) or os.environ.get("HF_KEY", "").count(":") == 1
    row("HF_API_KEY_ID/SECRET", hf, "Higgsfield generated shots and images", required=False)
    try:
        import pyannote.audio  # noqa: F401
        row("diarize extra", True, "automatic speaker detection", required=False)
    except ImportError:
        row("diarize extra", False, "optional: `uv sync --extra diarize` for automatic speakers (mic-per-person works without)", required=False)
    from .export import _resolve_paths
    mod, lib = _resolve_paths()
    row("Resolve scripting", os.path.exists(lib), "auto-import with `ea export --open` (manual import works without it)",
        required=False)
    from .resolve_mcp import VERSION, install_root, venv_python

    root = install_root()
    row("Resolve MCP", venv_python(root).exists() and (root / "src" / "server.py").exists(),
        f"live Resolve control via .mcp.json (davinci-resolve-mcp {VERSION}); `uv run ea resolve-mcp --setup`",
        required=False)
    print(f"editassist doctor ({platform.system()} {platform.machine()})")
    print("\n".join(rows))
    print("ready" if ok else "missing required pieces: run setup again")
    return ok
