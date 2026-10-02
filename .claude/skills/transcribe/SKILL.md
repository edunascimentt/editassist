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
- After transcribing, skim the `.txt`. Fix recurring proper-noun errors (brands, names) by noting
  them in `<memory>/preferences.md` under "Vocabulary" so captions use the right spelling; correct the
  word in the json too when it will appear on screen.
