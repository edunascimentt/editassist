---
name: motion-graphics
description: Animated overlays rendered with Remotion: lower thirds, titles, animated word-by-word captions, and new custom templates. Use for "add a lower third", "title card", "animated captions", "motion graphics".
---
# motion-graphics

Templates live in `remotion/src/` (Captions, LowerThird, Title). They render as transparent
ProRes 4444, matching the timeline size/fps, and are registered in media.json.

- Lower third: `uv run ea motion <p> LowerThird --props '{"name":"Ana Souza","role":"CEO, Acme"}' --seconds 5`
- Title: `uv run ea motion <p> Title --props '{"text":"Part 2","kicker":"HOW IT WORKS"}' --seconds 3`
- Captions: `uv run ea motion <p> Captions` (needs `ea subtitles` first; `--props '{"accent":"#00E5FF"}'`)
- Title takes `"y": 0.7` (0..1 of height) to sit below a logo or face instead of the centre; sizes follow
  the short side, so vertical frames don't overflow. Look at a frame of it over the shot.
- Place the result on V2+ in timeline.json at the moment it should appear (`in: 0`).
- `--props` also takes a path to a .json file: prefer that for long text or on Windows (no quote escaping).

New template: add a component in `remotion/src/`, register it in `Root.tsx` with the shared
`calculateMetadata`, use `FONT` from `fonts.ts`, then preview with `npm run studio` in `remotion/`.
Brand colours/fonts come from `<memory>/styles/`.
