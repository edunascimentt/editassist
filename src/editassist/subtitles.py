"""subtitles: captions that follow the EDITED timeline (source words remapped through the cut).

Writes output/<name>.srt (import into any NLE) and output/<name>.ass (styled, used for burn-in),
plus work/captions.json (word list on timeline time; feeds the Remotion caption template).
"""
from __future__ import annotations

import unicodedata

from . import timeline as T
from .ingest import media_by_id
from .project import Project, read_json, write_json
from .transcribe import words

STYLES = {
    # name: (font, size as % of height, primary, outline, highlight, bold, uppercase, position)
    "clean":  ("Montserrat Bold", 4.6, "&H00FFFFFF", "&H00000000", "&H0000E5FF", 1, False, 2),
    "bold":   ("Montserrat Black", 6.0, "&H00FFFFFF", "&H00000000", "&H0000E5FF", 1, True, 5),
    "boxed":  ("Montserrat Bold", 4.4, "&H00FFFFFF", "&H80000000", "&H0000E5FF", 1, False, 2),
}


def timeline_words(project: Project, tl: dict) -> list[dict]:
    """Every surviving word with timeline times, in order."""
    by_path = {m["path"]: sid for sid, m in media_by_id(project).items()}
    out = []
    for c in sorted(T.track(tl, "A1")["clips"], key=lambda c: c["start"]):
        sid = by_path.get(c["media"])
        if not sid:
            continue
        for w in words(project, sid):
            mid = (w["start"] + w["end"]) / 2
            # a word that starts inside the kept audio is heard even when Whisper stretched its end
            # over the following pause (its midpoint then falls after the cut)
            if c["in"] <= mid <= c["out"] or c["in"] <= w["start"] <= c["out"] - 0.05:
                sp = c.get("speed", 1.0)
                a = c["start"] + (max(w["start"], c["in"]) - c["in"]) / sp
                b = c["start"] + (min(w["end"], c["out"]) - c["in"]) / sp
                item = {"word": unicodedata.normalize("NFC", w["word"]), "start": round(a, 3), "end": round(max(b, a + 0.05), 3)}
                if w.get("speaker"):
                    item["speaker"] = w["speaker"]
                out.append(item)
    return out


# short words a caption line should not end on: they belong to what follows ("na | casa" reads badly)
CLINGY = {"o", "a", "os", "as", "um", "uma", "de", "da", "do", "das", "dos", "na", "no", "nas", "nos", "em",
          "e", "que", "pra", "para", "por", "com", "se", "ao", "à", "mais", "the", "an", "of", "to", "in",
          "on", "and", "for", "with", "at", "el", "la", "los", "las", "y", "en", "del", "como"}


def _num(t: str) -> bool:
    return t[:1].isdigit()


def _clings(last: dict, nxt: dict) -> bool:
    """`last` belongs on the next line: a function word, or a word glued to a number ("Stage 2",
    "600 cavalos")."""
    t = last["word"]
    if t.endswith((",", ".", "!", "?", ";", ":")):
        return False
    return t.lower() in CLINGY or _num(t) or _num(nxt["word"])


def group(ws: list[dict], max_words: int = 4, max_chars: int = 28, max_gap: float = 0.6,
          phrase: bool = True) -> list[dict]:
    """Words -> caption lines. `phrase`: also break after a comma, and never end a line on a short
    function word when it can move to the next line."""
    lines, cur = [], []
    for w in ws:
        text = " ".join(x["word"] for x in cur + [w])
        brk = cur and (len(cur) >= max_words or len(text) > max_chars or w["start"] - cur[-1]["end"] > max_gap
                       or cur[-1]["word"].endswith((".", "?", "!")) or cur[-1].get("speaker") != w.get("speaker")
                       or (phrase and cur[-1]["word"].endswith((",", ";", ":"))))
        if brk:
            carry = []
            while phrase and len(cur) > 1 and len(carry) < 2 and _clings(cur[-1], carry[0] if carry else w) \
                    and w["start"] - cur[-1]["end"] <= max_gap \
                    and not (len(cur) == 2 and cur[0]["word"].lower() in CLINGY):  # no lone "o" line
                carry.insert(0, cur.pop())
            lines.append(cur)
            cur = carry
        cur.append(w)
    if cur:
        lines.append(cur)
    return [{"start": l[0]["start"], "end": l[-1]["end"], "words": l,
             **({"speaker": l[0]["speaker"]} if l[0].get("speaker") else {})} for l in lines]


def sentences(ws: list[dict], max_gap: float = 1.2) -> list[dict]:
    """Timeline words -> sentences (for reading, chapters, translation)."""
    out, cur = [], []
    for w in ws:
        if cur and (w["start"] - cur[-1]["end"] > max_gap or cur[-1].get("speaker") != w.get("speaker")):
            out.append(cur); cur = []
        cur.append(w)
        if w["word"].endswith((".", "?", "!")):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"], "text": " ".join(x["word"] for x in c),
             **({"speaker": c[0]["speaker"]} if c[0].get("speaker") else {})} for c in out]


def transcript(project: Project) -> dict:
    """Transcript of the EDITED video, timestamps on the timeline. Written to output/<name>_transcript.txt."""
    from .transcribe import fmt_ts

    tl = T.load(project)
    sents = sentences(timeline_words(project, tl))
    lines = [f"[{fmt_ts(s['start'])}]" + (f" [{s['speaker']}]" if s.get("speaker") else "") + f" {s['text']}" for s in sents]
    dst = project.path("output", f"{tl['name']}_transcript.txt")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(project.path("work", "timeline_transcript.json"), sents)
    return {"read": project.rel(dst), "sentences": len(sents), "length": round(T.length(tl), 2)}


def _srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_ts(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def apply_fixes(ws: list[dict], fixes: list[str]) -> list[dict]:
    """Vocabulary fixes "heard=right" (case-insensitive, multi-word, punctuation kept), e.g.
    "loud control=launch control", "prêmio=premium"; an empty right side drops the words."""
    import re

    out = list(ws)
    for f in fixes or []:
        if "=" not in f:
            raise SystemExit(f"--fix needs heard=right: {f!r}")
        old, new = (x.split() for x in f.split("=", 1))
        norm = lambda t: re.sub(r"[^\w]", "", t.lower())
        i = 0
        while i + len(old) <= len(out):
            if [norm(x["word"]) for x in out[i:i + len(old)]] == [norm(x) for x in old]:
                span = out[i:i + len(old)]
                tail = re.sub(r"^.*?([.,!?;:]*)$", r"\1", span[-1]["word"])
                if new and re.search(r"[.,!?;:]$", new[-1]):
                    tail = ""  # the right side brings its own punctuation
                if " ".join(x["word"] for x in span) == " ".join(new) + tail:
                    i += len(span)  # already right (case-only fixes, re-applied dictionaries)
                    continue
                a, b = span[0]["start"], span[-1]["end"]
                # the right side stays ONE caption token, so "launch control" never splits over two lines
                rep = [{**span[0], "word": " ".join(new) + tail, "start": a, "end": b}] if new else []
                out[i:i + len(old)] = rep
                i += max(len(rep), 1)
            else:
                i += 1
    return out


def drop_strays(ws: list[dict], gap: float = 2.0) -> list[dict]:
    """Whisper hallucinates lone short words in engine noise or music ("A" in the middle of a launch):
    a 1-2 letter word with silence on both sides (>= 0.8 s, one side >= `gap`) is not a caption."""
    out = []
    for i, w in enumerate(ws):
        before = w["start"] - ws[i - 1]["end"] if i else gap
        after = ws[i + 1]["start"] - w["end"] if i + 1 < len(ws) else gap
        if len(w["word"].strip(".,!?")) <= 2 and min(before, after) >= 0.8 and max(before, after) >= gap:
            continue
        out.append(w)
    return out


def build(project: Project, style: str = "clean", max_words: int = 4, karaoke: bool = True,
          out_name: str | None = None, fixes: list[str] | None = None) -> dict:
    from . import vocab

    tl = T.load(project)
    known = vocab.load(project.dir.name)  # the user's dictionary, then this call's fixes
    ws = drop_strays(apply_fixes(vocab.fix_words(timeline_words(project, tl), known["fixes"])[0], fixes))
    ws = vocab.keep_terms(ws, known["terms"])
    if not ws:
        raise SystemExit("no words on the timeline: transcribe first and make sure A1 has dialogue")
    lines = group(ws, max_words=max_words)
    return _write(project, lines, out_name or tl["name"], style, karaoke)


def from_lines(project: Project, lines_file: str, name: str, style: str = "clean") -> dict:
    """Captions from already-timed text, e.g. a translation the model wrote from
    work/timeline_transcript.json: [{"start", "end", "text"}] on timeline time."""
    from pathlib import Path

    src = Path(lines_file) if Path(lines_file).is_file() else project.path(lines_file)
    items = read_json(src)
    if not items:
        raise SystemExit(f"no lines in {lines_file}")
    lines = []
    for it in items:
        toks = it["text"].split()
        step = (it["end"] - it["start"]) / max(len(toks), 1)
        ws = [{"word": unicodedata.normalize("NFC", t), "start": round(it["start"] + i * step, 3),
               "end": round(it["start"] + (i + 1) * step, 3)} for i, t in enumerate(toks)]
        lines += group(ws, max_words=7, max_chars=42, max_gap=9)  # long sentences -> readable chunks
    return _write(project, lines, name, style, karaoke=False, captions_file=f"work/captions_{name}.json")


def _write(project: Project, lines: list[dict], name: str, style: str, karaoke: bool,
           captions_file: str = "work/captions.json") -> dict:
    tl = T.load(project)
    # don't let a line linger past the next one
    for a, b in zip(lines, lines[1:]):
        a["end"] = min(a["end"] + 0.25, b["start"])
    srt = "\n".join(f"{i}\n{_srt_ts(l['start'])} --> {_srt_ts(l['end'])}\n"
                    f"{' '.join(w['word'] for w in l['words'])}\n" for i, l in enumerate(lines, 1))
    srt_path = project.path("output", f"{name}.srt")
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text(srt, encoding="utf-8")

    font, size_pct, primary, outline, hi, bold, upper, align = STYLES.get(style, STYLES["clean"])
    W, H = tl["width"], tl["height"]
    size = int(min(W, H) * size_pct / 100)  # by the short side: vertical frames would overflow
    border_style, outline_w, shadow = (3, 8, 0) if style == "boxed" else (1, max(2, size // 12), 0)
    margin_v = int(H * (0.1 if align == 2 else 0.0))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{hi},{outline},&H80000000,{-1 if bold else 0},0,0,0,100,100,0,0,{border_style},{outline_w},{shadow},{align},{int(W*0.08)},{int(W*0.08)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for l in lines:
        txt = lambda w: (w["word"].upper() if upper else w["word"]).replace("{", "(").replace("}", ")")
        if karaoke:
            # one event per word: current word highlighted, rest plain
            for i, w in enumerate(l["words"]):
                a = w["start"] if i else l["start"]
                b = l["words"][i + 1]["start"] if i + 1 < len(l["words"]) else l["end"]
                parts = [("{\\c" + hi + "}" + txt(x) + "{\\c" + primary + "}") if j == i else txt(x)
                         for j, x in enumerate(l["words"])]
                events.append(f"Dialogue: 0,{_ass_ts(a)},{_ass_ts(b)},Default,,0,0,0,,{' '.join(parts)}")
        else:
            events.append(f"Dialogue: 0,{_ass_ts(l['start'])},{_ass_ts(l['end'])},Default,,0,0,0,,"
                          f"{' '.join(txt(w) for w in l['words'])}")
    ass_path = project.path("output", f"{name}.ass")
    ass_path.write_text(head + "\n".join(events) + "\n", encoding="utf-8")
    # stamped with the timeline it was made for: a project can hold several videos (timeline slots)
    write_json(project.path(*captions_file.split("/")),
               {"timeline": tl["name"], "style": style, "karaoke": karaoke, "lines": lines})
    return {"srt": project.rel(srt_path), "ass": project.rel(ass_path), "lines": len(lines),
            "words": sum(len(l["words"]) for l in lines)}
