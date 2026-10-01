---
name: transitions
description: Dissolves, dips to black and fade in/out at the start and end. Use for "add transitions", "fade in/out", "smooth that cut", chapter breaks, emotional or time-passing moments.
---
# transitions

Default is a straight cut. Use transitions with intent: time passing, chapter or topic change,
start and end of the video. Never put them on every cut of a talking head.

- At specific cuts: `uv run ea transition <p> --at 12.4 30.1 --type dissolve --dur 0.5` (snaps to
  the nearest cut on V1; also applies to A1 for an audio crossfade).
- Every cut (montages only): `--all`.
- Dip to black (chapter break): `--type dip --dur 0.8`.
- Video start and end: `uv run ea transition <p> --fade-in 0.5 --fade-out 1.5`.
- Clear: `uv run ea transition <p> --clear`.

Dissolves eat handle: they need unused media before the incoming clip (and after the outgoing clip
in NLEs). The command warns when a cut has too little.
Export: dissolves become real NLE transitions (Resolve/Premiere/FCP). Fades and dips are only in
the render and the AE export; the export prints which ones to add in the NLE.
