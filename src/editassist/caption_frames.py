"""Burn-in captions without libass: draw each caption state as a transparent PNG (Pillow) and
play them back through ffmpeg's concat demuxer as ONE overlay input. Works with any ffmpeg
build, including ones without libass/drawtext (current Homebrew bottle, many Windows builds)."""
from __future__ import annotations

import unicodedata
import subprocess
from functools import lru_cache
from pathlib import Path

from .project import ROOT, Project, read_json

# Bundled (SIL OFL) so captions look identical on every machine and OS.
FONTS = {"bold": ROOT / "assets" / "fonts" / "Montserrat-Black.ttf",
         "regular": ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"}


@lru_cache(maxsize=None)
def has_libass() -> bool:
    res = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return any(line.split()[1:2] == ["ass"] for line in res.stdout.splitlines() if len(line.split()) > 1)


def _font(kind: str, size: int, look: dict | None = None):
    from PIL import ImageFont

    look = look or {}
    if look.get("font") and Path(look["font"]).exists():  # the user's own caption font (caption_style.json)
        f = ImageFont.truetype(look["font"], size)
        if look.get("weight"):
            try:  # variable fonts (Inter...): pick the named instance
                f.set_variation_by_name(look["weight"])
            except Exception:  # noqa: BLE001  static font or unknown instance name: keep the default
                pass
        return f
    if FONTS[kind].exists():
        return ImageFont.truetype(str(FONTS[kind]), size)
    return ImageFont.load_default(size)


def caption_look(project: Project) -> dict:
    """work/caption_style.json: the user's caption look for this project (font file, weight, size as %
    of the short side, y centre 0..1 from the top, stroke on/off), written by `ea subtitles --font ...`."""
    return read_json(project.path("work", "caption_style.json"), {}) or {}


def build(project: Project, W: int, H: int, captions_file: str = "work/captions.json") -> Path:
    from PIL import Image, ImageDraw

    caps = read_json(project.path(*captions_file.split("/")))
    if not caps:
        raise SystemExit("no work/captions.json: run `ea subtitles <project>` first")
    style = caps.get("style", "clean")
    look = caption_look(project)
    upper = look.get("upper", style == "bold")
    base = int(min(W, H) * (look.get("size_pct") or (6.0 if style == "bold" else 4.6)) / 100)  # short side
    accent = caps.get("accent", "#FFE500").lstrip("#")
    accent = tuple(int(accent[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    y_center = H * (look.get("y") if look.get("y") is not None else (0.5 if style == "bold" else 0.86))
    out = project.path("work", "caption_frames")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    blank = out / "blank.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)

    events = []  # (start, end, words, active index)
    karaoke = caps.get("karaoke", True)
    for l in caps["lines"]:
        ws = l["words"]
        if not karaoke:
            events.append((l["start"], l["end"], ws, -1))
            continue
        for i, w in enumerate(ws):
            a = w["start"] if i else l["start"]
            b = ws[i + 1]["start"] if i + 1 < len(ws) else l["end"]
            if b > a:
                events.append((a, b, ws, i))

    lines = ["ffconcat version 1.0"]
    t = 0.0
    for n, (a, b, ws, active) in enumerate(events):
        if a - t > 0.001:
            lines += ["file blank.png", f"duration {a - t:.3f}"]
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        toks = [unicodedata.normalize("NFC", x["word"].upper() if upper else x["word"]) for x in ws]
        size = base
        while True:  # shrink long lines until they fit inside 88% of the width
            font = _font("bold" if style == "bold" else "regular", size, look)
            space = d.textlength(" ", font=font)
            widths = [d.textlength(tk, font=font) for tk in toks]
            total = sum(widths) + space * (len(toks) - 1)
            if total <= W * 0.88 or size <= base * 0.5:
                break
            size = int(size * 0.92)
        stroke = max(2, size // 12) if look.get("stroke", True) else 0
        x = (W - total) / 2
        if style == "boxed":
            pad = size * 0.35
            d.rounded_rectangle([x - pad, y_center - size * 0.75, x + total + pad, y_center + size * 0.75],
                                radius=size * 0.25, fill=(0, 0, 0, 170))
        for j, tk in enumerate(toks):
            fill = accent if j == active else (255, 255, 255, 255)
            if look.get("shadow"):
                off = max(2, size // 20)
                d.text((x + off, y_center + off), tk, font=font, fill=(0, 0, 0, 150), anchor="lm")
            d.text((x, y_center), tk, font=font, fill=fill, anchor="lm",
                   stroke_width=0 if style == "boxed" else stroke, stroke_fill=(0, 0, 0, 255))
            x += widths[j] + space
        name = f"c{n:05d}.png"
        img.save(out / name)
        lines += [f"file {name}", f"duration {b - a:.3f}"]
        t = b
    lines += ["file blank.png", "duration 1.000", "file blank.png"]  # last entry needs a trailing file
    lst = out / "captions.ffconcat"
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lst
