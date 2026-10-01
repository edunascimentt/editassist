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
MEMORY = ROOT / "memory"

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
