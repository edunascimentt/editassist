"""thumbnail: find strong frames (sharp, well exposed, big face), then compose a thumbnail with
bold text on the side away from the face. Bundled Montserrat, so it looks the same everywhere."""
from __future__ import annotations

import subprocess
import textwrap

from . import timeline as T
from .project import ROOT, Project, read_json

SIZES = {"16:9": (1280, 720), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def _frame(path: str, t: float, width: int = 1280):
    import numpy as np

    res = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                          "-vf", f"scale={width}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if res.returncode or not res.stdout:
        return None
    h = len(res.stdout) // (width * 3)
    return np.frombuffer(res.stdout, np.uint8).reshape(h, width, 3)


def _faces(img):
    import os

    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    import cv2

    from .reformat import YUNET

    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), 0.7)
    _, faces = det.detect(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return [] if faces is None else [tuple(map(float, f[:4])) for f in faces]


def score(img) -> dict:
    import numpy as np

    g = img.mean(2)
    lap = np.abs(g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    sharp = float(lap.var())
    bright = float(g.mean() / 255)
    faces = _faces(img)
    face = max((f[2] * f[3] for f in faces), default=0) / (img.shape[0] * img.shape[1])
    s = min(sharp / 400, 1.5) + (1 - abs(bright - 0.5) * 2) + min(face * 8, 1.5)
    return {"score": round(s, 3), "sharp": round(sharp, 1), "bright": round(bright, 3), "face": round(face, 4), "faces": faces}


def candidates(project: Project, n: int = 12, per_clip: int = 3) -> dict:
    from PIL import Image, ImageDraw, ImageFont

    tl = T.load(project)
    cat = {m["path"]: m for m in (read_json(project.path("work", "media.json"), {}) or {}).values()}
    pool = []
    for c in T.track(tl, "V1")["clips"]:
        m = cat.get(c["media"])
        if not m or m.get("kind") != "video":
            continue
        for k in range(per_clip):
            t = c["in"] + (c["out"] - c["in"]) * (k + 0.5) / per_clip
            img = _frame(str(project.abs(c["media"])), t, 640)
            if img is not None:
                pool.append({"media": c["media"], "t": round(t, 3), "timeline": round(c["start"] + (t - c["in"]), 3),
                             **score(img), "_img": img})
    pool.sort(key=lambda x: -x["score"])
    picked = []
    for p in pool:  # keep them apart in time so the sheet shows variety
        if all(abs(p["timeline"] - q["timeline"]) > 2 for q in picked):
            picked.append(p)
        if len(picked) >= n:
            break
    out_dir = project.path("work", "thumbs")
    out_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"), 18)
    tiles = []
    for i, p in enumerate(picked):
        im = Image.fromarray(p.pop("_img")).resize((320, 180))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 320, 24], fill=(0, 0, 0))
        d.text((6, 3), f"#{i}  {p['timeline']:.1f}s  score {p['score']:.2f}", font=font, fill=(255, 255, 255))
        tiles.append(im)
        p.pop("faces", None)
        p["index"] = i
    for p in pool:
        p.pop("_img", None)
    cols = 4
    sheet = Image.new("RGB", (cols * 320, -(-len(tiles) // cols) * 180))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 320, (i // cols) * 180))
    sheet.save(out_dir / "candidates.jpg", quality=85)
    from .project import write_json
    write_json(out_dir / "candidates.json", picked)
    return {"look_at": project.rel(out_dir / "candidates.jpg"), "candidates": picked}


def compose(project: Project, text: str, pick: int | None = None, media: str | None = None, t: float | None = None,
            image: str | None = None, aspect: str = "16:9", accent: str = "#FFE500", out: str | None = None) -> dict:
    """Text: words wrapped in *asterisks* get the accent colour. Background: candidate #pick, a media
    frame (media id/path + source time), or any image (e.g. generated with the higgsfield skill)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    W, H = SIZES[aspect]
    if image:
        bg = Image.open(project.abs(image)).convert("RGB")
    else:
        if pick is not None:
            c = (read_json(project.path("work", "thumbs", "candidates.json")) or [])[pick]
            media, t = c["media"], c["t"]
        cat = read_json(project.path("work", "media.json"), {}) or {}
        path = cat[media]["path"] if media in cat else media
        arr = _frame(str(project.abs(path)), t or 0.0, 1920)
        if arr is None:
            raise SystemExit("could not read that frame")
        bg = Image.fromarray(arr)
    # fill-crop; with a face, zoom in a little and put the face on the third away from the text
    faces = _faces(np.array(bg))
    big = max(faces, key=lambda f: f[2] * f[3]) if faces else None
    fx = (big[0] + big[2] / 2) / bg.width if big else 0.5
    fy = (big[1] + big[3] / 2) / bg.height if big else 0.5
    text_side = "right" if fx < 0.5 else "left"
    s = max(W / bg.width, H / bg.height) * (1.3 if big and aspect == "16:9" else 1.0)
    bg = bg.resize((int(bg.width * s + 0.5), int(bg.height * s + 0.5)))
    target_x = (0.70 if text_side == "left" else 0.30) if aspect == "16:9" else 0.5
    x0 = int(min(max(fx * bg.width - target_x * W, 0), bg.width - W))
    y0 = int(min(max(fy * bg.height - 0.45 * H, 0), bg.height - H))
    bg = bg.crop((x0, y0, x0 + W, y0 + H))
    # readability: gradient on the text side + slight contrast boost
    grad = Image.new("L", (W, H))
    g = np.linspace(200, 0, W // 2 + 1).astype("uint8") if text_side == "left" else np.linspace(0, 200, W // 2 + 1).astype("uint8")
    full = np.zeros((H, W), "uint8")
    if text_side == "left":
        full[:, : W // 2 + 1] = g
    else:
        full[:, W - W // 2 - 1:] = g
    grad = Image.fromarray(full).filter(ImageFilter.GaussianBlur(20))
    bg = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), bg, grad)
    d = ImageDraw.Draw(bg)
    box_w = int(W * (0.52 if aspect == "16:9" else 0.86))
    size = int(H * (0.16 if aspect == "16:9" else 0.075))
    font_path = ROOT / "assets" / "fonts" / "Montserrat-Black.ttf"
    words = text.upper().split()
    while size > 20:  # shrink until it fits the box in <= 3 lines
        font = ImageFont.truetype(str(font_path), size)
        avg = d.textlength("M", font=font) * 0.75
        lines = textwrap.wrap(" ".join(words), width=max(4, int(box_w / avg)))
        if len(lines) <= 3 and all(d.textlength(l.replace("*", ""), font=font) <= box_w for l in lines):
            break
        size -= 4
    lh = int(size * 1.08)
    y = (H - lh * len(lines)) // 2 if aspect == "16:9" else int(H * 0.12)
    acc = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    margin = int(W * 0.05)
    for line in lines:
        lw = d.textlength(line.replace("*", ""), font=font)
        x = margin if text_side == "left" or aspect != "16:9" else W - margin - lw
        if aspect != "16:9":
            x = (W - lw) / 2
        hot = False
        for tok in line.split(" "):
            raw = tok.replace("*", "")
            if tok.startswith("*"):
                hot = True
            d.text((x, y), raw, font=font, fill=acc if hot else (255, 255, 255),
                   stroke_width=max(3, size // 14), stroke_fill=(0, 0, 0))
            if tok.endswith("*"):
                hot = False
            x += d.textlength(raw + " ", font=font)
        y += lh
    tl = read_json(project.path("timeline.json")) or {"name": project.name}
    dst = project.abs(out) if out else project.path("output", f"{tl['name']}_thumb.jpg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    q = 92
    bg.save(dst, quality=q)
    while dst.stat().st_size > 2_000_000 and q > 60:  # YouTube limit is 2 MB
        q -= 8
        bg.save(dst, quality=q)
    return {"thumbnail": project.rel(dst), "size": f"{W}x{H}", "kb": dst.stat().st_size // 1024,
            "text_side": text_side}
