---
name: speakers
description: Who speaks when (speaker diarization). Labels every transcript word with the speaker, so captions break per speaker, multicam follows the speaker, and highlights credit people. Use for podcasts, interviews, panels, "label the speakers".
---
# speakers

- **One mic per person** (best, no extra install):
  `uv run ea diarize <p> <transcribed media id> --tracks Ana=mic_ana Bruno=mic_bruno`
  It aligns the mics automatically if `ea sync` hasn't been run, then gives each word to the
  loudest mic, normalised per mic so bleed doesn't win.
- **One mixed recording**: `uv sync --extra diarize` (PyTorch, ~2 GB, one-time), set `HF_TOKEN` in `.env`
  (accept the terms of pyannote/speaker-diarization-3.1 on Hugging Face), then
  `uv run ea diarize <p> <id> [--speakers 2] [--names Ana Bruno]`. Names are assigned in order of first
  appearance. Check them against the transcript and rename if wrong.

After diarizing, `work/transcripts/<id>.txt` shows `[Name]` turns. Captions break at speaker changes,
and `ea transcript` shows who speaks in the edited video. Re-run subtitles after diarizing.
