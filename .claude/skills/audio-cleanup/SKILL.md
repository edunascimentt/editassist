---
name: audio-cleanup
description: Make dialogue clean and consistent: denoise, high-pass, gentle compression, loudness. Use for "fix the audio", "remove background noise", "voice sounds bad", mismatched levels between clips.
---
# audio-cleanup

There is no `ea` command for this: process the source audio with ffmpeg into `work/clean/` and point
A1 clips at the cleaned files (same timing, so `in`/`out` stay valid).

```
ffmpeg -i input/<file> -vn -af "highpass=f=80,afftdn=nf=-25,acompressor=threshold=-18dB:ratio=3:attack=10:release=200,loudnorm=I=-16:TP=-1.5" -c:a pcm_s24le work/clean/<id>.wav
uv run ea register <p> work/clean/<id>.wav --kind clean
```

- `afftdn=nf` -20 (light) to -30 (strong); stronger sounds watery: A/B by rendering a 10 s preview.
- Levels between clips: loudnorm each file to the same target before editing.
- Heavy noise or reverb beyond this: suggest ElevenLabs Voice Isolator or Resolve's Voice Isolation
  in the NLE, and say why.
