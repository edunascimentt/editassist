---
name: zoom-punch
description: Punch-ins and push-ins centred on the speaker's face. Alternate framing to hide jump cuts, or emphasis zooms on key phrases. Use for "add zooms", "punch in", "make it dynamic", "hide the jump cuts", talking-head shorts.
---
# zoom-punch

- **Hide jump cuts**: `uv run ea zoom <p> --punch [--scale 1.12] [--every 2]`. Every second clip is
  punched in, so consecutive cuts change framing. `--every 3` is subtler.
- **Emphasis**: find the phrase (`uv run ea transcript <p>`, then the timeline time of the words), then
  `uv run ea zoom <p> --at <t> --dur <s> [--scale 1.2] [--ramp 0.8]`. That splits only the picture and
  zooms that part. `--ramp` makes it a slow push-in instead of a hard punch.
- Remove all zooms: `uv run ea zoom <p> --clear`.
- Restraint: 1.08-1.15 for long-form, 1.15-1.3 for shorts; no more than one emphasis every ~5 s.
- Zooms render everywhere and After Effects keeps them (with keyframes for ramps). For Resolve or
  Premiere, run `uv run ea bake <p>` before export.
- Combine with sfx: a soft whoosh or hit on hard punches (sfx skill), never on every one.
