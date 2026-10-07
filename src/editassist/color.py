"""color: corrective grade, camera matching and looks, compiled into ONE .cube 3D LUT per media.

A LUT is the one colour format every tool reads: ffmpeg (render), Resolve (auto-applied on import
with `ea export --open`), Premiere (Lumetri > Input LUT), After Effects (Apply Color LUT).

work/color.json  {"<media path>": {"lut": "work/color/<id>.cube", "ops": [...], "stats": {...}}}

Ops, applied in order on RGB 0..1:
  {"op": "gain", "rgb": [r, g, b]}          white balance / channel match
  {"op": "levels", "lo": 0.02, "hi": 0.97}  black / white point to 0.03 .. 0.95
  {"op": "contrast", "amount": 1.1}         around mid grey
  {"op": "saturation", "amount": 1.1}
  {"op": "look", "name": "warm"|"cool"|"punchy"|"film"|"bw"}
  {"op": "lut", "file": "path/to/creative.cube"}   external LUT, sampled trilinearly
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .ingest import media_by_id
from .project import Project, read_json, write_json

SIZE = 33
LOOKS = ("warm", "cool", "punchy", "film", "bw")
LUMA = (0.2126, 0.7152, 0.0722)


def sample_frames(project: Project, sid: str, n: int = 12, width: int = 160):
    """n evenly spaced frames as float RGB arrays (h, w, 3) in 0..1."""
    import numpy as np

    m = media_by_id(project)[sid]
    # the proxy holds the same picture and decodes ~50x faster than 4K 10-bit originals
    src, dur = str(project.abs(m.get("proxy") or m["path"])), m["duration"] or 1
    h = int(round(width * m["height"] / m["width"] / 2) * 2)
    frames = []
    for k in range(n):
        t = dur * (k + 0.5) / n
        res = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                              "-vf", f"scale={width}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True)
        if res.returncode == 0 and len(res.stdout) == width * h * 3:
            frames.append(np.frombuffer(res.stdout, np.uint8).reshape(h, width, 3) / 255.0)
    if not frames:
        raise SystemExit(f"could not read frames from {m['path']}")
    return np.stack(frames)


def stats(px) -> dict:
    import numpy as np

    flat = px.reshape(-1, 3)
    luma = flat @ np.array(LUMA)
    mid = (luma > 0.08) & (luma < 0.92)  # ignore clipped pixels for balance
    base = flat[mid] if mid.sum() > 100 else flat
    return {"mean": [round(float(v), 4) for v in base.mean(0)],
            "luma_mean": round(float(luma.mean()), 4), "luma_std": round(float(luma.std()), 4),
            "p1": round(float(np.percentile(luma, 1)), 4), "p99": round(float(np.percentile(luma, 99)), 4),
            "sat": round(float((flat.max(1) - flat.min(1)).mean()), 4)}


def auto_ops(s: dict, strength: float = 1.0) -> list[dict]:
    """Grey-world balance + levels; gentle by design (it's a starting grade, not a look)."""
    mean = s["mean"]
    g = sum(mean) / 3
    gain = [min(max(1 + strength * (g / max(c, 1e-3) - 1), 0.85), 1.18) for c in mean]
    lo = min(max(s["p1"] - 0.02, 0.0), 0.12) * strength
    hi = max(min(s["p99"] + 0.02, 1.0), 0.8)
    hi = 1 - (1 - hi) * strength
    return [{"op": "gain", "rgb": [round(v, 4) for v in gain]}, {"op": "levels", "lo": round(lo, 4), "hi": round(hi, 4)}]


def match_ops(ref: dict, other: dict) -> list[dict]:
    """Make `other` look like `ref`: channel means and luma contrast."""
    gain = [min(max(r / max(o, 1e-3), 0.75), 1.33) for r, o in zip(ref["mean"], other["mean"])]
    contrast = min(max(ref["luma_std"] / max(other["luma_std"], 1e-3), 0.7), 1.4)
    sat = min(max(ref["sat"] / max(other["sat"], 1e-3), 0.7), 1.4)
    return [{"op": "gain", "rgb": [round(v, 4) for v in gain]},
            {"op": "contrast", "amount": round(contrast, 4)}, {"op": "saturation", "amount": round(sat, 4)}]


# --- LUT math ----------------------------------------------------------------------------------

def read_cube(path: Path):
    import numpy as np

    size, rows = None, []
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("LUT_3D_SIZE"):
            size = int(line.split()[1])
        elif line[0].isdigit() or line[0] in "-.":
            rows.append([float(x) for x in line.split()[:3]])
    if not size or len(rows) != size ** 3:
        raise SystemExit(f"{path}: not a 3D .cube LUT")
    # .cube order: red changes fastest -> index [b, g, r]
    return np.array(rows).reshape(size, size, size, 3)


def sample_cube(lut, rgb):
    """Trilinear lookup of rgb (..., 3) in a [b, g, r, 3] cube."""
    import numpy as np

    n = lut.shape[0] - 1
    p = np.clip(rgb, 0, 1) * n
    i0 = np.floor(p).astype(int)
    i1 = np.minimum(i0 + 1, n)
    f = p - i0
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                b = i1[..., 2] if db else i0[..., 2]
                g = i1[..., 1] if dg else i0[..., 1]
                r = i1[..., 0] if dr else i0[..., 0]
                w = ((f[..., 2] if db else 1 - f[..., 2]) * (f[..., 1] if dg else 1 - f[..., 1])
                     * (f[..., 0] if dr else 1 - f[..., 0]))
                out = out + lut[b, g, r] * w[..., None]
    return out


def apply_ops(rgb, ops: list[dict], project: Project | None = None):
    import numpy as np

    x = rgb.copy()
    lum = lambda a: (a @ np.array(LUMA))[..., None]
    for o in ops:
        k = o["op"]
        if k == "gain":
            x = x * np.array(o["rgb"])
        elif k == "levels":
            x = (x - o["lo"]) / max(o["hi"] - o["lo"], 1e-3) * 0.92 + 0.03
        elif k == "contrast":
            x = (x - 0.45) * o["amount"] + 0.45
        elif k == "saturation":
            y = lum(x)
            x = y + (x - y) * o["amount"]
        elif k == "look":
            name = o["name"]
            if name == "warm":
                x = x * np.array([1.05, 1.0, 0.93])
            elif name == "cool":
                x = x * np.array([0.94, 1.0, 1.06])
            elif name == "punchy":
                x = (x - 0.45) * 1.15 + 0.45
                y = lum(x); x = y + (x - y) * 1.18
            elif name == "film":
                x = 0.04 + x * 0.92  # lifted blacks, softer whites
                y = lum(x)
                x = x + np.clip(0.5 - y, 0, 1) * np.array([-0.02, 0.01, 0.03])  # teal shadows
                x = x + np.clip(y - 0.5, 0, 1) * np.array([0.04, 0.01, -0.03])  # warm highlights
                y = lum(x); x = y + (x - y) * 0.9
            elif name == "bw":
                x = np.repeat(lum(x), 3, axis=-1)
            else:
                raise SystemExit(f"unknown look {name!r}; one of {LOOKS}")
        elif k == "lut":
            path = project.abs(o["file"]) if project else Path(o["file"])
            x = sample_cube(read_cube(path), np.clip(x, 0, 1))
        x = np.clip(x, 0, 1)
    return x


def write_lut(path: Path, ops: list[dict], project: Project | None = None, title: str = "editassist") -> Path:
    import numpy as np

    v = np.linspace(0, 1, SIZE)
    b, g, r = np.meshgrid(v, v, v, indexing="ij")  # r fastest when flattened
    grid = np.stack([r, g, b], axis=-1).reshape(-1, 3)
    out = apply_ops(grid, ops, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {SIZE}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    lines += [f"{a:.6f} {bb:.6f} {c:.6f}" for a, bb, c in out]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --- commands ----------------------------------------------------------------------------------

def _video_ids(project: Project, only: list[str] | None) -> list[str]:
    return [k for k, m in media_by_id(project).items()
            if m.get("kind") == "video" and not m.get("derived") and (not only or k in only)]


def grade(project: Project, only: list[str] | None = None, auto: bool = False, match: str | None = None,
          look: str | None = None, lut: str | None = None, strength: float = 1.0, reset: bool = False) -> dict:
    catalog = media_by_id(project)
    grades = read_json(project.path("work", "color.json"), {}) or {}
    ids = _video_ids(project, only)
    unknown = sorted(set(only or []) - set(ids))
    if unknown:  # a shell that doesn't split "$ids" passed one long id: say so instead of grading nothing
        raise SystemExit(f"no video media with id: {', '.join(unknown)} (ids are in work/media.json)")
    ref_stats = stats(sample_frames(project, match)) if match else None
    out = {}
    for sid in ids:
        path = catalog[sid]["path"]
        if reset:
            grades.pop(path, None)
            out[sid] = "reset"
            continue
        st = stats(sample_frames(project, sid)) if (auto or match) else None  # LUT/look alone need no analysis
        ops = []
        if auto and catalog[sid].get("log") and not lut:
            out.setdefault("warnings", []).append(
                f"{sid} is {catalog[sid].get('gamma')} (log): auto balance on log is meaningless; "
                "pass --lut with a log-to-Rec709 conversion LUT")
        if auto:
            ops += auto_ops(st, strength)
        if match and sid != match:
            ops += match_ops(ref_stats, st)
        if lut:
            ops.append({"op": "lut", "file": project.rel(Path(lut).resolve())})
        if look:
            ops.append({"op": "look", "name": look})
        if not ops:
            out[sid] = {"stats": st}
            continue
        cube = project.path("work", "color", f"{sid}.cube")
        write_lut(cube, ops, project, title=f"editassist {sid}")
        grades[path] = {"lut": project.rel(cube), "ops": ops, "stats": st}
        out[sid] = {"lut": project.rel(cube), "ops": ops}
    write_json(project.path("work", "color.json"), grades)
    return out


def compare(project: Project, sid: str, t: float | None = None) -> str:
    """Before/after still for one media (left original, right graded) to look at."""
    from PIL import Image

    import numpy as np

    m = media_by_id(project)[sid]
    g = (read_json(project.path("work", "color.json"), {}) or {}).get(m["path"])
    if not g:
        raise SystemExit(f"{sid} has no grade yet")
    t = t if t is not None else (m["duration"] or 1) / 2
    res = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(project.abs(m["path"])), "-frames:v", "1",
                          "-vf", "scale=640:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    h = len(res.stdout) // (640 * 3)
    a = np.frombuffer(res.stdout, np.uint8).reshape(h, 640, 3) / 255.0
    b = sample_cube(read_cube(project.abs(g["lut"])), a)
    img = np.concatenate([a, b], axis=1)
    dst = project.path("work", "color", f"{sid}_compare.jpg")
    Image.fromarray((img * 255).astype("uint8")).save(dst, quality=88)
    return project.rel(dst)
