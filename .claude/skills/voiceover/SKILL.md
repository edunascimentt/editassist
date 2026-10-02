---
name: voiceover
description: Narration with ElevenLabs text-to-speech (or the user's cloned voice). Use for "add narration", "voiceover", "read this script", replacing a bad line, dubbing.
---
# voiceover

1. `uv run ea voices` to list voices (needs `ELEVENLABS_API_KEY`). Prefer the voice id in
   `<memory>/preferences.md` / `ELEVENLABS_VOICE_ID`.
2. Generate one file per paragraph (easier to retime than one long file):
   `uv run ea voiceover <p> "text" [--voice <id>] [--model eleven_multilingual_v2]`
3. The result is registered in media.json (`voiceover__...`). To caption it: `uv run ea transcribe <p> --only <id>`.
4. Place on A1 (narration-led video) or A2 (over dialogue) in timeline.json.
5. Costs credits: confirm the full script with the user before generating more than a few lines.
