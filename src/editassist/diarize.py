"""diarize: who speaks when. Writes "speaker" on every word (and segment) of a transcript and
regenerates the .txt with [Name] tags, so cuts, captions and multicam can follow the speaker.

Two modes:
  tracks  one mic per person (podcasts, interviews): each word goes to the mic that is loudest
          during it. No extra dependencies; needs `ea sync` between the mics and the transcribed media.
  auto    single mixed recording: pyannote.audio (optional extra: `uv sync --extra diarize`, plus a
          Hugging Face token in HF_TOKEN with access to pyannote/speaker-diarization-3.1).
"""
from __future__ import annotations

import os
import wave

from .ingest import media_by_id
from .project import ROOT, Project, read_json, write_json
from .sync import RATE, _to_ref
from .transcribe import fmt_ts, load_transcript


def _audio(project: Project, sid: str):
    import numpy as np

    m = media_by_id(project)[sid]
    with wave.open(str(project.abs(m["analysis_audio"])), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


def _rms(x, a: float, b: float) -> float:
    import numpy as np

    i, j = max(0, int(a * RATE)), max(0, int(b * RATE))
    seg = x[i:j]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


def by_tracks(project: Project, sid: str, speakers: dict[str, str]) -> dict:
    """speakers: {"Ana": "mic_ana", "Bruno": "mic_bruno"} (media ids, synced to `sid` or to a shared ref)."""
    t = load_transcript(project, sid)
    if not t:
        raise SystemExit(f"no transcript for {sid}: run `ea transcribe` first")
    data = read_json(project.path("work", "sync.json"), {}) or {}
    tracks = {}
    for name, mid in speakers.items():
        if mid == sid:
            off = 0.0
        else:
            try:
                off = _to_ref(data, mid, sid)
            except SystemExit:  # not aligned yet: do it now
                from .sync import sync
                sync(project, sid, [mid])
                data = read_json(project.path("work", "sync.json"), {}) or {}
                off = _to_ref(data, mid, sid)
        x = _audio(project, mid)
        # normalise each mic by its own SPEECH level (loud 50 ms frames), so a hot mic doesn't win
        # everything and a mic that is mostly bleed doesn't get its bleed amplified
        import numpy as np
        hop = 800
        n = max(1, len(x) // hop)
        frames = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1))
        level = float(np.percentile(frames, 95)) + 1e-6
        tracks[name] = (x / level, off)
    counts = {n: 0 for n in speakers}
    for seg in t["segments"]:
        for w in seg["words"]:
            scores = {n: _rms(x, w["start"] + off, w["end"] + off) for n, (x, off) in tracks.items()}
            w["speaker"] = max(scores, key=scores.get)
            counts[w["speaker"]] += 1
    return _finish(project, sid, t, counts, "tracks")


def auto(project: Project, sid: str, num_speakers: int | None = None, names: list[str] | None = None) -> dict:
    try:
        import torch  # noqa: F401
        from pyannote.audio import Pipeline
    except ImportError:
        raise SystemExit("automatic diarization needs the optional extra: `uv sync --extra diarize` "
                         "(downloads PyTorch, ~2 GB). Or record one mic per speaker and use --tracks.")
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN missing: create a read token at huggingface.co/settings/tokens and accept "
                         "the terms of pyannote/speaker-diarization-3.1 and pyannote/segmentation-3.0")
    t = load_transcript(project, sid)
    if not t:
        raise SystemExit(f"no transcript for {sid}: run `ea transcribe` first")
    m = media_by_id(project)[sid]
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
    kw = {"num_speakers": num_speakers} if num_speakers else {}
    diar = pipe(str(project.abs(m["analysis_audio"])), **kw)
    turns = [(seg.start, seg.end, label) for seg, _, label in diar.itertracks(yield_label=True)]
    labels = sorted({lab for _, _, lab in turns})
    rename = {lab: (names[i] if names and i < len(names) else f"S{i + 1}") for i, lab in enumerate(labels)}
    counts = {v: 0 for v in rename.values()}
    for seg in t["segments"]:
        for w in seg["words"]:
            best, ov = None, 0.0
            for a, b, lab in turns:
                o = min(b, w["end"]) - max(a, w["start"])
                if o > ov:
                    best, ov = lab, o
            if best:
                w["speaker"] = rename[best]
                counts[w["speaker"]] += 1
    return _finish(project, sid, t, counts, "pyannote")


def _finish(project: Project, sid: str, t: dict, counts: dict, method: str) -> dict:
    from collections import Counter

    for seg in t["segments"]:
        c = Counter(w.get("speaker") for w in seg["words"] if w.get("speaker"))
        if c:
            seg["speaker"] = c.most_common(1)[0][0]
    t["diarization"] = method
    write_json(project.path("work", "transcripts", f"{sid}.json"), t)
    # .txt grouped by speaker turns (words, so a turn change mid-segment still shows)
    lines, cur, buf, t0, t1 = [], None, [], 0.0, 0.0
    for seg in t["segments"]:
        for w in seg["words"]:
            spk = w.get("speaker", "?")
            if spk != cur and buf:
                lines.append(f"[{fmt_ts(t0)} - {fmt_ts(t1)}] [{cur}] {' '.join(buf)}")
                buf = []
            if not buf:
                t0 = w["start"]
            cur, t1 = spk, w["end"]
            buf.append(w["word"])
    if buf:
        lines.append(f"[{fmt_ts(t0)} - {fmt_ts(t1)}] [{cur}] {' '.join(buf)}")
    project.path("work", "transcripts", f"{sid}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"media": sid, "method": method, "words_per_speaker": counts, "read": f"work/transcripts/{sid}.txt"}
