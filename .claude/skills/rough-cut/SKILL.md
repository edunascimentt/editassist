---
name: rough-cut
description: Build a first cut from the user's goal or script by choosing the best bites from the transcripts (story order, best takes, hook first). Use for "make a rough cut", "edit this into a 5 min video", "follow this script", "pick the best takes".
---
# rough-cut

1. Requirements: ingest + transcribe done. Read every `work/transcripts/*.txt`.
2. Understand the brief: target length, audience, platform, tone. Ask only if the length or goal
   is unclear and not in memory.
3. Plan the story: hook (first 3-5 s), setup, body, payoff/CTA. With repeated takes of the same
   line, pick the cleanest delivery (fewer stumbles, more energy; check word `prob` in the json for
   mumbles) and say which take you chose.
4. Write `work/segments.json` (list, in timeline order). Quote the transcript so times snap to words:
   ```json
   [{"media": "cam_a", "from": "first words of bite", "to": "last words of bite", "note": "hook"},
    {"media": "cam_a", "in": 61.2, "out": 74.9, "note": "explicit times also work"}]
   ```
   Use `uv run ea find <p> "phrase"` when a quote is ambiguous (it returns every match).
5. `uv run ea cut <p> work/segments.json [--tighten]` (`--tighten` also removes pauses inside bites).
6. `uv run ea timeline <p>` for length; adjust segments until it fits the target.
7. Preview + summary: list the bites with one line each on why they are there.

Padding (`pad`, default 0.08 s) never reaches into the neighbouring words, so a bite doesn't start
with the tail of the previous sentence ("ali Eu quero...").

Several cameras or a separate audio recorder: multicam skill (`ea sync` aligns them by sound,
swaps in the clean mic, switches angles). Interviews and podcasts: run the speakers skill first,
so the transcript says who speaks when.
