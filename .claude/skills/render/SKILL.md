---
name: render
description: Render the timeline to an mp4 with platform loudness and optional burned captions. Use for previews during editing and for final delivery when the user doesn't need an NLE project.
---
# render

`uv run ea render <p> [--preset preview|youtube|instagram|tiktok|podcast|broadcast] [--subs output/<name>.ass] [--out path]`

- `preview` (540p, fast) after every meaningful change; send the user the path. It reads the proxies
  when ingest made them (`--proxies`): 4K 10-bit footage previews many times faster.
- `--out` is project-relative (like `--subs`), e.g. `--out output/<name>_v2.mp4`. Version the files
  (`_v1`, `_v2`) so the user can compare.
- Delivery presets set loudness (YouTube/social -14 LUFS, podcast -16, broadcast -23) at full res.
- Then `uv run ea qa <p> --render <file> --preset <same>` to verify loudness, peaks, black frames,
  audio shorter than the picture and silent stretches. Also look at frames of the render (qa skill):
  text overflowing the frame or sitting on a logo is not something qa can see.
