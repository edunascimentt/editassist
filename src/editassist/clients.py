"""clients: per-client preferences in the user's private editing memory.

<memory>/clients/<slug>/preferences.md   house style and taste of ONE client (overrides the general
                                          <memory>/preferences.md on that client's projects)
<memory>/clients/<slug>/...              anything else about them (logo path notes, music notes)

A project belongs to a client through `"client": "<slug>"` in project.json (`ea new <p> --client`,
`ea client set`); without it, a client whose slug is part of the project name is assumed
("acme-carro-cinza" -> acme). Feedback during an edit goes to the client's file when it is
about that client (their brand, format, music, people, what they asked for) and to the general file
when it is about editing itself (see the style-profile skill).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

from . import project as P
from .project import ROOT, Project, memory_dir, read_json, write_json

TEMPLATE = ROOT / "memory.template" / "clients" / "_template" / "preferences.md"


def client_slug(name: str) -> str:
    """"Ana Souza" -> "ana-souza" (accents dropped, so the folder name is the same on every OS)."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if not s:
        raise SystemExit(f"client name has no letters or digits: {name!r}")
    return s


def clients_dir() -> Path:
    return memory_dir() / "clients"


def client_dir(slug: str) -> Path:
    return clients_dir() / slug


def all_clients() -> list[str]:
    d = clients_dir()
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith("_")) if d.is_dir() else []


def display_name(slug: str) -> str:
    f = client_dir(slug) / "preferences.md"
    if f.exists():
        m = re.match(r"#\s*Client:\s*(.+)", f.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip()
    return slug


def create(name: str) -> dict:
    """Make <memory>/clients/<slug>/preferences.md from the template; never overwrites."""
    slug = client_slug(name)
    f = client_dir(slug) / "preferences.md"
    created = not f.exists()
    if created:
        f.parent.mkdir(parents=True, exist_ok=True)
        body = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.exists() else "# Client: {name}\n"
        f.write_text(body.replace("{name}", name).replace("{date}", date.today().isoformat()), encoding="utf-8")
    return {"client": slug, "name": display_name(slug), "preferences": str(f), "created": created}


def client_of(project: str | Project | None) -> str | None:
    """The project's client slug: project.json "client", else a known client whose slug appears in the
    project name (longest match wins), else None."""
    if project is None:
        return None
    name = project.name if isinstance(project, Project) else str(project)
    cfg = (project.dir if isinstance(project, Project) else P.PROJECTS / name) / "project.json"
    explicit = (read_json(cfg, {}) or {}).get("client")
    if explicit:
        return client_slug(explicit)
    hits = [c for c in all_clients() if c in client_slug(name)]
    return max(hits, key=len) if hits else None


def assign(project: Project, name: str) -> dict:
    """Tie a project to a client (creating the client folder when new)."""
    res = create(name)
    cfg = project.path("project.json")
    data = read_json(cfg, {}) or {}
    data["client"] = res["client"]
    write_json(cfg, data)
    return {"project": project.name, **res}


def show(project: Project) -> dict:
    """Which preference files apply to this project, in reading order (later overrides earlier)."""
    general = memory_dir() / "preferences.md"
    slug = client_of(project)
    out = {"project": project.name, "client": slug,
           "how": "client file overrides the general one on this project",
           "read": [str(general)]}
    if slug:
        d = client_dir(slug)
        out["client_name"] = display_name(slug)
        out["read"] += [str(f) for f in sorted(d.rglob("*.md"))] if d.is_dir() else []
        if not d.is_dir():
            out["missing"] = f"client folder not created yet: `uv run ea client new \"{slug}\"`"
        source = "project.json" if (read_json(project.path("project.json"), {}) or {}).get("client") else "project name"
        out["matched_by"] = source
    else:
        out["hint"] = "no client: `uv run ea client set <project> \"<Client Name>\"` if this is client work"
    return out


def listing() -> dict:
    projects = {}
    if P.PROJECTS.is_dir():
        for d in sorted(P.PROJECTS.iterdir()):
            if (d / "project.json").exists():
                c = client_of(Project(str(d)))
                if c:
                    projects.setdefault(c, []).append(d.name)
    return {"dir": str(clients_dir()),
            "clients": [{"client": c, "name": display_name(c), "preferences": str(client_dir(c) / "preferences.md"),
                         "projects": projects.get(c, [])} for c in all_clients()]}
