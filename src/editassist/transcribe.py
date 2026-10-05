"""transcribe: word-level transcripts with faster-whisper.

Output per clip: work/transcripts/<id>.json
  {"language": "pt", "segments": [{"start","end","text","words":[{"start","end","word","prob"}]}]}
plus a plain .txt with timestamps that is cheap for the model to read.
"""
from __future__ import annotations

import os
import platform

from .ingest import media_by_id
from .project import Project, read_json, write_json


def _model(name: str):
    from faster_whisper import WhisperModel

    import ctranslate2

    # NVIDIA GPU (Windows/Linux) -> float16 on CUDA; everything else (incl. Apple Silicon, where
    # CTranslate2 has no Metal backend) -> int8 on CPU, which is several times faster than float32.
    cuda = platform.system() != "Darwin" and ctranslate2.get_cuda_device_count() > 0
    device = os.environ.get("EA_WHISPER_DEVICE") or ("cuda" if cuda else "cpu")
    compute = os.environ.get("EA_WHISPER_COMPUTE") or ("float16" if device == "cuda" else "int8")
    return WhisperModel(name, device=device, compute_type=compute)


def _load_wav(path):
    """16 kHz mono s16 wav (made by ingest) -> float32 array. Passing an array instead of a path
    keeps faster-whisper from decoding through PyAV, whose API keeps shifting between releases."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{path}: expected 16 kHz mono 16-bit wav, re-run `ea ingest`")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def uncovered_speech(audio, segs: list[dict], min_len: float = 1.0) -> list[tuple[float, float]]:
    """Loud stretches with no transcribed word: Whisper sometimes drops a whole sentence."""
    import numpy as np

    hop = 800  # 50 ms at 16 kHz
    n = len(audio) // hop
    if not n:
        return []
    rms = np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9
    db = 20 * np.log10(rms)
    loud = db > max(np.percentile(db, 90) - 25, -45)
    k = 8  # bridge the short pauses between words (0.4 s)
    loud = np.convolve(loud.astype(float), np.ones(k), mode="same") > 0
    covered = np.zeros(n, bool)
    for sg in segs:
        for w in sg["words"] or [{"start": sg["start"], "end": sg["end"]}]:
            covered[max(0, int((w["start"] - 0.3) * 20)):int((w["end"] + 0.3) * 20) + 1] = True
    gaps, start = [], None
    for i, v in enumerate(loud & ~covered):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if (i - start) / 20 >= min_len:
                gaps.append((round(start / 20, 2), round(i / 20, 2)))
            start = None
    if start is not None and (n - start) / 20 >= min_len:
        gaps.append((round(start / 20, 2), round(n / 20, 2)))
    return gaps


def fmt_ts(t: float) -> str:
    m, s = divmod(t, 60)
    h, m = divmod(int(m), 60)
    return f"{h:02d}:{m:02d}:{s:06.3f}" if h else f"{m:02d}:{s:06.3f}"


def transcribe(project: Project, model: str | None = None, language: str | None = None,
               only: list[str] | None = None, force: bool = False) -> list[str]:
    catalog = media_by_id(project)
    language = language or project.settings.get("language")
    model = model or os.environ.get("EA_WHISPER_MODEL", "large-v3-turbo")
    whisper = None
    done = []
    for sid, m in catalog.items():
        if only and sid not in only:
            continue
        if not m.get("analysis_audio"):
            continue
        out = project.path("work", "transcripts", f"{sid}.json")
        if out.exists() and not force:
            done.append(sid)
            continue
        whisper = whisper or _model(model)
        print(f"transcribing {sid} ({m['duration']:.0f}s) with {model} ...", flush=True)
        audio = _load_wav(project.abs(m["analysis_audio"]))
        segments, info = whisper.transcribe(
            audio, language=language, word_timestamps=True,
            vad_filter=True, condition_on_previous_text=False,
        )
        segs = []
        for s in segments:
            segs.append({
                "start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip(),
                           "prob": round(w.probability, 3)} for w in (s.words or [])],
            })
        missed = uncovered_speech(audio, segs)
        if missed:
            print(f"  warning {sid}: speech-like audio with no words at {missed}; "
                  f"listen there or re-run with --force --model large-v3", flush=True)
        write_json(out, {"media": sid, "language": info.language, "model": model, "segments": segs,
                         "possibly_missed": missed})
        lines = [f"[{fmt_ts(s['start'])} - {fmt_ts(s['end'])}] {s['text']}" for s in segs]
        out.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        done.append(sid)
    return done


def load_transcript(project: Project, sid: str) -> dict | None:
    return read_json(project.path("work", "transcripts", f"{sid}.json"))


def words(project: Project, sid: str) -> list[dict]:
    t = load_transcript(project, sid)
    return [w for s in (t or {}).get("segments", []) for w in s["words"]]
