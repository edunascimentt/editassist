---
name: reformat
description: Change aspect ratio (16:9 to 9:16, 1:1, 4:5) keeping the speaker's face in frame. Use for vertical versions, Reels/TikTok/Shorts, square posts.
---
# reformat

`uv run ea reformat <p> --aspect 9:16 [--prefer left|right] [--bake]`

- Output keeps the project's resolution (4K project: 2160x3840 for 9:16).
- Podcasts/interviews: `--prefer left|right` = the side the guest sits on; in shots with several faces
  (the wide two-shot) the crop frames that person instead of the biggest face.

- Splits video clips at camera cuts inside them (switched multi-camera feeds), then finds the face per
  shot (YuNet, biggest face) and sets a crop box; no face falls back to centre. `flash_frames` in the
  output = a camera cut a few frames from a clip edge: move that edit point.
- In wides the biggest face is often a LISTENER nearer the camera: use `--prefer`, then check every
  wide (crop contact sheet) and re-aim the crop `x` at the speaker where needed.
- Without `--bake`: crops live in timeline.json; render and the After Effects export honour them.
- Resolve via `ea export --open`: no bake needed, crops become Zoom + Pan on each item (how the user
  frames vertical cuts by hand).
- With `--bake` (same as running `uv run ea bake <p>` afterwards): renders the crops (and any zooms or
  speed changes) into `work/baked/` and repoints the timeline. Required before exporting to
  Resolve/Premiere, because XML/OTIO can't carry crops. Run it as the LAST picture step, after the cut
  is locked.
- Re-run subtitles after reformatting (caption size depends on frame size).
- Check the preview: two people in frame or wide shots may need a manual `crop` edit in
  timeline.json (`{"w","h","x","y"}` in source pixels).
