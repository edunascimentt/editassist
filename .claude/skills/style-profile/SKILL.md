---
name: style-profile
description: Maintain the user's editing memory (<memory>/preferences.md, per-client <memory>/clients/<client>/preferences.md, <memory>/styles/*.md): pacing, caption style, music taste, loudness, brand colours, vocabulary, NLE of choice. Decides whether a note is general or about one client and saves it in the right file. Use when the user states a preference, corrects a recurring choice, says "esse cliente não gosta de...", or asks to learn their (or a client's) style from a previous video.
---
# style-profile

`<memory>` = the folder `uv run ea memory` prints: the user's PRIVATE memory-os global tier
(`~/.memory-os/memory/editassist/`, shared by all their Claude accounts, never committed), or the
gitignored `memory/` fallback when memory-os isn't installed. Missing files: `uv run ea memory --init`.

Files:
- `<memory>/preferences.md`: defaults for every edit, one bullet each, newest wins.
- `<memory>/clients/<client>/preferences.md`: one client's house style and taste (Acme, Ana
  Souza...). Overrides the general file on that client's projects. `uv run ea client list | new | set | show`.
- `<memory>/styles/<name>.md`: named looks ("podcast", "shorts-brand-x"); the user says
  "use the podcast style".
- `<memory>/log.md`: one dated line per delivered project (what, length, notable decisions).

General or client? Every time you write a preference, decide first (`uv run ea client show <p>` says
whose project it is):
- Client file: about THIS client: their brand (logo, colours, fonts), format and structure (length,
  intro, sting), their music/tracks, their people and names, their audience/platform, what the client
  asked for or rejected ("a Ana não gosta de zoom", "pra ela sempre legenda amarela").
- General file: about editing itself, true for any video: cut quality (mid-word, holes, sync), audio
  levels, stabilisation, NLE habits (bins, template timelines), the user's own tools and fonts, "sempre"
  / "nunca" said without the client in mind.
- Unclear (a look, a pace, a caption size said during one client's video): ask once, short: "Isso vale
  só pro <cliente> ou pra todos os vídeos?". Never guess silently.
- Tell the user where you saved it ("salvei nas preferências da Ana Souza"). A client file wins
  over the general one only on that client's projects; when a client rule repeats across 2+ clients,
  offer to promote it to the general file.
- New client: `uv run ea new <p> --client "<Name>"` or `uv run ea client set <p> "<Name>"` (creates the
  folder from the template). Words Whisper gets wrong only for them: `ea vocab --scope <client-slug>`.

Rules:
- Write when the user expresses a durable preference or corrects the same thing twice. Quote them
  briefly and date it: `- Silence cut min 0.3s for shorts (2026-10-01, "corta mais seco")`.
- Edit the existing line instead of appending a contradiction.
- Never store API keys or personal data about third parties (a client's taste and brand are fine;
  their phone, address, documents are not).
- Taste goes here; facts about how the editassist CODE works go to `.claude/_memory/` (shared project
  tier: facts.md gotchas, decisions.md), following its rules. Never write the user's taste there.

Learning from a reference video: put it in a project's `input/`, ingest + transcribe + scenes, then
measure: average shot length (scenes), words per caption line and caption position (look at frames),
pause length between sentences (transcript gaps), music presence, loudness
(`ffmpeg -i f -af ebur128 -f null -`). Write the findings as a style file (a client's reference
video: into `clients/<client>/preferences.md`) and confirm with the user.
