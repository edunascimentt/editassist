---
name: review
description: Apply the user's feedback on a preview or NLE pass ("cut the part about X", "faster pace", "captions bigger", "at 1:23 remove that") and learn from it. Use whenever the user reacts to a version.
---
# review

1. Map each note to the timeline: timestamps refer to the PREVIEW (timeline time).
   `uv run ea transcript <p>` shows what is said at each timeline time; `ea timeline <p> json` shows
   the clip covering t (start <= t < start + (out - in)). After removing material, `ea timeline <p> ripple`
   closes the gap.
   Content notes ("the part about pricing"): find it in the transcript with `ea find`.
2. Edit `timeline.json` (or segments.json + `ea cut` for structural changes). Keep a copy before big
   changes: `timeline.v<N>.json` in the project folder.
3. Re-run what depends on the change: subtitles after any cut, reformat --bake if clips changed,
   qa, preview.
4. Reply with what changed, per note.
5. **Learn**: if the note is a general taste ("I always want tighter cuts", "never use that font"),
   record it in `memory/preferences.md` right away (style-profile skill). One-off fixes are not
   preferences.
