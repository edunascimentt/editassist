---
name: music
description: Background music bed (ElevenLabs music generation or a track the user provides), placed under dialogue with automatic ducking. Use for "add music", "soundtrack", "trilha".
---
# music

1. Ask or infer mood, genre and energy from the brief and memory (e.g. "lofi, calm, 85 bpm").
   Look for music the user already licensed first: client folders often have `_MUSICA`/`music`/`trilha`
   folders (filenames may note how a track was used: gain, start, fades). Reusing a client's track keeps
   their videos consistent and costs nothing. ElevenLabs music needs a PAID plan (the free plan answers
   402 `paid_plan_required`; `ea keys --check` shows the plan).
   Delivered tracks are often pre-mixed quiet (bed already at -24 dB): measure, then normalise a copy
   (`ffmpeg -i in.wav -af loudnorm=I=-14:TP=-1.5 work/music/x.wav`) and register that.
   Choose where the music STARTS so its natural ending lands on the video's end (`ea beats`: start on a
   downbeat, end = start + video length = file end); a fade-out on a cut-off track is the fallback.
2. Generate: `uv run ea music <p> "prompt" --seconds <timeline length + 5>` (instrumental unless
   `--vocals`). Or the user's own file: `uv run ea register <p> <file> --kind music`.
3. Add a track to timeline.json:
   `{"kind": "audio", "name": "Music", "clips": [{"media": "...", "in": 0, "out": L, "start": 0,
   "gain_db": -18, "duck": true, "fade": 1.5}]}`
   `duck: true` lowers it under dialogue in the render (sidechain). Then ALWAYS `uv run ea level <p>`:
   it measures every audio clip and sets gains by role (voice -16 LUFS, bed under speech -30, music
   alone -16, sfx -22). A guessed `gain_db` on a mastered track under a raw lav mic left the music as
   loud as the voice (user feedback 2026-10-06). Re-run after any audio change. It also spots dual-mic
   stereo (lav on one channel, car/camera mic on the other) and sets `channel: "L"|"R"` on dialogue so
   only the voice side plays, centred; put the other mic on its own track with the opposite `channel`
   when you want its sound (engine roar), e.g. `role: "sfx"`. `ea export` bakes the same ducking
   into one stem (`work/baked/music_ducked_*.wav`) for the NLE, because exchange formats only keep gain.
4. Beats (you can't hear the music, so read them): `uv run ea beats <p> <music id>` writes
   `work/beats/<id>.json` with bpm, every beat and the downbeats (first beat of each bar).
   - Snap inserts (b-roll, motion, sfx) to beats: `uv run ea snap <p> --music <id> --tracks V2 SFX [--downbeats]`.
   - Beat-cut montage (no dialogue): write `[{"media": id, "in": s}, ...]` and run
     `uv run ea montage <p> --music <id> shots.json --every 2` (one shot per 2 beats; 1 = frantic, 4 = calm).
   - Start the music so a downbeat lands on the first cut or the hook (adjust the music clip's `in`).
