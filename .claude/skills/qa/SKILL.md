---
name: qa
description: Automatic quality checks before showing or delivering an edit (missing media, overlaps, gaps, flash frames, cuts mid-word, caption timing, loudness, peaks, black frames). Use before every preview you hand over and before export.
---
# qa

`uv run ea qa <p> [--render output/<file>.mp4 --preset youtube]`

- `error`: fix before anything else. `warn`: fix unless intentional (say so). `info`: mention.
- Mid-word cuts: move that clip's in/out to the word boundary from `work/transcripts/<id>.json`.
- Gaps on V1 render as black: close them (ripple) or cover with b-roll.
- "audio ends before the picture" / "render silent": a music bed or a track was cut short; fix before
  handing over (a silent end card is easy to miss when you can't listen).
- Loudness off target: check gain_db on music/sfx, re-render with the right preset.
- Also watch the preview yourself where possible: sample frames with ffmpeg at cut points and look
  at them (`ffmpeg -ss <t> -i <file> -frames:v 1 work/qa_<t>.jpg`).
