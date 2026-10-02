"""resolve-mcp: launcher for samuelgursky/davinci-resolve-mcp, the MCP server that lets the agent
drive a RUNNING DaVinci Resolve Studio (timeline edits, grades, renders, markers...).

`.mcp.json` points Claude Code at `uv run ea resolve-mcp`, which starts the server from its managed
install (one per machine, created by `ea resolve-mcp --setup`, which setup.sh / setup.ps1 run).
Same command on macOS, Windows and Linux, no absolute paths in the repo, no network per launch.
Nothing may be printed to stdout here: stdout is the MCP JSON-RPC channel.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "4.8.26"  # pinned; bump deliberately after checking the changelog
APP = "davinci-resolve-mcp"


def install_root() -> Path:
    if os.environ.get("DAVINCI_RESOLVE_MCP_INSTALL_ROOT"):
        return Path(os.environ["DAVINCI_RESOLVE_MCP_INSTALL_ROOT"])
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP


def venv_python(root: Path) -> Path:
    return root / "venv" / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def serve(args: list[str]) -> int:
    root = install_root()
    py, server = venv_python(root), root / "src" / "server.py"
    if not (py.exists() and server.exists()):
        print(f"DaVinci Resolve MCP is not installed at {root}. Run: uv run ea resolve-mcp --setup",
              file=sys.stderr)
        return 1
    return subprocess.call([str(py), str(server), *args], cwd=str(root))


def setup(version: str = VERSION) -> int:
    npx = shutil.which("npx")
    if not npx:
        print("npx not found: install Node.js 20+ first", file=sys.stderr)
        return 1
    # the MCP needs Python 3.10+; hand it this project's interpreter (uv-managed 3.12) instead of
    # whatever `python3` is on PATH (macOS ships 3.9)
    env = {**os.environ, "DAVINCI_RESOLVE_MCP_PYTHON": sys.executable}
    return subprocess.call([npx, "-y", f"{APP}@{version}", "setup", "--clients", "manual",
                            "--update-policy", "notify"], env=env)
