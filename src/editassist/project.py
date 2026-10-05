"""Project layout on disk.

projects/<name>/
  project.json      settings: fps, resolution, language, target platform
  input/            raw media dropped by the user (never modified)
  work/             everything derived: media.json, transcripts/, scenes/, frames/, audio/
  timeline.json     the edit, in editassist's own simple format (see timeline.py)
  output/           previews, renders, exported NLE projects
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = ROOT / "projects"
LOCAL_MEMORY = ROOT / "memory"
MEMORY_OS = ROOT / "vendor" / "memory-os"  # memory-os ships with the repo (upstream github.com/edunascimentt/memory-os)


def memory_dir() -> Path:
    """Where this user's EDITING memory lives (taste, styles, vocabulary, project log):
    1. EA_MEMORY_DIR if set
    2. memory-os global tier: ~/.memory-os/memory/editassist/  (private, shared by all the
       user's Claude accounts, never committed; system in vendor/memory-os, `ea memory --install`)
    3. <repo>/memory/  (gitignored fallback when memory-os isn't installed)
    Codebase knowledge is separate: .claude/_memory/ (memory-os project tier, committed)."""
    import os

    if os.environ.get("EA_MEMORY_DIR"):
        return Path(os.environ["EA_MEMORY_DIR"]).expanduser()
    global_tier = Path.home() / ".memory-os" / "memory"
    if global_tier.is_dir():
        return global_tier / "editassist"
    return LOCAL_MEMORY


def init_memory() -> dict:
    """Seed the editing memory from memory.template/ without touching existing files; when moving
    to memory-os, carry over anything already written in the local fallback."""
    import shutil

    dst = memory_dir()
    created, migrated = [], []
    for src in sorted((ROOT / "memory.template").rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(ROOT / "memory.template")
        target = dst / rel
        if target.exists():
            continue
        local = LOCAL_MEMORY / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if dst != LOCAL_MEMORY and local.exists() and local.read_bytes() != src.read_bytes():
            shutil.copy2(local, target)  # user already wrote here before memory-os existed
            migrated.append(str(rel))
        else:
            shutil.copy2(src, target)
            created.append(str(rel))
    if dst != LOCAL_MEMORY and LOCAL_MEMORY.is_dir():  # extra files written locally (new styles...)
        for f in LOCAL_MEMORY.rglob("*"):
            rel = f.relative_to(LOCAL_MEMORY)
            if f.is_file() and not (dst / rel).exists():
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst / rel)
                migrated.append(str(rel))
    index = dst.parent / "_index.md"
    line = "- [editassist/](editassist/preferences.md) — video-editing taste for editassist: pacing, captions, music, looks, vocabulary, named styles, delivery log"
    if dst != LOCAL_MEMORY and index.exists() and "editassist/" not in index.read_text(encoding="utf-8"):
        with open(index, "a", encoding="utf-8") as fh:
            fh.write("\n" + line + "\n")
    tier = "memory-os global (private)" if dst.parent == Path.home() / ".memory-os" / "memory" else (
        "EA_MEMORY_DIR" if dst != LOCAL_MEMORY else "local fallback (gitignored)")
    return {"dir": str(dst), "tier": tier, "created": created, "migrated": migrated}

def install_memory_os(run_installer: bool = True) -> dict:
    """Install memory-os from vendor/memory-os into ~/.memory-os, no network. The private memory/
    store is seeded here (same as its install.sh) so it works on every OS; install.sh then adds
    the parts that need bash (CLI on PATH, Claude account hooks), skipped on Windows without
    Git Bash. A git clone already at ~/.memory-os is left alone; a copied install gets its system
    files refreshed and keeps memory/."""
    import os
    import shutil
    import subprocess

    dst = Path.home() / ".memory-os"
    res: dict = {"store": str(dst)}
    if (dst / ".git").exists():
        res["system"] = "git clone, left as is (update with `memory-os update`)"
    else:
        shutil.copytree(MEMORY_OS, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("memory"))
        res["system"] = "copied from vendor/memory-os"
    store = dst / "memory"
    if not store.is_dir():
        (store / "journal").mkdir(parents=True)
        for f in (dst / "templates" / "global").glob("*.md"):
            shutil.copy2(f, store / ("journal" if f.name == "log.md" else "") / f.name)
        res["seeded"] = True
    bash = shutil.which("bash")
    if not run_installer:
        res["install_sh"] = "skipped"
    elif os.name == "nt" or not bash:
        res["install_sh"] = "skipped: run ~/.memory-os/install.sh from Git Bash for the CLI and account hooks"
    else:
        r = subprocess.run([bash, str(dst / "install.sh")], capture_output=True, text=True,
                           env={**os.environ, "HOME": str(Path.home())})
        res["install_sh"] = "ok" if r.returncode == 0 else "failed: " + r.stderr.strip()[-300:]
    return res | {"editing_memory": init_memory()}


MEDIA_EXT = {
    "video": {".mp4", ".mov", ".mkv", ".mxf", ".avi", ".m4v", ".webm", ".mts"},
    "audio": {".wav", ".mp3", ".m4a", ".aac", ".flac", ".aiff", ".aif", ".ogg"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".heic"},
}

DEFAULT_SETTINGS = {
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "language": None,  # None = autodetect
    "platform": "youtube",
}


def media_kind(path: Path) -> str | None:
    ext = path.suffix.lower()
    for kind, exts in MEDIA_EXT.items():
        if ext in exts:
            return kind
    return None


class Project:
    def __init__(self, name_or_path: str):
        p = Path(name_or_path)
        self.dir = p.resolve() if p.exists() and p.is_dir() else PROJECTS / name_or_path
        if not self.dir.exists():
            raise SystemExit(f"project not found: {self.dir} (create it with `ea new <name>`)")

    @classmethod
    def create(cls, name: str, **settings) -> "Project":
        d = PROJECTS / name
        for sub in ("input", "work", "output"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        cfg = d / "project.json"
        if not cfg.exists():
            data = {"name": name, **DEFAULT_SETTINGS, **{k: v for k, v in settings.items() if v is not None}}
            write_json(cfg, data)
        return cls(str(d))

    @property
    def name(self) -> str:
        return self.dir.name

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    @property
    def settings(self) -> dict:
        return {**DEFAULT_SETTINGS, **read_json(self.path("project.json"), {})}

    def input_files(self) -> list[Path]:
        return sorted(p for p in self.path("input").rglob("*") if p.is_file() and media_kind(p))

    def rel(self, p: Path) -> str:
        """Path stored in json files: relative to the project dir when inside it."""
        p = Path(p).resolve()
        try:  # forward slashes so json written on Windows matches json written on macOS
            return p.relative_to(self.dir).as_posix()
        except ValueError:
            return p.as_posix()

    def abs(self, stored: str) -> Path:
        p = Path(stored)
        return p if p.is_absolute() else (self.dir / p).resolve()


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def slug(path: Path) -> str:
    """Stable id for a media file, used to name derived files."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in Path(path).stem)
