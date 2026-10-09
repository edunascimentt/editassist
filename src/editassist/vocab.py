"""vocab: the user's transcription dictionary, <memory>/vocabulary.md.

Whisper keeps mishearing the same names and terms ("Camoriú" for Camboriú, "loud control" for launch
control). Every correction goes into one file in the user's private editing memory, and from then on:
  - `ea transcribe` biases Whisper toward the right spellings (hotwords) and fixes every new transcript;
  - `ea vocab <project> --apply` fixes transcripts that already exist (json + txt, no re-transcribing);
  - `ea subtitles` applies it again on the edited words, so captions never show a known mistake.

File format (hand-editable markdown):

    ## Fixes
    - Camoriú = Camboriú  (2026-10-08, inauguração conselho tutelar)
    - prêmio = premium [vulcano]      <- [scope]: only in projects whose name contains it
    - loud control = launch control
    ## Terms
    - Balneário Camboriú              <- right spellings Whisper should know (names, brands)
"""
from __future__ import annotations

import re
from datetime import date

from .project import Project, memory_dir, read_json, write_json

HEADER = """# Transcription dictionary

> Read by `ea transcribe`, `ea vocab --apply` and `ea subtitles`. Add a line every time Whisper gets a
> word wrong (`uv run ea vocab --add "heard=right" --note "..."`). `[scope]` limits a fix to projects
> whose name contains it (for words that are only wrong for one client).

## Fixes

## Terms
"""

FIX_RE = re.compile(r"^-\s*(.+?)\s*=\s*(.*?)\s*(?:\[([^\]]+)\])?\s*(?:\((.*)\))?\s*$")


def path():
    return memory_dir() / "vocabulary.md"


def load(project_name: str | None = None) -> dict:
    """{"fixes": ["heard=right", ...], "terms": [...]} for this project (scoped fixes filtered)."""
    f = path()
    fixes, terms, section = [], [], None
    if not f.exists():
        return {"fixes": fixes, "terms": terms}
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip().lower()
            continue
        if not s.startswith("- "):
            continue
        if section == "fixes":
            m = FIX_RE.match(s)
            if not m or not m.group(1):
                continue
            heard, right, scope = m.group(1), m.group(2), m.group(3)
            if scope and (not project_name or scope.strip().lower() not in project_name.lower()):
                continue
            fixes.append(f"{heard}={right}")
        elif section == "terms":
            term = re.sub(r"\s*\(.*\)\s*$", "", s[2:]).strip()
            if term:
                terms.append(term)
    return {"fixes": fixes, "terms": terms}


def add(fixes: list[str] | None = None, terms: list[str] | None = None, note: str | None = None,
        scope: str | None = None) -> dict:
    """Append fixes ("heard=right") and terms; an existing fix for the same heard words is replaced."""
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    text = f.read_text(encoding="utf-8") if f.exists() else HEADER
    lines = text.splitlines()
    if "## Fixes" not in text:
        lines += ["", "## Fixes"]
    if "## Terms" not in text:
        lines += ["", "## Terms"]
    stamp = f"  ({date.today().isoformat()}{', ' + note if note else ''})"
    added = []
    for fx in fixes or []:
        if "=" not in fx:
            raise SystemExit(f"--add needs heard=right: {fx!r}")
        heard, right = (x.strip() for x in fx.split("=", 1))
        key = heard.lower()
        lines = [ln for ln in lines
                 if not ((m := FIX_RE.match(ln.strip())) and m.group(1).lower() == key
                         and (m.group(3) or None) == scope)]
        i = lines.index("## Fixes") + 1
        while i < len(lines) and lines[i].strip().startswith("- "):
            i += 1
        lines.insert(i, f"- {heard} = {right}{f' [{scope}]' if scope else ''}{stamp}")
        added.append(f"{heard}={right}")
    have = {t.lower() for t in load()["terms"]}
    for t in terms or []:
        if t.lower() in have:
            continue
        i = lines.index("## Terms") + 1
        while i < len(lines) and lines[i].strip().startswith("- "):
            i += 1
        lines.insert(i, f"- {t}")
        added.append(t)
    f.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"file": str(f), "added": added}


def hotwords(project_name: str | None = None) -> str | None:
    """Right spellings to bias Whisper toward: the terms plus capitalised right sides of fixes."""
    v = load(project_name)
    words = list(v["terms"])
    for fx in v["fixes"]:
        right = fx.split("=", 1)[1].strip()
        if right[:1].isupper() and right not in words:
            words.append(right)
    return " ".join(words) or None


def fix_words(ws: list[dict], fixes: list[str]) -> tuple[list[dict], int]:
    """Apply fixes to a word list; returns (words, number of replacements). A capitalised heard word
    keeps its capital ("Prêmio" -> "Premium")."""
    from .subtitles import apply_fixes

    n = 0
    out = list(ws)
    for fx in fixes:
        before = out
        out = apply_fixes(out, [fx])
        if out != before:
            right = fx.split("=", 1)[1].strip()
            changed = [w for w in out if w not in before]
            n += len(changed) or 1
            for w in changed:
                orig = next((b for b in before if b["start"] == w["start"]), None)
                if orig and orig["word"][:1].isupper() and right[:1].islower():
                    w["word"] = w["word"][:1].upper() + w["word"][1:]
    return out, n


def keep_terms(ws: list[dict], terms: list[str]) -> list[dict]:
    """Join multi-word dictionary terms ("Conselho Tutelar") into one caption token, so a caption line
    never breaks inside a name ("do Conselho | Tutelar.")."""
    norm = lambda t: re.sub(r"[^\w]", "", t.lower())
    multi = sorted((t.split() for t in terms if len(t.split()) > 1), key=len, reverse=True)
    out, i = [], 0
    while i < len(ws):
        for term in multi:
            span = ws[i:i + len(term)]
            if len(span) == len(term) and [norm(w["word"]) for w in span] == [norm(x) for x in term]:
                out.append({**span[0], "word": " ".join(w["word"] for w in span), "end": span[-1]["end"]})
                i += len(term)
                break
        else:
            out.append(ws[i])
            i += 1
    return out


def fix_transcript(t: dict, fixes: list[str]) -> int:
    """Fix every segment of a transcript dict in place; segment text is rebuilt from fixed words."""
    total = 0
    for sg in t.get("segments", []):
        if not sg.get("words"):
            continue
        ws, n = fix_words(sg["words"], fixes)
        if n:
            sg["words"] = ws
            sg["text"] = " ".join(w["word"] for w in ws)
            total += n
    return total


def apply_project(project: Project) -> dict:
    """Re-apply the dictionary to every existing transcript of a project (json and txt)."""
    from .transcribe import write_txt

    fixes = load(project.dir.name)["fixes"]
    changed = {}
    for f in sorted(project.path("work", "transcripts").glob("*.json")):
        t = read_json(f)
        n = fix_transcript(t, fixes)
        if n:
            write_json(f, t)
            write_txt(f.with_suffix(".txt"), t["segments"])
            changed[f.stem] = n
    return {"fixes": len(fixes), "changed": changed}
