"""scenes: shot detection + keyframes the model looks at to build the visual index.

work/scenes/<id>.json          [{"index","start","end","frame": "work/frames/<id>/s000.jpg"}]
work/frames/<id>/contact_NN.jpg  labeled grids of keyframes (20 per sheet) for one-glance review
work/visual_index.json         written by the model (see the visual-index skill), not by this code
"""
from __future__ import annotations

import re

from .ingest import media_by_id
from .media import frame_at, run
from .project import Project, write_json

SHEET_COLS, SHEET_ROWS, THUMB_W = 5, 4, 320


def cut_times(src: str, threshold: float) -> list[float]:
    """Shot changes via ffmpeg's scene score (0..1) on a downscaled stream: no extra libraries."""
    res = run(["ffmpeg", "-hide_banner", "-v", "info", "-i", src, "-an", "-vf",
               f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"])
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", res.stderr)]


def detect(project: Project, threshold: float = 0.3, min_scene: float = 1.0,
           only: list[str] | None = None) -> dict:
    out = {}
    for sid, m in media_by_id(project).items():
        if (only and sid not in only) or m.get("kind") != "video" or m.get("derived"):
            continue
        src = project.abs(m["path"])
        bounds = [0.0]
        for t in cut_times(str(src), threshold):
            if t - bounds[-1] >= min_scene:
                bounds.append(t)
        ranges = list(zip(bounds, bounds[1:] + [m["duration"]]))
        items = []
        for i, (a, b) in enumerate(ranges):
            jpg = project.path("work", "frames", sid, f"s{i:03d}.jpg")
            frame_at(src, a + (b - a) / 2, jpg, width=480)
            items.append({"index": i, "start": round(a, 3), "end": round(b, 3), "frame": project.rel(jpg)})
        write_json(project.path("work", "scenes", f"{sid}.json"), items)
        contact_sheets(project, sid, items)
        out[sid] = len(items)
    return out


def contact_sheets(project: Project, sid: str, items: list[dict]) -> list[str]:
    from PIL import Image, ImageDraw, ImageFont

    from .project import ROOT

    font_path = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"
    font = ImageFont.truetype(str(font_path), 15) if font_path.exists() else ImageFont.load_default(15)
    per = SHEET_COLS * SHEET_ROWS
    sheets = []
    for page in range(0, len(items), per):
        chunk = items[page:page + per]
        thumbs = []
        for it in chunk:
            img = Image.open(project.abs(it["frame"])).convert("RGB")
            img = img.resize((THUMB_W, int(img.height * THUMB_W / img.width)))
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, THUMB_W, 22], fill=(0, 0, 0))
            d.text((6, 3), f"#{it['index']}  {it['start']:.1f}-{it['end']:.1f}s", font=font, fill=(255, 255, 255))
            thumbs.append(img)
        th = max(t.height for t in thumbs)
        rows = -(-len(thumbs) // SHEET_COLS)
        sheet = Image.new("RGB", (SHEET_COLS * THUMB_W, rows * th))
        for i, t in enumerate(thumbs):
            r, c = divmod(i, SHEET_COLS)
            sheet.paste(t, (c * THUMB_W, r * th))
        dst = project.path("work", "frames", sid, f"contact_{page // per:02d}.jpg")
        sheet.save(dst, quality=85)
        sheets.append(project.rel(dst))
    return sheets
