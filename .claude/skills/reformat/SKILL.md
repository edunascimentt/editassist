---
name: reformat
description: Change aspect ratio (16:9 to 9:16, 1:1, 4:5) keeping the speaker's face in frame. Use for vertical versions, Reels/TikTok/Shorts, square posts.
---
# reformat

`uv run ea reformat <p> --aspect 9:16 [--bake]`

- Finds the speaker's face per clip (YuNet) and sets a crop box; no face falls back to centre.
- Without `--bake`: crops live in timeline.json; render and the After Effects export honour them.
- With `--bake` (same as running `uv run ea bake <p>` afterwards): renders the crops (and any zooms or
  speed changes) into `work/baked/` and repoints the timeline. Required before exporting to
  Resolve/Premiere, because XML/OTIO can't carry crops. Run it as the LAST picture step, after the cut
  is locked.
- Re-run subtitles after reformatting (caption size depends on frame size).
- Check the preview: two people in frame or wide shots may need a manual `crop` edit in
  timeline.json (`{"w","h","x","y"}` in source pixels).
