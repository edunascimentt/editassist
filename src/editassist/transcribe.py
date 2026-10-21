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


def _tok(w: str) -> str:
    return "".join(ch for ch in w.casefold() if ch.isalnum())


def hallucinated(seg: dict, hotwords: str | None) -> bool:
    """Whisper on music or crowd noise (party clips, 2026-10-13): near-zero-confidence words ("Aero",
    "Música", p < 0.15), or the dictionary's own hotwords recited ("Gael Gael Gael", "Balneário Camboriú
    Carvalho Agrestes Vavá DOMCast" over a DJ set, p ~0.1-0.4). Real speech that names a dictionary term
    is heard with confidence, so it stays."""
    ws = seg.get("words") or []
    if not ws:
        return False
    p = sum(w.get("prob", 1.0) for w in ws) / len(ws)
    if p < 0.15:
        return True
    hot = {_tok(h) for h in (hotwords or "").split()} - {""}
    toks = [_tok(w["word"]) for w in ws if _tok(w["word"])]
    return bool(hot and toks) and p < 0.5 and sum(t in hot for t in toks) / len(toks) >= 0.6


def windows(duration: float, head: float | None = None, tail: float | None = None,
            spans: list[tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    """Source-time stretches to transcribe: the whole clip, or only its first `head` and last `tail`
    seconds and/or given (start, end) spans (finding where a long recording really starts, ends or
    could be split without transcribing hours). Overlapping stretches are merged."""
    if not head and not tail and not spans:
        return [(0.0, duration)]
    out = [(max(0.0, float(a)), min(float(b), duration)) for a, b in spans or [] if a < duration]
    if head:
        out.append((0.0, min(head, duration)))
    if tail:
        out.append((max(0.0, duration - tail), duration))
    merged: list[tuple[float, float]] = []
    for a, b in sorted(out):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def missing(want: list[tuple[float, float]], have: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Parts of `want` not already inside `have` (stretches still to transcribe)."""
    out = []
    for a, b in want:
        cur = a
        for x, y in sorted(have):
            if y <= cur or x >= b:
                continue
            if x > cur:
                out.append((cur, x))
            cur = max(cur, y)
        if b - cur > 0.5:
            out.append((cur, b))
    return out


def fmt_ts(t: float) -> str:
    m, s = divmod(t, 60)
    h, m = divmod(int(m), 60)
    return f"{h:02d}:{m:02d}:{s:06.3f}" if h else f"{m:02d}:{s:06.3f}"


def transcribe(project: Project, model: str | None = None, language: str | None = None,
               only: list[str] | None = None, force: bool = False,
               head: float | None = None, tail: float | None = None,
               spans: list[tuple[float, float]] | None = None) -> list[str]:
    catalog = media_by_id(project)
    language = language or project.settings.get("language")
    model = model or os.environ.get("EA_WHISPER_MODEL", "large-v3-turbo")
    whisper = None
    done = []
    from . import vocab

    dictionary = vocab.load(project.dir.name)
    hot = vocab.hotwords(project.dir.name)
    for sid, m in catalog.items():
        if only and sid not in only:
            continue
        if not m.get("analysis_audio"):
            continue
        out = project.path("work", "transcripts", f"{sid}.json")
        prev = read_json(out) if out.exists() and not force else None
        if prev is not None and not prev.get("windows"):
            done.append(sid)  # a whole transcript already covers any window
            continue
        dur = m["duration"]
        spans_ = windows(dur, head, tail, spans)
        whole = spans_ == [(0.0, dur)]
        todo = spans_
        if prev is not None:  # partial transcript: add only the stretches it lacks
            have = [tuple(w) for w in prev["windows"]]
            todo = missing(spans_, have)
            if not todo:
                done.append(sid)
                continue
            whole = False
            spans_ = windows(dur, spans=have + todo)
        whisper = whisper or _model(model)
        audio = _load_wav(project.abs(m["analysis_audio"]))
        part = "" if whole else " (" + ", ".join(f"{fmt_ts(a)}-{fmt_ts(b)}" for a, b in todo) + ")"
        print(f"transcribing {sid} ({dur:.0f}s){part} with {model} ...", flush=True)
        segs = list(prev["segments"]) if prev else []
        missed = [tuple(x) for x in prev.get("possibly_missed", [])] if prev else []
        lang = language
        dropped = []
        for a, b in todo:  # times stay in source seconds whatever the window
            chunk = audio[int(a * 16000):int(b * 16000)]
            segments, info = whisper.transcribe(
                chunk, language=language, word_timestamps=True,
                vad_filter=True, condition_on_previous_text=False, hotwords=hot,
            )
            lang = info.language
            chunk_segs = []
            for s in segments:
                chunk_segs.append({
                    "start": round(a + s.start, 3), "end": round(a + s.end, 3), "text": s.text.strip(),
                    "words": [{"start": round(a + w.start, 3), "end": round(a + w.end, 3), "word": w.word.strip(),
                               "prob": round(w.probability, 3)} for w in (s.words or [])],
                })
            dropped += [sg["text"] for sg in chunk_segs if hallucinated(sg, hot)]
            chunk_segs = [sg for sg in chunk_segs if not hallucinated(sg, hot)]
            local = [{"words": [{"start": w["start"] - a, "end": w["end"] - a} for w in sg["words"]],
                      "start": sg["start"] - a, "end": sg["end"] - a} for sg in chunk_segs]
            missed += [(round(x + a, 2), round(y + a, 2)) for x, y in uncovered_speech(chunk, local)]
            segs += chunk_segs
        segs.sort(key=lambda sg: sg["start"])
        missed.sort()
        fixed = vocab.fix_transcript({"segments": segs}, dictionary["fixes"])  # <memory>/vocabulary.md
        if missed:
            print(f"  warning {sid}: speech-like audio with no words at {missed}; "
                  f"listen there or re-run with --force --model large-v3", flush=True)
        doc = {"media": sid, "language": lang, "model": model, "segments": segs,
               "possibly_missed": missed, "vocab_fixes": fixed}
        if dropped:  # kept for the record: what Whisper "heard" in music/noise
            doc["dropped_hallucinations"] = dropped
        if part:  # partial transcript: only these source stretches were heard
            doc["windows"] = [[round(a, 3), round(b, 3)] for a, b in spans_]
        write_json(out, doc)
        write_txt(out.with_suffix(".txt"), segs)
        done.append(sid)
    return done


def write_txt(path, segs: list[dict]) -> None:
    lines = [f"[{fmt_ts(s['start'])} - {fmt_ts(s['end'])}] {s['text']}" for s in segs]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_transcript(project: Project, sid: str) -> dict | None:
    return read_json(project.path("work", "transcripts", f"{sid}.json"))


def words(project: Project, sid: str) -> list[dict]:
    t = load_transcript(project, sid)
    return [w for s in (t or {}).get("segments", []) for w in s["words"]]


def heard_start(w: dict) -> float:
    """Where the voice of a word really starts. Whisper often stretches a short word back over the
    pause before it ("A" of "A gente" as 0.86 s, "Segue" as 1.66 s): the sound sits at the END of
    such a span. Longer than a slow reading of its letters, the word starts that long before its end."""
    longest = 0.15 + 0.12 * max(1, sum(ch.isalnum() for ch in w["word"]))
    return max(w["start"], w["end"] - longest)
