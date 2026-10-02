---
name: style-profile
description: Maintain the user's editing memory (<memory>/preferences.md and <memory>/styles/*.md): pacing, caption style, music taste, loudness, brand colours, vocabulary, NLE of choice. Use when the user states a preference, corrects a recurring choice, or asks to learn their style from a previous video.
---
# style-profile

`<memory>` = the folder `uv run ea memory` prints: the user's PRIVATE memory-os global tier
(`~/.memory-os/memory/editassist/`, shared by all their Claude accounts, never committed), or the
gitignored `memory/` fallback when memory-os isn't installed. Missing files: `uv run ea memory --init`.

Files:
- `<memory>/preferences.md`: defaults for every edit, one bullet each, newest wins.
- `<memory>/styles/<name>.md`: named looks ("podcast", "shorts-brand-x"); the user says
  "use the podcast style".
- `<memory>/log.md`: one dated line per delivered project (what, length, notable decisions).

Rules:
- Write when the user expresses a durable preference or corrects the same thing twice. Quote them
  briefly and date it: `- Silence cut min 0.3s for shorts (2026-10-01, "corta mais seco")`.
- Edit the existing line instead of appending a contradiction.
- Never store API keys or personal data about third parties.
- Taste goes here; facts about how the editassist CODE works go to `.claude/_memory/` (shared project
  tier: facts.md gotchas, decisions.md), following its rules. Never write the user's taste there.

Learning from a reference video: put it in a project's `input/`, ingest + transcribe + scenes, then
measure: average shot length (scenes), words per caption line and caption position (look at frames),
pause length between sentences (transcript gaps), music presence, loudness
(`ffmpeg -i f -af ebur128 -f null -`). Write the findings as a style file and confirm with the user.
