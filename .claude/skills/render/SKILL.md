---
name: render
description: Render the timeline to an mp4 with platform loudness and optional burned captions. Use for previews during editing and for final delivery when the user doesn't need an NLE project.
---
# render

`uv run ea render <p> [--preset preview|youtube|instagram|tiktok|podcast|broadcast] [--subs output/<name>.ass] [--out path]`

- `preview` (540p, fast) after every meaningful change; send the user the path.
- Delivery presets set loudness (YouTube/social -14 LUFS, podcast -16, broadcast -23) at full res.
- Then `uv run ea qa <p> --render <file> --preset <same>` to verify loudness, peaks and black frames.
