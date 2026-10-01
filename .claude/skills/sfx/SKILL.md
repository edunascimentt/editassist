---
name: sfx
description: Sound effects (whooshes, hits, risers, ambience, UI clicks) generated with ElevenLabs and placed on cuts, transitions or on-screen text. Use for "add sound effects", "sfx", "make it punchier".
---
# sfx

1. Choose moments: zoom punches, b-roll entries, title reveals, list items. Less is more; reuse one
   generated whoosh rather than generating ten.
2. `uv run ea sfx <p> "short cinematic whoosh, airy" --seconds 1.2`
3. Add on an `SFX` audio track at the moment, start slightly before the visual (~2 frames),
   `gain_db` around -10 to -6.
