---
name: style-profile
description: Maintain the user's editing memory (memory/preferences.md and memory/styles/*.md): pacing, caption style, music taste, loudness, brand colours, vocabulary, NLE of choice. Use when the user states a preference, corrects a recurring choice, or asks to learn their style from a previous video.
---
# style-profile

Files (personal, gitignored, created by setup from `memory.template/`):
- `memory/preferences.md`: defaults for every edit, one bullet each, newest wins.
- `memory/styles/<name>.md`: named looks ("podcast", "shorts-brand-x"); the user says
  "use the podcast style".
- `memory/log.md`: one dated line per delivered project (what, length, notable decisions).

Rules:
- Write when the user expresses a durable preference or corrects the same thing twice. Quote them
  briefly and date it: `- Silence cut min 0.3s for shorts (2026-10-01, "corta mais seco")`.
- Edit the existing line instead of appending a contradiction.
- Never store API keys or personal data about third parties.

Learning from a reference video: put it in a project's `input/`, ingest + transcribe + scenes, then
measure: average shot length (scenes), words per caption line and caption position (look at frames),
pause length between sentences (transcript gaps), music presence, loudness
(`ffmpeg -i f -af ebur128 -f null -`). Write the findings as a style file and confirm with the user.
