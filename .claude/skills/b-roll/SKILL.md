---
name: b-roll
description: Cover talking-head sections with relevant footage: first from the user's own clips (visual index), then stock (Pexels), then generated with the Higgsfield API. Use for "add b-roll", "cover the jump cuts", "illustrate this part".
---
# b-roll

1. Decide where: moments the speaker names something visual, long unbroken talking (>8-10 s),
   and jump cuts the user wants hidden. Keep each insert 2-5 s; never cover the hook's first second.
2. Source in this order:
   - **Own footage**: visual-index skill, `broll_candidate: true` scenes.
   - **Stock**: `uv run ea broll <p> "query" [--orientation portrait] [-n 5] [--download 2]`
     (needs `PEXELS_API_KEY`). Look at the `preview` image links before downloading. Credit is
     stored in media.json.
   - **Generated**: higgsfield skill (`ea hf ...`), text-to-video for shots that don't exist,
     image-to-video to animate a frame of the user's footage so it matches the look. Costs credits:
     estimate and confirm first.
   - Files made elsewhere (downloads, other tools): `uv run ea register <p> <file> --kind broll`.
3. Place on V2 in timeline.json: `{"media": "...", "in": 0, "out": 3.5, "start": <timeline s>}`.
   Dialogue keeps playing from A1; b-roll audio is not used unless you also add an audio clip.
4. Validate, preview, describe each insert in one line.
