"""ffprobe/ffmpeg helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def need(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise SystemExit(f"`{binary}` not found on PATH. Run ./setup.sh")
    return path


def run(cmd: list[str], quiet: bool = True, cwd=None) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-15:])
        raise SystemExit(f"command failed: {' '.join(cmd[:6])} ...\n{tail}")
    if not quiet:
        print(res.stdout)
    return res


def probe(path: Path) -> dict:
    """Normalized media info: duration, fps, size, audio presence."""
    need("ffprobe")
    res = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    data = json.loads(res.stdout)
    v = next((s for s in data["streams"] if s["codec_type"] == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    info = {
        "duration": float(data["format"].get("duration") or 0),
        "has_video": v is not None,
        "has_audio": a is not None,
    }
    if v:
        num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
        rot = 0
        for sd in v.get("side_data_list", []):
            if "rotation" in sd:
                rot = int(sd["rotation"])
        w, h = int(v["width"]), int(v["height"])
        if abs(rot) in (90, 270):
            w, h = h, w
        info.update(width=w, height=h, fps=round(fps, 3), vcodec=v.get("codec_name"))
    if a:
        info.update(sample_rate=int(a.get("sample_rate", 48000)), channels=a.get("channels"), acodec=a.get("codec_name"))
    return info


def extract_audio(src: Path, dst: Path, rate: int = 16000) -> Path:
    """Mono wav for analysis (transcription, silence detection)."""
    need("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(dst)])
    return dst


def frame_at(src: Path, t: float, dst: Path, width: int = 640) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-q:v", "4", str(dst)])
    return dst
