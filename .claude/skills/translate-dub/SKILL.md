---
name: translate-dub
description: Versions in other languages. Translated subtitles (SRT/ASS, burn-in) written by you from the edited transcript, and optional ElevenLabs dubbing that keeps the speakers' voices. Use for "translate", "English subtitles", "legenda em inglês", "dub this", "versão em espanhol".
---
# translate-dub

**Translated subtitles** (no API cost):
1. `uv run ea transcript <p>` writes `work/timeline_transcript.json` (sentences on timeline time).
2. Translate each sentence yourself and keep `start`/`end`. Write `work/subs_<lang>.json`
   `[{"start", "end", "text"}]`. Translate meaning, not word order; keep names and brand terms; keep
   each sentence about as long as the original so reading speed works.
3. `uv run ea subtitles <p> --lines work/subs_<lang>.json --name <name>_<lang> [--style clean]`
   writes `output/<name>_<lang>.srt` and `.ass`.
4. Burn in: `uv run ea render <p> --preset youtube --subs output/<name>_<lang>.ass --out output/<name>_<lang>.mp4`.
   Or upload the SRT to YouTube as a caption track.

**Dubbing** (ElevenLabs, costs credits, confirm first):
1. Render the dialogue only: temporarily mute music/SFX (copy the timeline, drop those tracks), then
   `uv run ea render <p> --preset youtube --out output/<name>_dialog.mp4`, and restore the timeline.
2. `uv run ea dub <p> --lang en --source output/<name>_dialog.mp4 [--speakers 2]`. Waits for the dub and
   registers `work/dub/<name>_en.mp4`.
3. Make the language version: copy the project timeline, replace A1 with one clip of the dubbed
   file's audio (start 0, in 0, out = length), keep music/SFX, render. Re-check lip-sync-sensitive close-ups.
