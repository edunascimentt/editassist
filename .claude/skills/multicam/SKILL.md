---
name: multicam
description: Sync several cameras and external microphones by sound, replace camera audio with the clean mic, and cut between angles. Use for podcasts and interviews with 2+ cameras, separate audio recorders, "sync the audio", "use the good mic", "switch cameras".
---
# multicam

1. Ingest everything. Pick the reference: the camera that rolls the longest.
2. `uv run ea sync <p> --ref cam_a cam_b mic_1 [mic_2]` writes the offsets to `work/sync.json`.
   Confidence below 5 means the result is unreliable: tell the user, check for a clap, or trim
   very long silences.
3. Transcribe the reference camera (or the cleanest mic: transcription is better on the mic), and
   cut as usual (rough-cut / silence-cut) on that media.
4. Clean audio: `uv run ea sync <p> --swap-audio cam_a mic_1`. Every A1 clip cut from cam_a now plays the same
   moment from mic_1. Clips outside the mic's recording are listed and left unchanged.
5. Angles: `uv run ea sync <p> --switch <t0> <t1> cam_b` shows cam_b on that timeline range, in sync.
   Cutting rules: switch to whoever is speaking (speakers skill gives you who speaks when), go to the
   listener for reactions, hold each angle for at least ~2 s, and use the wide shot when people talk
   over each other.
6. Then subtitles, color (`--match` the cameras to each other), qa, export. Each angle exports as
   its own clip of its own file, so the NLE edit stays editable.
