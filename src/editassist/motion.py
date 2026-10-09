"""motion: render Remotion compositions (remotion/src) as transparent ProRes 4444 overlays,
register them in media.json, ready to drop on a V2+ track."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from . import timeline as T
from .generate import register_file
from .project import ROOT, Project, read_json, write_json

REMOTION = ROOT / "remotion"


def render_motion(project: Project, composition: str, props: dict, seconds: float | None = None) -> dict:
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx not found: install Node.js 20+ and run setup")
    if not (REMOTION / "node_modules").exists():
        raise SystemExit("remotion/node_modules missing: run `npm install` inside remotion/ (setup does it)")
    tl = read_json(project.path("timeline.json")) or T.new(project)
    props = {"width": tl["width"], "height": tl["height"], "fps": tl["fps"], **props}
    if composition == "Captions" and "lines" not in props:
        caps = read_json(project.path("work", "captions.json"))
        if not caps:
            raise SystemExit("no work/captions.json: run `ea subtitles <project>` first")
        props["lines"] = caps["lines"]
        props.setdefault("durationInSeconds", T.length(tl))
    if props.get("font"):  # a font the user owns: copied next to the bundled ones, never committed
        src = Path(props.pop("font")).expanduser()
        if not src.is_file():
            raise SystemExit(f"font file not found: {src}")
        dst_font = ROOT / "assets" / "user-fonts" / src.name
        dst_font.parent.mkdir(parents=True, exist_ok=True)
        if not dst_font.exists():
            shutil.copy2(src, dst_font)
        props["fontFile"] = f"user-fonts/{src.name}"
    if seconds:
        props["durationInSeconds"] = seconds
    props.setdefault("durationInSeconds", 5)
    stamp = int(time.time() * 1000)  # two renders in one second overwrote each other
    props_file = project.path("work", "motion", f"{composition}_{stamp}.props.json")
    write_json(props_file, props)
    dst = project.path("work", "motion", f"{composition}_{stamp}.mov")
    cmd = [npx, "remotion", "render", "src/index.ts", composition, str(dst), f"--props={props_file}",
           "--codec=prores", "--prores-profile=4444", "--pixel-format=yuva444p10le", "--image-format=png",
           "--log=error"]
    res = subprocess.run(cmd, cwd=str(REMOTION), capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit("remotion render failed:\n" + "\n".join((res.stderr or res.stdout).strip().splitlines()[-25:]))
    entry = register_file(project, str(dst), kind="motion", note=composition)
    entry["place_on"] = "V2 or higher, start where it should appear; it has alpha"
    return entry
