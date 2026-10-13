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
- Countdown ("faltam N dias" teaser, opaque, posts as is): split-flap card on a string drops in, rolls from
  `from` to `to`, then handwritten lines (Caveat) write on; `_word_` = drawn underline, `(word)` = drawn loop.
  `uv run ea motion <p> Countdown --props work/countdown.props.json --seconds 7`, props: kicker, from, to,
  lines, paper, ink, tag, symbol, logo. Flips land at 1.13 + 0.13 k s, the last at 2.25 s (60 fps): put
  short clicks there (peak on the landing) on two alternating SFX tracks, they overlap otherwise.
- SaveTheDate ("save the date dd/mm", opaque): grainy background, script title (Pinyon Script) writes on,
  month calendar cascades in, a soft pill sweeps along the week and a solid dot lands on the day (3.45 s),
  then the weekday (Cinzel caps) and the date (Montserrat italic) and the logo. Needs the timeline at the
  output size first (a new project is 1920x1080@30: write timeline.json with width/height/fps before
  `ea motion`). Props: day, month (1-12), year, title, eyebrow, line, paper, ink, symbol, logo (one-colour
  images are tinted with `ink`). Put the click/hit on 3.45 s and a music section lift there.
- Image props (logo, symbol) take a file path: `ea motion` copies it to assets/user-media/ (gitignored).
- Title takes `"y": 0.7` (0..1 of height) to sit below a logo or face instead of the centre; sizes follow
  the short side, so vertical frames don't overflow. Look at a frame of it over the shot.
- Place the result on V2+ in timeline.json at the moment it should appear (`in: 0`).
- `--props` also takes a path to a .json file: prefer that for long text or on Windows (no quote escaping).

New template: add a component in `remotion/src/`, register it in `Root.tsx` with the shared
`calculateMetadata`, use `FONT` from `fonts.ts`, then preview with `npm run studio` in `remotion/`.
Brand colours/fonts come from the client's `<memory>/clients/<client>/preferences.md` (`ea client show <p>`),
else `<memory>/styles/`.
