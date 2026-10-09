---
name: transcribe
description: Word-level transcription of every clip with audio (faster-whisper). Needed by rough-cut, silence-cut, subtitles, highlight and qa. Use after ingest or when transcripts are missing.
---
# transcribe

`uv run ea transcribe <p> [--language pt] [--model large-v3-turbo] [--only id1 id2] [--force]`

- Default model `large-v3-turbo` (good accuracy and speed on CPU). Override per machine with
  `EA_WHISPER_MODEL` in `.env` (`small` for quick drafts, `large-v3` for hard audio).
- Set `--language` when known: autodetect on short clips misfires.
- Outputs `work/transcripts/<id>.json` (word times) and `<id>.txt` (read this one).
- If it prints "speech-like audio with no words at [...]", Whisper dropped a passage: listen there
  (render a 5 s preview) and re-run that clip with `--force --model large-v3`.
- Transcription dictionary `<memory>/vocabulary.md` (the user's request, 2026-10-08: "sempre que tu
  ver que algo tava errado ... vai la e corrige"): `ea transcribe` biases Whisper toward its terms and
  fixes every new transcript with it. After transcribing, READ the `.txt` files looking for misheard
  names, places, brands and terms; for EVERY one you spot (or the user points out), right away:
  `uv run ea vocab <p> --add "heard=right" [--term "Right Name"] --note "<project>" --apply`
  (`--scope <client>` when the "wrong" word is a real word elsewhere, e.g. prêmio). `--apply` fixes the
  project's existing transcripts; never fix only the .srt or one json by hand.
