---
name: subtitles
description: Captions synced to the EDITED timeline. SRT for the NLE, styled ASS for burn-in, word-by-word highlight, or animated Remotion captions. Use for "add captions/subtitles/legendas".
---
# subtitles

`uv run ea subtitles <p> [--style clean|bold|boxed] [--max-words 4] [--no-karaoke] [--fix "heard=right" ...]`

- Lines break on phrases (after commas, never ending on "o/a/de/na..."). Read every line before
  delivering; polish the few bad splits with `--lines` (from work/captions.json) + `--name`.
- `--fix "loud control=launch control"`: vocabulary fixes on the edited words (multi-word, kept as one
  caption token; empty right side drops the words). Lone 1-2 letter words in noise are dropped.
- The user's caption look for burn-in: `--font <file> --weight SemiBold --size <% of short side>
  --y <0..1 from top> [--no-stroke] [--shadow]` (saved in work/caption_style.json). In Resolve the
  look lives on the subtitle TRACK and no API sets it: build with `ea export --open --current
  --template "<a timeline whose subtitle track the user already styled>"` (export-nle).
- Run AFTER the cut is final: captions are remapped from source words through timeline.json; re-run
  after any edit.
- `clean`: bottom, sentence case (YouTube). `bold`: centre, uppercase, highlighted word (shorts).
  `boxed`: bottom with dark box (accessibility). Use the user's style from memory when set.
- `--max-words`: 2-3 for shorts, 5-7 for long-form. Vertical frames: sizes follow the short side and
  long lines shrink to fit; still check a rendered frame.
- Accent colour of the highlighted word: set `"accent": "#RRGGBB"` in `work/captions.json` (burn-in
  path) and the `\c&HBBGGRR&` highlight in the .ass. Match titles/brand.
- Misheard words (têm/tem, missing commas, names): fix them in `work/transcripts/<id>.json` and re-run,
  not by hand in the .srt/.ass (render burns from `work/captions.json`, which a re-run overwrites).
- Outputs: `output/<name>.srt` (import as subtitle track; exported alongside NLE projects),
  `output/<name>.ass`, `work/captions.json`.
- Burn in: `uv run ea render <p> --subs output/<name>.ass` (works with or without libass in ffmpeg).
- Animated captions: `uv run ea motion <p> Captions` renders a transparent overlay from captions.json;
  put it on V2 (see motion-graphics).
- Speakers: after the speakers skill, caption lines never mix two people.
- Other languages: translate-dub skill (`--lines` + `--name`).
- Captions apply the user's dictionary (`<memory>/vocabulary.md`) automatically. Read every caption
  line; a misheard word you find = `uv run ea vocab <p> --add "heard=right" --apply`, then re-run
  subtitles (the dictionary grows, so the next project gets it right too). `--fix` is only for one-off
  changes that should NOT be remembered.
