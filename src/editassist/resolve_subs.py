"""resolve-subs: re-break the captions already on a Resolve timeline's subtitle track to a maximum
line length (vertical cuts: 15 characters, 2 lines), keeping the text the editor corrected.

Resolve draws a subtitle cue on one line however long it is, so a 40-character cue runs edge to edge
on a 9:16 frame and under the Instagram buttons (DOMCast cortes, 2026-10-13). The track style (font,
size, position) is untouched; only the cues are rewritten. A cue that needs more than `max_lines`
lines is split into several cues, timed from the project's word timestamps when the timeline's audio
comes from transcribed media (else by character share of the cue).
"""
from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from pathlib import Path

from .subtitles import CLINGY

SENTENCE_END = (".", "?", "!", "...", "…")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t).lower()
    return re.sub(r"[^\w]", "", t)


VOWELS = set("aeiouáéíóúâêôãõàü")


def hyphenate(tok: str, max_chars: int) -> list[str]:
    """A word longer than a line: split at its own hyphen ("pré-" "adolescência,"), else at a
    vowel-consonant-vowel boundary near the middle ("responsa-" "bilidade."), else hard."""
    if len(tok) <= max_chars:
        return [tok]
    if "-" in tok[1:-1]:
        i = tok.index("-", 1) + 1
        return [tok[:i]] + hyphenate(tok[i:], max_chars)
    low = tok.lower()
    cuts = [i for i in range(2, len(tok) - 2) if low[i - 1] in VOWELS and low[i] not in VOWELS
            and low[i + 1] in VOWELS and i + 1 <= max_chars]
    i = min(cuts, key=lambda i: abs(i - len(tok) / 2)) if cuts else max_chars - 1
    return [tok[:i] + "-"] + hyphenate(tok[i:], max_chars)


def _line_cost(toks: list[str], max_chars: int) -> float:
    n = len(" ".join(toks))
    if n > max_chars and len(toks) > 1:
        return float("inf")
    last = toks[-1]
    cost = 30 + (max_chars - n) ** 2 * 0.25  # few lines first, then even lengths
    if last.endswith((",", ";", ":")) or last.endswith(SENTENCE_END):
        cost -= 6  # a line that ends where the voice pauses
    elif last.lower() in CLINGY:
        cost += 12  # never end on "de", "a", "que" when avoidable
    return cost


def wrap(text: str, max_chars: int = 15, span_secs=None, min_secs: float = 0.7) -> list[str]:
    """Word wrap to `max_chars` with the fewest lines, preferring breaks after punctuation and never
    ending a line on a short function word when another break exists (minimum-cost line breaking).
    `span_secs(a, b)`: seconds tokens a..b-1 are spoken; one-line captions avoid lines that would flash."""
    toks = [p for t in text.split() for p in hyphenate(t, max_chars)]
    n = len(toks)
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            if j - i > 1 and len(" ".join(toks[i:j])) > max_chars:
                break
            c = best[i] + _line_cost(toks[i:j], max_chars)
            if span_secs and span_secs(i, j) < min_secs:
                c += 15
            if c < best[j]:
                best[j], back[j] = c, i
    lines, j = [], n
    while j > 0:
        lines.insert(0, " ".join(toks[back[j]:j]))
        j = back[j]
    return lines


def chunks(text: str, max_chars: int = 15, max_lines: int = 2, span_secs=None,
           min_secs: float = 0.7) -> list[list[str]]:
    """Cue text -> cues, each a list of <= max_lines lines: the fewest cues, split where the voice
    pauses (sentence end, comma), never leaving a lone short word on a cue of its own ("dela").
    `span_secs(a, b)`: seconds that tokens a..b-1 are on screen; a cue shorter than `min_secs`
    is a flash and costs extra ("Ai, porque" for 0.32 s, 2026-10-13)."""
    lines = wrap(text, max_chars, span_secs if max_lines == 1 else None, min_secs)
    n = len(lines)
    offs = [0]
    for line in lines:
        offs.append(offs[-1] + len(line.split()))

    def cost(i: int, j: int) -> float:
        group = lines[i:j]
        if j < n and group[-1].endswith("-") and max_lines > 1:
            return float("inf")  # both halves of a hyphenated word stay on one caption ("responsa-" | "bilidade");
            # one-line captions have no choice but to show them one after the other
        c = 10.0
        if len(group) == 1 and len(group[0]) < 8:
            c += 6  # a flash of one short word
        if span_secs and span_secs(offs[i], offs[j]) < min_secs:
            c += 9
        if j < n:  # the cue ends here and the next one starts
            if group[-1].endswith(SENTENCE_END):
                c -= 4
            elif group[-1].endswith((",", ";", ":")):
                c -= 3
        return c

    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(max(0, j - max_lines), j):
            c = best[i] + cost(i, j)
            if c < best[j]:
                best[j], back[j] = c, i
    out, j = [], n
    while j > 0:
        out.insert(0, lines[back[j]:j])
        j = back[j]
    return out


def _token_times(tokens: list[str], words: list[dict]) -> list[float | None]:
    """Start time of each caption token, from the transcript word it matches (None when unmatched)."""
    a = [_norm(t) for t in tokens]
    b = [_norm(w["word"]) for w in words]
    times: list[float | None] = [None] * len(tokens)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = words[blk.b + k]["start"]
    return times


def reflow(cues: list[dict], words: list[dict] | None = None, max_chars: int = 15, max_lines: int = 2,
           min_dur: float = 0.5) -> list[dict]:
    """[{start, end, text}] (seconds) -> the same captions with lines <= max_chars, text "line1\\nline2".
    Split cues start on their first word's transcript time when it falls inside the cue."""
    out = []
    for c in cues:
        tokens = [p for t in c["text"].split() for p in hyphenate(t, max_chars)]  # as wrap() saw them
        inside = [w for w in (words or []) if c["start"] - 0.3 <= w["start"] < c["end"]]
        times = _token_times(tokens, inside) if inside else [None] * len(tokens)
        total = sum(len(t) + 1 for t in tokens)
        at, chars = [], 0
        for k, tok in enumerate(tokens):  # when each token starts: its word's time, else its character share
            share = c["start"] + (c["end"] - c["start"]) * chars / total
            t = times[k]
            at.append(t if t is not None and c["start"] <= t < c["end"] else share)
            chars += len(tok) + 1
        at[0] = c["start"]
        at.append(c["end"])
        parts = chunks(c["text"], max_chars, max_lines, lambda a, b: at[b] - at[a])
        if len(parts) == 1:
            out.append({"start": c["start"], "end": c["end"], "text": "\n".join(parts[0])})
            continue
        starts, k = [], 0
        for p in parts:
            starts.append(at[k])
            k += sum(len(l.split()) for l in p)
        # keep order and a readable minimum (shrunk when the cue is too short to give every piece
        # min_dur: a 0.9 s cue cut in 3 gave a -0.07 s piece, 2026-10-13)
        md = min(min_dur, (c["end"] - c["start"]) / len(starts))
        for i in range(1, len(starts)):
            lo, hi = starts[i - 1] + md, c["end"] - md * (len(starts) - i)
            if not lo <= starts[i] <= hi:
                starts[i] = min(max(starts[i], lo), hi)
        for i, p in enumerate(parts):
            end = starts[i + 1] if i + 1 < len(parts) else c["end"]
            out.append({"start": round(starts[i], 3), "end": round(end, 3), "text": "\n".join(p)})
    return out


def _cue_lines(text: str) -> list[str]:
    """Lines of a cue; Resolve returns a cue's line break as U+2028 (LINE SEPARATOR), not "\\n"."""
    return text.replace("\u2028", "\n").split("\n")


def too_long(cues: list[dict], max_chars: int) -> list[str]:
    return [l for c in cues for l in _cue_lines(c["text"]) if len(l) > max_chars]


def srt(cues: list[dict]) -> str:
    from .subtitles import _srt_ts
    return "".join(f"{i}\n{_srt_ts(c['start'])} --> {_srt_ts(c['end'])}\n{c['text']}\n\n"
                   for i, c in enumerate(cues, 1))


# --- live Resolve ----------------------------------------------------------------------------

def _resolve():
    import os
    import sys

    from .export import _resolve_paths
    mod, lib = _resolve_paths()
    os.environ.setdefault("RESOLVE_SCRIPT_API", str(Path(mod).parent))
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", lib)
    sys.path.append(mod)
    import DaVinciResolveScript as dvr  # type: ignore
    r = dvr.scriptapp("Resolve")
    if not r:
        raise SystemExit("Resolve not reachable (open it; Preferences > System > General > External scripting: Local)")
    rp = r.GetProjectManager().GetCurrentProject()
    if not rp:
        raise SystemExit("no project open in Resolve")
    return r, rp


def _timeline_words(tlo, by_path: dict, load_words) -> list[dict]:
    """Transcript words on this timeline's A1, in timeline seconds. Source offsets come from
    GetLeftOffset at the media's own rate (GetSourceStartTime is camera-timecode absolute)."""
    fps = float(tlo.GetSetting("timelineFrameRate"))
    start0 = tlo.GetStartFrame()
    out = []
    for it in tlo.GetItemListInTrack("audio", 1) or []:
        mpi = it.GetMediaPoolItem()
        sid = by_path.get(mpi.GetClipProperty("File Path")) if mpi else None
        if not sid:
            continue
        src_fps = float(mpi.GetClipProperty("FPS") or fps)
        s_in = it.GetLeftOffset() / src_fps
        dur = it.GetDuration() / fps
        rec = (it.GetStart() - start0) / fps
        for w in load_words(sid):
            if s_in <= w["start"] < s_in + dur:
                out.append({"word": w["word"], "start": round(rec + w["start"] - s_in, 3)})
    return sorted(out, key=lambda w: w["start"])


BIN = "editassist legendas"


def _bin(mp):
    root = mp.GetRootFolder()
    return next((f for f in root.GetSubFolderList() or [] if f.GetName() == BIN), None) or mp.AddSubFolder(root, BIN)


def _place(tlo, mp, out_dir: Path, name: str, body: str, want_first: int) -> int:
    """Import `body` as an .srt and put it on subtitle track 1 at its own times; returns cues placed.
    A pool .srt keeps the cues of its first import, so each body gets a copy named by its content."""
    fresh = out_dir / "_import" / f"{name} {hashlib.sha1(body.encode()).hexdigest()[:8]}.srt"
    fresh.parent.mkdir(exist_ok=True)
    fresh.write_text(body, encoding="utf-8")
    was = mp.GetCurrentFolder()
    mp.SetCurrentFolder(_bin(mp))  # ImportMedia lands in the selected bin (it was the user's timelines bin)
    sub = (mp.ImportMedia([str(fresh)]) or [None])[0]
    if was:
        mp.SetCurrentFolder(was)
    if not sub:
        return 0
    for _ in range(2):  # an .srt lands at the PLAYHEAD; re-place once if it moved (see resolve_native)
        tlo.SetCurrentTimecode(tlo.GetStartTimecode())
        mp.AppendToTimeline([sub])
        placed = tlo.GetItemListInTrack("subtitle", 1) or []
        first = min((i.GetStart() for i in placed), default=None)
        if first is not None and abs(first - want_first) <= 2:
            return len(placed)
        if placed:
            tlo.DeleteClips(placed, False)
    return 0


def run(names: list[str], match: str | None, out_dir: Path, project_dir: str | None = None,
        max_chars: int = 15, max_lines: int = 2, dry_run: bool = False, restore: bool = False) -> dict:
    """Reflow the subtitle track 1 of each named (or `match`-ing) timeline in the open Resolve project.
    `restore`: put back the cues saved in <out_dir>/antes/<timeline>.srt by an earlier run (undo)."""
    r, rp = _resolve()
    by_path, load_words = {}, lambda sid: []
    if project_dir:
        from .ingest import media_by_id
        from .project import Project
        from .transcribe import words
        pr = Project(project_dir)
        by_path = {m["path"]: sid for sid, m in media_by_id(pr).items()}
        load_words = lambda sid: words(pr, sid)  # noqa: E731
    tls = [rp.GetTimelineByIndex(i + 1) for i in range(rp.GetTimelineCount())]
    pick = [t for t in tls if t and (t.GetName() in names or (match and re.search(match, t.GetName())))]
    missing = [n for n in names if n not in {t.GetName() for t in pick}]
    was = rp.GetCurrentTimeline()
    mp = rp.GetMediaPool()
    out_dir = out_dir.resolve()  # Resolve keeps a relative ImportMedia path as is and then reads no cues
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"timelines": [], "missing": missing, "dry_run": dry_run}
    for tlo in pick:
        name = tlo.GetName()
        rp.SetCurrentTimeline(tlo)
        fps = float(tlo.GetSetting("timelineFrameRate"))
        start0 = tlo.GetStartFrame()
        items = tlo.GetItemListInTrack("subtitle", 1) or []
        cues = [{"start": (i.GetStart() - start0) / fps, "end": (i.GetEnd() - start0) / fps,
                 "text": "\n".join(_cue_lines(i.GetName()))} for i in items]
        entry = {"timeline": name, "cues_before": len(cues)}
        if restore:
            old = out_dir / "antes" / f"{name}.srt"
            if not old.exists():
                report["timelines"].append(entry | {"skipped": f"no {old}"})
                continue
            body = old.read_text(encoding="utf-8")
            first = re.search(r"(\d+):(\d+):(\d+),(\d+)\s*-->", body)
            secs = int(first[1]) * 3600 + int(first[2]) * 60 + int(first[3]) + int(first[4]) / 1000
            if not dry_run:
                tlo.DeleteClips(items, False)
                entry["cues_placed"] = _place(tlo, mp, out_dir, name, body, start0 + round(secs * fps))
            report["timelines"].append(entry | {"restored": str(old)})
            continue
        if not cues:
            report["timelines"].append(entry | {"skipped": "no subtitles on track 1"})
            continue
        if not too_long(cues, max_chars) and all(c["text"].count("\n") < max_lines for c in cues):
            report["timelines"].append(entry | {"skipped": f"already <= {max_chars} chars per line"})
            continue
        ws = _timeline_words(tlo, by_path, load_words)
        new = reflow(cues, ws, max_chars, max_lines)
        body = srt(new)
        dst = out_dir / f"{name}.srt"
        dst.write_text(body, encoding="utf-8")
        entry |= {"cues_after": len(new), "srt": str(dst), "timed_from_words": bool(ws),
                  "long_words": too_long(new, max_chars)}
        if dry_run:
            report["timelines"].append(entry)
            continue
        old = out_dir / "antes" / f"{name}.srt"  # the cues as they were, to put back by hand or on failure
        old.parent.mkdir(exist_ok=True)
        if not old.exists():  # a second pass (2 lines -> 1) must keep the ORIGINAL cues, not the first pass
            old.write_text(srt(cues), encoding="utf-8")
        tlo.DeleteClips(items, False)
        n = _place(tlo, mp, out_dir, name, body, start0 + round(new[0]["start"] * fps))
        entry["cues_placed"] = n
        if n != len(new):
            back = _place(tlo, mp, out_dir, name, srt(cues), start0 + round(cues[0]["start"] * fps))
            entry["failed"] = (f"placed {n} cues, expected {len(new)}; original cues put back: {back}/{len(cues)}"
                               f" (also in {old})")
        report["timelines"].append(entry)
    if was:
        rp.SetCurrentTimeline(was)
    if not dry_run:
        r.GetProjectManager().SaveProject()
    return report
