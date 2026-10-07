"""Cutting from transcripts: silence/filler removal, phrase lookup, segment lists -> timeline."""
from __future__ import annotations

import re
import unicodedata

from . import timeline as T
from .ingest import media_by_id
from .media import run
from .project import Project
from .transcribe import words

# Hesitation sounds only. Real words that are often fillers ("tipo", "like", "né", "so") are
# context dependent: the model removes those by reading the transcript, not by list.
FILLERS = {"uh", "um", "uhm", "umm", "ah", "ahh", "eh", "ehh", "er", "erm", "hmm", "hm", "mm",
           "ãh", "ã", "ãã", "éé", "éé", "ahn", "hum", "humm", "ééé", "aham"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", "", s)


def is_filler(w: str) -> bool:
    raw = re.sub(r"[^\w]+", "", w.lower())
    return raw in FILLERS or norm(w) in {norm(f) for f in FILLERS}


def speech_segments(project: Project, sid: str, min_silence: float = 0.45, pad: float = 0.08,
                    drop_fillers: bool = True) -> list[dict]:
    m = media_by_id(project)[sid]
    ws = words(project, sid)
    if not ws:
        return silencedetect_segments(project, sid, min_silence, pad)
    if drop_fillers:
        ws = [w for w in ws if not is_filler(w["word"])]
    segs, cur = [], None
    for w in ws:
        if cur and w["start"] - cur["out"] < min_silence:
            cur["out"] = w["end"]
        else:
            if cur:
                segs.append(cur)
            cur = {"media": m["path"], "in": w["start"], "out": w["end"]}
    if cur:
        segs.append(cur)
    return _pad_merge(segs, pad, m["duration"])


def silencedetect_segments(project: Project, sid: str, min_silence: float, pad: float,
                           noise_db: float = -35) -> list[dict]:
    """Fallback without a transcript: keep everything that is not silence."""
    m = media_by_id(project)[sid]
    res = run(["ffmpeg", "-v", "info", "-i", str(project.abs(m["analysis_audio"])), "-af",
               f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    segs, t = [], 0.0
    for s, e in zip(starts, ends + [m["duration"]] * (len(starts) - len(ends))):
        if s > t:
            segs.append({"media": m["path"], "in": t, "out": s})
        t = e
    if t < m["duration"]:
        segs.append({"media": m["path"], "in": t, "out": m["duration"]})
    return _pad_merge(segs, pad, m["duration"])


def _pad_merge(segs: list[dict], pad: float, duration: float) -> list[dict]:
    out = []
    for s in segs:
        a, b = max(0.0, s["in"] - pad), min(duration, s["out"] + pad)
        if out and out[-1]["media"] == s["media"] and a <= out[-1]["out"]:
            out[-1]["out"] = max(out[-1]["out"], b)
        else:
            out.append({**s, "in": round(a, 3), "out": round(b, 3)})
    return [s for s in out if s["out"] - s["in"] >= 0.15]


def find_phrase(project: Project, phrase: str, sid: str | None = None) -> list[dict]:
    """Exact word-boundary times of a phrase quoted from the transcript (accent/punct insensitive)."""
    target = [norm(t) for t in phrase.split() if norm(t)]
    hits = []
    if not target:
        return hits
    for mid, m in media_by_id(project).items():
        if sid and mid != sid:
            continue
        ws = words(project, mid)
        toks = [norm(w["word"]) for w in ws]
        for i in range(len(toks) - len(target) + 1):
            if toks[i:i + len(target)] == target:
                hits.append({"media_id": mid, "media": m["path"], "in": ws[i]["start"],
                             "out": ws[i + len(target) - 1]["end"],
                             "text": " ".join(w["word"] for w in ws[i:i + len(target)])})
    return hits


def _neighbours(ws: list[dict], a: float, b: float) -> tuple[float, float]:
    """End of the last word before `a` and start of the first word after `b` (mid-points decide)."""
    prev_end, next_start = 0.0, float("inf")
    for w in ws:
        mid = (w["start"] + w["end"]) / 2
        if mid < a - 1e-3:
            prev_end = max(prev_end, w["end"])
        elif mid > b + 1e-3:
            next_start = min(next_start, w["start"])
    return prev_end, next_start


PAD_IN, PAD_OUT = 0.12, 0.30


def resolve_segments(project: Project, spec: list[dict]) -> list[dict]:
    """Segment specs written by the model. Each item is either
      {"media": "<id or path>", "in": 1.2, "out": 5.0}
    or quotes that get snapped to word boundaries:
      {"media": "<id>", "from": "first words of the bite", "to": "last words of the bite"}
    """
    catalog = media_by_id(project)
    out = []
    for i, s in enumerate(spec):
        sid = s["media"] if s["media"] in catalog else next(
            (k for k, m in catalog.items() if m["path"] == s["media"]), None)
        if sid is None:
            raise SystemExit(f"segment {i}: unknown media {s['media']!r}")
        seg = {"media": catalog[sid]["path"], "note": s.get("note")}
        if "from" in s:
            a = find_phrase(project, s["from"], sid)
            if not a:
                raise SystemExit(f"segment {i}: phrase not found in {sid}: {s['from']!r}")
            seg["in"] = a[0]["in"]
            after = [h for h in find_phrase(project, s.get("to", s["from"]), sid) if h["out"] >= seg["in"]]
            if not after:
                raise SystemExit(f"segment {i}: end phrase not found after start in {sid}: {s.get('to')!r}")
            seg["out"] = after[0]["out"]
        else:
            seg["in"], seg["out"] = float(s["in"]), float(s["out"])
        # Whisper puts word ends early (final consonants, breath): a bite cut at the word end sounds
        # clipped. More room after than before; padding never reaches into the neighbouring words.
        pad_in, pad_out = s.get("pad_in", s.get("pad", PAD_IN)), s.get("pad_out", s.get("pad", PAD_OUT))
        prev_end, next_start = _neighbours(words(project, sid), seg["in"], seg["out"])
        seg["in"] = max(0.0, prev_end + 0.02 if prev_end else 0.0, seg["in"] - pad_in)
        seg["out"] = min(catalog[sid]["duration"] or seg["out"] + pad_out, next_start - 0.02, seg["out"] + pad_out)
        out.append(seg)
    return out


def build(project: Project, spec: list[dict], tighten: bool = False, **kw) -> dict:
    segs = resolve_segments(project, spec)
    if tighten:  # also strip pauses/fillers inside each chosen bite
        catalog = media_by_id(project)
        by_path = {m["path"]: k for k, m in catalog.items()}
        tight = []
        for s in segs:
            inner = speech_segments(project, by_path[s["media"]], **kw)
            for x in inner:
                a, b = max(x["in"], s["in"]), min(x["out"], s["out"])
                if b - a >= 0.15:
                    tight.append({**s, "in": a, "out": b})
        segs = tight
    return T.from_segments(project, segs)
