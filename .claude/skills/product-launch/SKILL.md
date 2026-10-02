---
name: product-launch
description: Make a UI-first product launch film (motion graphics, 30-90 s) in Remotion, where the product's own interface is the star. Reference study, storyboard file, UI kit + bench, elastic stage, dense UI scenes, frame-by-frame review, composed music + voice-over + an effect on every action, pacing fix, verified export and format variants. Use for "launch video", "product video", "promo/ad for my app", "vídeo de lançamento", "motion graphics of our product", "make it like this reference".
---
# product-launch

Playbook from "Make product launch videos with AI" (Signet, Danfo Rush, Resolve films). You are both
the motion designer and your own harshest reviewer: build, render stills, LOOK, name the problem,
fix, repeat. Details: `rules.md` (measurable rules), `playbook.md` (each step's full brief),
`checklist.md` (before delivery), `styles.md` (variations from the case studies).

## 0. Intake (ask only what's missing; check `<memory>/styles/` for a saved brand)
- Product, one-sentence promise, audience, call to action (e.g. "Book a demo").
- Brand: colours, font files, logo SVG, or a Figma / design-token source.
- Product UI source, best first: an HTML prototype or the live app, then Figma screens, then screenshots.
  The film is built from the REAL interface.
- A reference film the user loves. Ask for one if there isn't any: it beats any adjective.
- Length (default 50 s, often 60-75 s after pacing), voice-over yes/no, formats needed (16:9 master,
  1:1 or 4:5 feed, 9:16 story).
- Paid parts (ElevenLabs music/voice/SFX): say roughly what you will generate and get a yes.

## 1. Studio
`uv run ea new <p>` then `uv run ea launch new <p> --seconds 50 [--size 1920x1080] [--font Brand-Black.ttf --font-bold Brand-Bold.ttf --font-name "Brand"]`.
That creates `projects/<p>/launch/` (Remotion + TS) with the stage, the kit, a bench and an example scene.
- Brand: replace `src/brand/palette.json` (ONLY these colours may appear) and `src/brand/Logo.tsx`.
- Tell the user they can watch live: `cd projects/<p>/launch && npm run studio`.

## 2. Reference
`uv run ea launch reference <p> <video>` writes 2 fps sheets, 30 fps strips around every cut, and fixes
dim screen recordings (it measures white). Open EVERY sheet and strip, then write
`work/launch/reference/breakdown.md`: pacing (shot lengths), how type animates (gap between words,
overshoot), every transition type, every UI animation technique (lists, cursor, modals, numbers),
colour and layout rules. Take the techniques, never the assets.

## 3. Storyboard (`src/beats.json`, the contract)
Title beat, UI demo, title, demo... About three quarters of the film is product UI. Each beat: `id`, `kind`
(title|demo), `from`, `duration` (picture frames, contiguous), `bg` (palette name), `transition`
(shape: circle|star|squircle|donut|diamond|blob|bloom), `title` (lines of spans, one `accent` span per
line), `scene`, and precise `notes` of every UI action. The words on screen plus the UI labels must
explain the product with the sound off. Sentence case. Show the user the beat table before building.

## 4. UI kit and bench (the turning point)
Rebuild the product's screens with `src/kit/` pieces (Browser, Phone, Notification, Cursor, Button,
TypeField, Toggle, Pill, RollingNumber, Rows, StatCard, Toast, Check, Panel, Camera) and add what the
product needs (dropdown, keypad, morphs) in the same style: pure functions of the frame.
Show everything in `src/Bench.tsx` (8 s), check it with `uv run ea launch stills <p> --comp Bench --every 8`,
and get the user's "wow" here. Then FREEZE the kit: from now on, new needs are built inside the scene.

## 5. Stage
`src/stage/` already does colour floods, elastic shape wipes with a 3-frame glitch, word-pop titles
that dock as a pinned caption, and calm props. Decide the background early and keep it quiet (props
density ≤ 1); the energy belongs in the foreground. Add a mascot only if the brand has one.

## 6. Scenes, one beat at a time
Copy `src/scenes/Example.tsx` per demo beat and register it in `src/scenes/index.ts`. Keep all timing in one
`T` object and export `cues` from it (sounds then follow the animation automatically). Per scene:
something meaningful moves in every 8-frame window, 12+ distinct UI animations (list them), the camera
never rests, the cursor never covers a label, labels ≥ 20 px on screen, every frame has readable
text. Land big moves on `src/music-hits.json` once music exists. After each scene, render strips of
it and of the hand-off into the next beat, and fix what you see.

## 7. Review: frames, not vibes
- `uv run ea launch stills <p> --every 6` → open every sheet. Look for frames without text, collisions,
  accidental clipping, numbers caught mid-roll on a hold, a cursor on a label, and jumps.
- `uv run ea launch audit <p> --motion` → storyboard continuity, sentence case, one accent per line,
  title hold ≥ 1 s, UI share, off-palette colours, missing glyphs (₦, ⌘, curly quotes), audio files,
  and the 8-frame density rule measured on renders. Fix every error; justify any warn you keep.
- Ask the user for screenshots of anything they dislike, and translate vibes into rules (`rules.md`).
- Change one big thing at a time (style → structure → polish), and render the current cut
  (`ea launch render`) before any big change. That render is the undo button.

## 8. Sound
- Effects: `uv run ea launch sfx-kit <p>` (9 UI sounds, cached so later films reuse them for free). Stage
  and scene cues place them; pile-ups within 2 frames are dropped automatically.
- Music composed to the cut: write a plan (`playbook.md` §8) with sections ending on beat ids, each
  ≥ 3 s, then `uv run ea launch music <p> plan.json`. It normalises to -16 LUFS and writes the hits for
  syncing.
- Voice-over (optional): one short line per beat that EXPLAINS (never repeats the title):
  `uv run ea launch vo <p> lines.json [--voice <id>]`. Defaults to stability 0.3, similarity 0.8,
  style 0.5, speed 1.05, trimmed, -16 LUFS, music ducked under it.

## 9. Pace
If you'd have to pause to read it, it's too fast: a title needs ~1 s settled, a UI step ~0.5 s of
stillness after it completes. To slow the whole film without touching animation, set
`"playback": 0.6667` in `src/film.json` (1.5x slower). The picture is slowed and the audio stays at real speed
(cues are remapped). Then re-fit the music: `uv run ea launch stretch-music <p> <seconds>` loops the
groove on bar lines for free, or re-compose.

## 10. Export and deliver
`uv run ea launch render <p>` renders, normalises to -16 LUFS / TP < -1 without re-encoding video, and
verifies the FILE (frames, size, a sheet every 3 s, loudness). Open the verify sheet.
Formats: `--size 1080x1080`, `--size 1080x1350`, `--size 1080x1920`. Scenes read `useVideoConfig()`, so
REFLOW the layout per format (don't crop); for 9:16 keep text out of the top 200 px and bottom 250 px.
Then check every format with `ea launch stills --size ...`.
Save the brand (palette, fonts, voice, look) as `<memory>/styles/<brand>.md` for the next film.
