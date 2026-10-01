"""beats: tempo and beat times of a music track (the model can't listen, so it reads these).

work/beats/<id>.json  {"bpm": 120.2, "beats": [s...], "downbeats": [s...], "confidence": 0..1}

Onset envelope from spectral flux (numpy STFT), tempo from its autocorrelation with a prior around
110 BPM, beats by dynamic programming (Ellis 2007), downbeats as the strongest 4-beat phase.
No librosa/numba, so it installs the same on every OS.
"""
from __future__ import annotations

import subprocess

from . import timeline as T
from .ingest import media_by_id
from .project import Project, read_json, write_json

SR, N_FFT, HOP = 22050, 2048, 512


def load_audio(path: str, start: float = 0.0, dur: float | None = None):
    import numpy as np

    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + \
          ["-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def _bands():
    import numpy as np

    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    edges = np.geomspace(30, 11000, 25)  # 24 log-spaced bands: every octave weighs the same
    return freqs, edges


def onset_envelope(y, low_only: bool = False):
    """Spectral flux per log band, summed. low_only: < 250 Hz (kick drum), used to pick beat phase."""
    import numpy as np

    if len(y) < N_FFT:
        y = np.pad(y, (0, N_FFT - len(y)))
    frames = np.lib.stride_tricks.sliding_window_view(y, N_FFT)[::HOP] * np.hanning(N_FFT)
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs, edges = _bands()
    if low_only:
        edges = edges[edges <= 250]
    bands = np.stack([power[:, (freqs >= lo) & (freqs < hi)].sum(1) for lo, hi in zip(edges[:-1], edges[1:])], 1)
    logb = np.log1p(1000 * bands / (bands.max() + 1e-12))
    flux = np.maximum(np.diff(logb, axis=0), 0).sum(1)
    flux = np.concatenate([[0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")  # remove slow trend
    flux = np.maximum(flux, 0)
    return flux / (flux.std() + 1e-9)


def frame_time(i):
    """Centre of analysis frame i (frames start at i*HOP)."""
    return (i * HOP + N_FFT / 2) / SR


def tempo(env, lo: float = 60, hi: float = 200, prior: float = 110):
    import numpy as np

    fr = SR / HOP
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    lags = np.arange(int(fr * 60 / hi), int(fr * 60 / lo) + 1)
    bpm = 60 * fr / lags
    weight = np.exp(-0.5 * (np.log2(bpm / prior) / 0.9) ** 2)  # mild preference for common tempi
    score = ac[lags] * weight
    i = int(np.argmax(score))
    # refine with parabolic interpolation
    if 0 < i < len(score) - 1:
        a, b, c = score[i - 1], score[i], score[i + 1]
        shift = 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
    else:
        shift = 0.0
    period = lags[i] + shift
    conf = float(score[i] / (ac[0] + 1e-9))
    return 60 * fr / period, period, conf


def track_beats(env, period: float, tightness: float = 100.0):
    import numpy as np

    n = len(env)
    score = env.copy()
    back = np.full(n, -1)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    window = np.arange(-hi, -lo + 1)
    penalty = -tightness * np.log(-window / period) ** 2
    for t in range(hi, n):
        cand = score[t + window] + penalty
        k = int(np.argmax(cand))
        score[t] = env[t] + cand[k]
        back[t] = t + window[k]
    # start from the best of the last period, walk back
    t = int(np.argmax(score[n - hi:]) + n - hi) if n > hi else int(np.argmax(score))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    return np.array(beats[::-1])


def detect(project: Project, sid: str) -> dict:
    import numpy as np

    m = media_by_id(project)[sid]
    y = load_audio(str(project.abs(m["path"])))
    env = onset_envelope(y)
    bpm, period, conf = tempo(env)
    idx = track_beats(env, period)
    # beat vs off-beat: pick the phase where the kick (low band) hits harder
    low = onset_envelope(y, low_only=True)
    half = int(round(period / 2))
    shifted = idx[idx + half < len(low)] + half
    if len(shifted) and low[shifted].sum() > 1.2 * low[idx].sum():
        idx = shifted
    # the flux of frame i reflects the change between frames i-1 and i; measured on synthetic
    # tracks with known beats, the onset sits half a hop after frame i's centre
    beats = [round(float(frame_time(i) + HOP / SR / 2), 3) for i in idx]
    # downbeat phase: which of the 4 offsets carries the most onset energy
    strength = [float(np.sum(low[idx[p::4]])) for p in range(4)] if len(idx) >= 8 else [1, 0, 0, 0]
    phase = int(np.argmax(strength))
    res = {"media": sid, "bpm": round(float(bpm), 2), "confidence": round(conf, 3),
           "beats": beats, "downbeats": beats[phase::4]}
    write_json(project.path("work", "beats", f"{sid}.json"), res)
    return {k: (v if k not in ("beats", "downbeats") else f"{len(v)} times") for k, v in res.items()} | {
        "file": f"work/beats/{sid}.json"}


def timeline_beats(project: Project, tl: dict, sid: str, downbeats: bool = False) -> list[float]:
    """Beat times on the TIMELINE for every placement of that music media."""
    b = read_json(project.path("work", "beats", f"{sid}.json"))
    if not b:
        raise SystemExit(f"no beats for {sid}: run `ea beats <project> {sid}`")
    path = media_by_id(project)[sid]["path"]
    times = []
    for tr in tl["tracks"]:
        for c in tr["clips"]:
            if c["media"] == path:
                sp = c.get("speed", 1.0)
                times += [c["start"] + (t - c["in"]) / sp for t in (b["downbeats"] if downbeats else b["beats"])
                          if c["in"] <= t <= c["out"]]
    return sorted(times)


def snap(project: Project, sid: str, tracks: list[str], downbeats: bool = False, max_shift: float = 0.25) -> dict:
    """Move the START of clips on insert tracks (b-roll, motion, sfx) to the nearest beat."""
    tl = T.load(project)
    beats = timeline_beats(project, tl, sid, downbeats)
    moved = []
    for name in tracks:
        for c in T.track(tl, name)["clips"]:
            if not beats:
                break
            nb = min(beats, key=lambda b: abs(b - c["start"]))
            if 0.001 < abs(nb - c["start"]) <= max_shift and nb >= 0:
                moved.append({"track": name, "from": c["start"], "to": round(nb, 3)})
                c["start"] = nb
    T.save(project, tl)
    return {"moved": moved, "beats_on_timeline": len(beats)}


def montage(project: Project, sid: str, segments: list[dict], every: int = 2, start_beat: int = 0,
            track: str = "V1", music_gain: float = -6.0) -> dict:
    """Beat-cut montage: each segment {media, in} fills `every` beats, in order, music on its own track.
    Replaces `track` and the Music track; dialogue tracks are left alone."""
    b = read_json(project.path("work", "beats", f"{sid}.json"))
    if not b:
        raise SystemExit(f"no beats for {sid}: run `ea beats <project> {sid}`")
    catalog = media_by_id(project)
    tl = read_json(project.path("timeline.json")) or T.new(project)
    beats = b["beats"][start_beat:]
    cuts = beats[::every]
    if len(cuts) < 2:
        raise SystemExit("not enough beats for a montage")
    t0 = cuts[0]
    v = T.track(tl, track, "video")
    v["clips"] = []
    for i, seg in enumerate(segments):
        if i + 1 >= len(cuts):
            break
        sid_v = seg["media"] if seg["media"] in catalog else next(k for k, m in catalog.items() if m["path"] == seg["media"])
        m = catalog[sid_v]
        d = cuts[i + 1] - cuts[i]
        a = float(seg.get("in", 0.0))
        if m.get("kind") != "image" and m.get("duration") and a + d > m["duration"]:
            a = max(0.0, m["duration"] - d)
        v["clips"].append({"media": m["path"], "in": a, "out": a + d, "start": cuts[i] - t0})
    length = T.end(v["clips"][-1])
    mus = T.track(tl, "Music", "audio")
    mpath = catalog[sid]["path"]
    mus["clips"] = [{"media": mpath, "in": t0, "out": t0 + length, "start": 0.0, "gain_db": music_gain, "fade": 0.5}]
    T.save(project, tl)
    return {"clips": len(v["clips"]), "length": round(length, 3), "bpm": b["bpm"], "cut_every_beats": every}
