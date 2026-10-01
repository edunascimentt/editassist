"""Shared fixtures: synthetic media (ffmpeg lavfi, no speech engine needed) and a fake word-level
transcript, so the whole pipeline runs the same on macOS, Windows and Linux CI without Whisper."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# "speech": 440 Hz tone bursts where the fake words are, silence between
WORDS = [("Olá", 0.5, 0.9), ("pessoal.", 0.95, 1.5),
         ("Hoje", 3.0, 3.3), ("vamos", 3.35, 3.7), ("editar", 3.75, 4.2), ("vídeo.", 4.25, 4.8),
         ("Hum", 6.0, 6.4),
         ("Primeiro", 7.5, 8.0), ("o", 8.05, 8.15), ("material", 8.2, 8.8), ("bruto.", 8.85, 9.4)]


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    d = tmp_path_factory.mktemp("media")
    expr = "+".join(f"between(t,{a},{b})" for _, a, b in WORDS)
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=10", "-f", "lavfi",
       "-i", f"aevalsrc='0.3*sin(2*PI*440*t)*({expr})':s=48000:d=10",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "cam_a.mp4"))
    # second camera: same sound, started 1.5 s later (cam_b time = cam_a time - 1.5)
    ff("-ss", "1.5", "-i", str(d / "cam_a.mp4"), "-f", "lavfi", "-i", "smptebars=s=640x360:r=30",
       "-map", "1:v", "-map", "0:a", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
       str(d / "cam_b.mp4"))
    # music: 120 bpm kick, 20 s
    ff("-f", "lavfi", "-i", "aevalsrc='0.6*sin(2*PI*55*t)*exp(-25*mod(t,0.5))*(1+0.8*eq(mod(floor(t/0.5),4),0))':s=44100:d=20",
       str(d / "music_120.wav"))
    return d


def fake_transcript(sid: str, words=WORDS, offset: float = 0.0) -> dict:
    segs, cur = [], []
    for w, a, b in words:
        cur.append({"start": a + offset, "end": b + offset, "word": w, "prob": 0.99})
        if w.endswith(".") or w == "Hum":
            segs.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["word"] for x in cur), "words": cur})
            cur = []
    return {"media": sid, "language": "pt", "model": "fake", "segments": segs}


@pytest.fixture()
def project(tmp_path, media_dir, monkeypatch):
    import editassist.project as P

    monkeypatch.setattr(P, "PROJECTS", tmp_path)
    pr = P.Project.create("t", fps=30, width=640, height=360, language="pt")
    for f in ("cam_a.mp4", "cam_b.mp4", "music_120.wav"):
        shutil.copy(media_dir / f, pr.path("input", f))
    from editassist.ingest import ingest

    ingest(pr)
    tdir = pr.path("work", "transcripts")
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "cam_a.json").write_text(json.dumps(fake_transcript("cam_a")), encoding="utf-8")
    return pr
