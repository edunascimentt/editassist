---
name: color
description: Colour correction and looks. Auto balance and exposure, match cameras to each other, add a look (warm, cool, punchy, film, bw) or a creative .cube LUT. Use for "fix the colour", "match the cameras", "make it cinematic", "apply this LUT", mismatched footage.
---
# color

Every grade compiles into ONE `.cube` per media (`work/color/<id>.cube`, listed in
`work/color.json`). Render applies it, Resolve gets it applied on import (`ea export --open`),
Premiere/AE users load the same file.

0. Log footage first (`log: true` / `gamma` in `work/media.json`, e.g. Sony S-Log3): it needs a
   log-to-Rec709 LUT, never `--auto` on the flat image. Look for the user's own LUTs first (Resolve:
   `/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/` and its `Custom/`; creative
   ones made for that camera, e.g. "S-Log3-Sg3Cine", beat the neutral Sony conversion). Then
   `uv run ea color <p> --lut <file.cube>` (no frame analysis: fast) and `--compare` two or three clips.
1. Correct: `uv run ea color <p> --auto [--media id1 id2] [--strength 0.7]`. Grey-world balance and
   levels, deliberately gentle.
2. Match cameras: `uv run ea color <p> --match <reference id> --media <others>`. Pick as reference the
   best-looking camera (look at the contact sheets first).
3. Look: add `--look warm|cool|punchy|film|bw`, or `--lut path/to/creative.cube` for a LUT the user gives.
   Options combine in one call, applied in order: auto, then match, then LUT, then look.
4. Check before and after: `uv run ea color <p> --compare <id>` writes `work/color/<id>_compare.jpg`
   (left original, right graded). Open it and judge skin tones; if they look off, lower `--strength`
   or drop the look.
5. Undo: `uv run ea color <p> --reset [--media id]`.

Each call rebuilds the LUT from scratch with the options given, so repeat the options you want to keep.
Save the user's preferred look in `<memory>/preferences.md`.
