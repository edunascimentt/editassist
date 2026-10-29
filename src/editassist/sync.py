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


def _find(a, b):
    """GCC-PHAT: where window b sits inside a, as (lag, confidence) with b[t] ~ a[t + lag].
    Only lags that keep b wholly inside a: a lag past n/2 of the circular correlation would
    wrap around and read as a large negative jump."""
    import numpy as np

    n = 1
    while n < len(a) + len(b):
        n *= 2
    R = np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n))
    R /= np.abs(R) + 1e-12
    cc = np.fft.irfft(R, n)[:max(1, len(a) - len(b) + 1)]
    k = int(np.argmax(cc))
    return k, float(cc[k]) / (float(np.median(np.abs(cc))) + 1e-12)


def _fits(a, b, m: int, s: int, block: int) -> float:
    """Confidence that b[m:m+block] plays at a[m+s] (whitened, +-10 ms); 0 when it does not."""
    pad = RATE // 20
    if m < 0 or m + s - pad < 0 or m + block > len(b) or m + s + block + pad > len(a):
        return 0.0
    lag, conf = _find(a[m + s - pad:m + s + block + pad], b[m:m + block])
    return conf if abs(lag - pad) <= RATE // 100 else 0.0


def _boundary(a, b, m0: int, m1: int, s1: int, s2: int, block: int) -> int:
    """Sample in b (between m0 and m1) where shift s1 stops fitting and s2 starts:
    the split that maximises how well each side fits its own shift. A plain dot product fails
    here (camera mic vs desk feed); the whitened per-block match does not."""
    import numpy as np

    starts = list(range(max(m0, 0), max(m1, m0 + block), block))
    c1 = np.array([_fits(a, b, m, s1, block) for m in starts])
    c2 = np.array([_fits(a, b, m, s2, block) for m in starts])
    score = [c1[:k].sum() + c2[k:].sum() for k in range(len(starts) + 1)]
    k = int(np.argmax(score))
    return starts[k] if k < len(starts) else m1


def drift_map(project: Project, ref: str, other: str, win: float = 10.0, hop: float = 5.0,
              search: float = 90.0, min_conf: float = 8.0, tol: float = 0.08) -> dict:
    """Where an external recorder (`other`) lost audio against a continuous camera (`ref`).

    A recorder that drops samples (card too slow) gets SHORTER instead of going silent, so one
    global offset only fits until the first drop. This slides a window along `other`, finds it in
    `ref` near the previous shift, and splits the recording into pieces of constant shift.
      segments: [{other_in, other_out, ref_in, ref_out, shift}]  (ref = other + shift)
      gaps:     [{ref_from, ref_to, missing}]  camera time with no recorder audio
    Writes work/sync_map/<other>__<ref>.json."""
    import numpy as np

    a, b = _wav(project, ref, 1e9), _wav(project, other, 1e9)
    W, H = int(win * RATE), int(hop * RATE)
    # anchor: where minutes of other sit in ref, probed along the whole recording; probes far
    # below the best one are chance matches (a camera's opening can be silent or not in ref).
    # Drops only push the shift later, so the search spans the confident probes plus `search` s
    # (or whatever is left of ref after other, whichever is larger)
    first = next((m for m in range(0, len(b) - W, H) if float(np.abs(b[m:m + W]).max()) >= 1e-3), 0)
    step = max(6 * W, (len(b) - first) // 8)
    probes = [(m, *_find(a, b[m:m + 6 * W])) for m in range(first, max(first + 1, len(b) - 6 * W), step)]
    top = max(c for _, _, c in probes)
    shifts = [lag - m for m, lag, c in probes if c >= top / 2]
    lo_s = min(shifts) - 2 * RATE
    hi_s = max(max(shifts) + int(search * RATE), len(a) - len(b)) + 2 * RATE
    pts = []
    for m in range(0, len(b) - W, H):
        lo = max(0, m + lo_s)
        seg = a[lo:m + hi_s + W]
        if len(seg) < W + RATE or float(np.abs(b[m:m + W]).max()) < 1e-3:
            continue
        lag, conf = _find(seg, b[m:m + W])
        if conf >= min_conf:
            pts.append((m, lo + lag - m, conf))
    # runs of >= 3 consecutive windows that agree are real; a single window can match anywhere
    runs: list[list] = []
    for p in pts:
        if runs and abs(p[1] - runs[-1][-1][1]) <= tol * RATE:
            runs[-1].append(p)
        else:
            runs.append([p])
    runs = [r for r in runs if len(r) >= 3]
    if not runs:
        raise SystemExit(f"{other} not found in {ref}: no stretch of windows agreed")
    # the heaviest chain of runs whose shift never goes back (a drop only adds camera time)
    med = [float(np.median([p[1] for p in r])) for r in runs]
    best, prev = [len(r) for r in runs], [-1] * len(runs)
    for i in range(len(runs)):
        for k in range(i):
            if med[k] <= med[i] + tol * RATE and best[k] + len(runs[i]) > best[i]:
                best[i], prev[i] = best[k] + len(runs[i]), k
    i, chain = int(np.argmax(best)), []
    while i >= 0:
        chain.append(runs[i])
        i = prev[i]
    merged: list[list] = []
    for r in reversed(chain):
        if merged and abs(np.median([p[1] for p in r]) - np.median([p[1] for p in merged[-1]])) <= tol * RATE:
            merged[-1] += r
        else:
            merged.append(r)
    segs = []
    start = 0
    for i, r in enumerate(merged):
        s = int(np.median([p[1] for p in r]))
        if i + 1 < len(merged):
            s2 = int(np.median([p[1] for p in merged[i + 1]]))
            end = _boundary(a, b, max(start, r[-1][0] - W), merged[i + 1][0][0] + W, s, s2, RATE // 2)
        else:
            end = len(b)
        end = min(end, len(a) - s)
        segs.append({"other_in": round(start / RATE, 3), "other_out": round(end / RATE, 3),
                     "ref_in": round((start + s) / RATE, 3), "ref_out": round((end + s) / RATE, 3),
                     "shift": round(s / RATE, 4), "windows": len(r),
                     "confidence": round(float(np.median([p[2] for p in r])), 1)})
        start = end
    gaps = [{"ref_from": p["ref_out"], "ref_to": q["ref_in"], "missing": round(q["ref_in"] - p["ref_out"], 3)}
            for p, q in zip(segs, segs[1:]) if q["ref_in"] - p["ref_out"] > 0.01]
    res = {"ref": ref, "other": other, "segments": segs, "gaps": gaps,
           "overlaps": [{"ref_at": p["ref_out"], "repeated": round(p["ref_out"] - q["ref_in"], 3)}
                        for p, q in zip(segs, segs[1:]) if p["ref_out"] - q["ref_in"] > 0.01]}
    write_json(project.path("work", "sync_map", f"{other}__{ref}.json"), res)
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


def _map(project: Project, other: str, ref: str) -> dict:
    m = read_json(project.path("work", "sync_map", f"{other}__{ref}.json"))
    if m is None:
        raise SystemExit(f"no map of {other} on {ref}: run `ea sync <project> --map --ref {ref} {other}`")
    return m


def _ref_time(m: dict, t: float, end: bool = False) -> float:
    """Time on the map's ref for time t of its other; refuses a t inside a dropout seam."""
    for s in m["segments"]:
        if s["other_in"] - 1e-6 <= t <= s["other_out"] + 1e-6 and (not end or t > s["other_in"] + 1e-6):
            return t + s["shift"]
    raise SystemExit(f"{t:.3f}s of {m['other']} is outside its mapped recording")


def build_from_map(project: Project, ref: str, recorder: str, camera: str, keep: list[tuple[float, float]],
                   name: str | None = None) -> dict:
    """timeline.json of one camera under the recorder's audio, keeping only `keep` (recorder time).

    Every kept range must sit inside ONE piece of the recorder's map (cut out each dropout,
    whole sentences around it): the picture of each range is the camera at the same moment, so lips
    stay in sync across the drops. Camera time = ref time + the camera's own shift on ref
    (from its map, `ea sync --map --ref <ref> <camera>`); camera == ref needs none."""
    cat = media_by_id(project)
    rm = _map(project, recorder, ref)
    cshift = 0.0
    if camera != ref:
        cm = _map(project, camera, ref)
        if len(cm["segments"]) != 1:
            raise SystemExit(f"{camera} has {len(cm['segments'])} pieces on {ref}: a camera should be continuous")
        cshift = -cm["segments"][0]["shift"]  # ref = camera + shift
    v, a, t, bad = [], [], 0.0, []
    for k0, k1 in keep:
        r0, r1 = _ref_time(rm, k0), _ref_time(rm, k1, end=True)
        if abs((r1 - r0) - (k1 - k0)) > 1e-3:
            bad.append([k0, k1])
            continue
        c0 = r0 + cshift
        if c0 < 0 or c0 + (k1 - k0) > cat[camera]["duration"] + 0.01:
            raise SystemExit(f"{camera} is not rolling for recorder {k0:.2f}-{k1:.2f}")
        v.append({"media": cat[camera]["path"], "in": c0, "out": c0 + (k1 - k0), "start": t})
        a.append({"media": cat[recorder]["path"], "in": k0, "out": k1, "start": t, "role": "dialogue"})
        t += k1 - k0
    if bad:
        raise SystemExit(f"kept ranges cross a dropout (cut around it): {bad}; seams at "
                         f"{[s['other_out'] for s in rm['segments'][:-1]]}")
    pj = read_json(project.path("project.json"), {}) or {}
    tl = {"name": name or f"{project.name}_{camera}", "fps": pj.get("fps", 30), "width": pj.get("width", 1920),
          "height": pj.get("height", 1080),
          "tracks": [{"kind": "video", "name": "V1", "clips": v}, {"kind": "audio", "name": "A1", "clips": a}],
          "markers": []}
    T.save(project, tl)
    return {"timeline": tl["name"], "clips": len(v), "duration": round(t, 3), "camera_shift_on_ref": -cshift}
