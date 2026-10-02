---
name: silence-cut
description: Remove dead air and hesitation sounds (uh, um, hum, ãh) from talking footage, producing a tight jump-cut timeline. Use for "remove silences", "tighten this", "jump cut", podcasts, vlogs.
---
# silence-cut

`uv run ea silence-cut <p> [--media id1 id2] [--min-silence 0.45] [--pad 0.08] [--keep-fillers]`

- Builds V1+A1 from speech only, in the order of `--media` (default: all source clips).
- `--min-silence`: pauses longer than this are cut. 0.3 = aggressive (shorts), 0.45 default,
  0.7 = relaxed (interviews, emotional content). Check `<memory>/preferences.md` for the user's value.
- `--pad`: breathing room around words. Below 0.05 clips consonants.
- The filler list only has hesitation sounds. Words like "tipo", "né", "like", "so" are removed
  only by reading the transcript and editing timeline.json (or using rough-cut segments), because
  they are sometimes meaningful.
- Then run `uv run ea qa <p>`: "splits the word" warnings mean a cut landed mid-word; widen that
  clip's in/out by ~0.05s.
