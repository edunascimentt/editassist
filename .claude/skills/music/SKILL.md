---
name: music
description: Background music bed (ElevenLabs music generation or a track the user provides), placed under dialogue with automatic ducking. Use for "add music", "soundtrack", "trilha".
---
# music

1. Ask or infer mood, genre and energy from the brief and memory (e.g. "lofi, calm, 85 bpm").
2. Generate: `uv run ea music <p> "prompt" --seconds <timeline length + 5>` (instrumental unless
   `--vocals`). Or the user's own file: `uv run ea register <p> <file> --kind music`.
3. Add a track to timeline.json:
   `{"kind": "audio", "name": "Music", "clips": [{"media": "...", "in": 0, "out": L, "start": 0,
   "gain_db": -18, "duck": true, "fade": 1.5}]}`
   `duck: true` lowers it under dialogue in the render (sidechain). In the NLE export the gain is
   kept; ducking must be redone there (Resolve: Fairlight ducking, Premiere: Essential Sound > Ducking).
4. Beats (you can't hear the music, so read them): `uv run ea beats <p> <music id>` writes
   `work/beats/<id>.json` with bpm, every beat and the downbeats (first beat of each bar).
   - Snap inserts (b-roll, motion, sfx) to beats: `uv run ea snap <p> --music <id> --tracks V2 SFX [--downbeats]`.
   - Beat-cut montage (no dialogue): write `[{"media": id, "in": s}, ...]` and run
     `uv run ea montage <p> --music <id> shots.json --every 2` (one shot per 2 beats; 1 = frantic, 4 = calm).
   - Start the music so a downbeat lands on the first cut or the hook (adjust the music clip's `in`).
