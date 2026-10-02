---
name: subtitles
description: Captions synced to the EDITED timeline. SRT for the NLE, styled ASS for burn-in, word-by-word highlight, or animated Remotion captions. Use for "add captions/subtitles/legendas".
---
# subtitles

`uv run ea subtitles <p> [--style clean|bold|boxed] [--max-words 4] [--no-karaoke]`

- Run AFTER the cut is final: captions are remapped from source words through timeline.json; re-run
  after any edit.
- `clean`: bottom, sentence case (YouTube). `bold`: centre, uppercase, highlighted word (shorts).
  `boxed`: bottom with dark box (accessibility). Use the user's style from memory when set.
- `--max-words`: 2-3 for shorts, 5-7 for long-form.
- Outputs: `output/<name>.srt` (import as subtitle track; exported alongside NLE projects),
  `output/<name>.ass`, `work/captions.json`.
- Burn in: `uv run ea render <p> --subs output/<name>.ass` (works with or without libass in ffmpeg).
- Animated captions: `uv run ea motion <p> Captions` renders a transparent overlay from captions.json;
  put it on V2 (see motion-graphics).
- Speakers: after the speakers skill, caption lines never mix two people.
- Other languages: translate-dub skill (`--lines` + `--name`).
- Check spelling of names/brands against `<memory>/preferences.md` "Vocabulary"; fix in
  `work/transcripts/<id>.json` and re-run.
