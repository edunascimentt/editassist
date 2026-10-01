"""sync: align cameras and external audio by their sound, then swap audio or switch camera angles.

  offset  = how many seconds `other` started BEFORE the reference; i.e.
            reference_time = other_time - offset   <=>   other_time = reference_time + offset
work/sync.json  {"<other id>": {"ref": "<ref id>", "offset": 1.234, "confidence": 7.9}}

GCC-PHAT cross-correlation on the 16 kHz analysis audio: whitening makes it robust to different
mics, gain and room tone. confidence = peak / median of the correlation (above ~5 is solid).
"""
from __future__ import annotations

import wave

from . import timeline as T
from .ingest import media_by_id
from .project import Project, read_json, write_json

RATE = 16000


def _wav(project: Project, sid: str, seconds: float):
    import numpy as np

    m = media_by_id(project)[sid]
    if not m.get("analysis_audio"):
        raise SystemExit(f"{sid} has no audio")
    with wave.open(str(project.abs(m["analysis_audio"])), "rb") as w:
        n = min(w.getnframes(), int(seconds * RATE))
        return np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768.0


def offset(project: Project, ref: str, other: str, seconds: float = 600, max_lag: float = 300) -> dict:
    import numpy as np

    a, b = _wav(project, ref, seconds), _wav(project, other, seconds)
    n = 1
    while n < len(a) + len(b):
        n *= 2
    A, B = np.fft.rfft(a, n), np.fft.rfft(b, n)
    R = B * np.conj(A)
    R /= np.abs(R) + 1e-12
    cc = np.fft.irfft(R, n)
    lag_max = min(int(max_lag * RATE), n // 2 - 1, max(len(a), len(b)))
    cc = np.concatenate([cc[-lag_max:], cc[:lag_max + 1]])  # lags -lag_max .. +lag_max
    k = int(np.argmax(cc))
    lag = k - lag_max  # samples: b[t + lag] ~ a[t]
    peak = float(cc[k])
    conf = peak / (float(np.median(np.abs(cc))) + 1e-12)
    return {"ref": ref, "offset": round(lag / RATE, 4), "confidence": round(conf, 1)}


def sync(project: Project, ref: str, others: list[str]) -> dict:
    data = read_json(project.path("work", "sync.json"), {}) or {}
    res = {}
    for o in others:
        r = offset(project, ref, o)
        data[o] = r
        res[o] = r | ({"warning": "low confidence: check visually (clap) before trusting"} if r["confidence"] < 5 else {})
    write_json(project.path("work", "sync.json"), data)
    return res


def _to_ref(data: dict, sid: str, ref: str) -> float:
    """Offset that maps ref time -> sid time (sid_time = ref_time + off)."""
    if sid == ref:
        return 0.0
    d = data.get(sid)
    if d and d["ref"] == ref:
        return d["offset"]
    r = data.get(ref)  # ref itself synced to a third clip
    if d and r and d["ref"] == r["ref"]:
        return d["offset"] - r["offset"]
    raise SystemExit(f"no sync between {ref} and {sid}: run `ea sync <project> --ref {ref} {sid}`")


def swap_audio(project: Project, from_id: str, to_id: str, track: str = "A1") -> dict:
    """Replace dialogue cut from `from_id` (camera audio) with the same moments from `to_id`
    (external mic). Timing is unchanged; only the source changes."""
    cat = media_by_id(project)
    data = read_json(project.path("work", "sync.json"), {}) or {}
    off = _to_ref(data, to_id, from_id)
    tl = T.load(project)
    src, dst = cat[from_id]["path"], cat[to_id]["path"]
    n, skipped = 0, []
    for c in T.track(tl, track)["clips"]:
        if c["media"] != src:
            continue
        a, b = c["in"] + off, c["out"] + off
        if a < 0 or b > cat[to_id]["duration"] + 0.01:
            skipped.append(c["start"])
            continue
        c.update(media=dst, **{"in": round(a, 4), "out": round(b, 4)})
        n += 1
    T.save(project, tl)
    return {"swapped": n, "offset": off, "outside_other_recording_at": skipped}


def switch(project: Project, t0: float, t1: float, to_id: str, track: str = "V1") -> dict:
    """Multicam: show camera `to_id` on [t0, t1) of the timeline, in sync with what's playing."""
    cat = media_by_id(project)
    data = read_json(project.path("work", "sync.json"), {}) or {}
    tl = T.load(project)
    T.split(tl, t0, (track,))
    T.split(tl, t1, (track,))
    by_path = {m["path"]: k for k, m in cat.items()}
    n = 0
    for c in T.track(tl, track)["clips"]:
        if c["start"] >= t0 - T.EPS and T.end(c) <= t1 + T.EPS:
            cur = by_path.get(c["media"])
            if cur is None or cur == to_id:
                continue
            # current clip's source time -> shared clock -> new camera's source time
            off = _to_ref(data, to_id, cur)
            a, b = c["in"] + off, c["out"] + off
            if a < 0 or b > cat[to_id]["duration"] + 0.01:
                raise SystemExit(f"{to_id} doesn't cover {c['start']:.2f}s (camera not rolling)")
            c.update(media=cat[to_id]["path"], **{"in": round(a, 4), "out": round(b, 4)})
            c.pop("crop", None)
            c.pop("zoom", None)  # framing belonged to the other camera
            n += 1
    T.save(project, tl)
    return {"switched_clips": n, "to": to_id, "range": [t0, t1]}
