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
- Zooms render everywhere and After Effects keeps them (with keyframes for ramps). Resolve via
  `ea export --open` gets hard punches natively (Zoom + Pan); push-ins (`ramp`) and zoom transitions need
  `uv run ea bake <p> [--to <client media folder>]` first (Resolve 21.0 scripting has no keyframes, and
  Fusion comps added by script do not render). Premiere: always bake.
- Reel recipe that worked (2026-10-10): every shot a slow push-in 1.0 -> 1.07 over its length, a hard
  punch 1.2 from the key word of ~half the lines to the end of the line, zoom transitions between lines.
- Combine with sfx: a soft whoosh or hit on hard punches (sfx skill), never on every one.
