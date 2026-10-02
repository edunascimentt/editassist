# Playbook: the brief for each step

Adapted from the guide's prompt library. You execute these yourself; `[brackets]` are what you fill in
from the intake.

1. **Studio**: `ea launch new` sets up a [50] s [1920×1080] 30 fps TypeScript Remotion project with the brand
   font loaded from local files and the stills/contact-sheet helper (`ea launch stills`), so every
   change ends with "render strips and fix what you see".
2. **Brand tokens**: one palette file + one theme; only those colours; logo as an SVG component.
3. **Reference study**: contact sheets at 2 fps plus 30 fps strips of key moments (every transition,
   word animations, the cursor, each UI interaction). Breakdown covers pacing, type animation, every
   transition type, every UI technique, colour and layout. Measure white first: screen recordings are
   often at half brightness.
4. **Storyboard**: [50] s, about [12] beats modelled on the reference; UI demos ≈ ¾ of the film with
   short title beats between; on-screen words + UI labels explain the product with sound off; sentence
   case, one accent per line; each beat's frame range, colour, transition, copy and detailed UI notes.
   Shape that worked (Signet, 13 beats): opener → dashboard (stats count up, ⌘K search) → request a
   change (drawer, typed reason, submit) → set rules (chips, dropdown, toggle, save) → approve on
   phone (notification, PIN keypad, check) → punchline grid → inbox bulk approve ("All caught up") →
   audit log → team roles → summary cards flip to Approved → logo + "Book a demo".
5. **UI kit + bench**: browser and phone frames that rise in with overshoot; blob cursor with smear
   trail, press squash and click ring; rows that stagger in with sparkle bursts; rolling numbers;
   status pills; buttons with hover/press/spinner; self-typing fields with caret; dropdowns; toggles;
   keypad with PIN dots; drawers, modals, toasts; a check that draws itself; a camera that pushes and
   pans; shared-element morphs (a row becomes a detail card, a notification becomes a sheet). All pure
   functions of the frame; one 8 s bench showing everything.
6. **Stage**: flat flood per beat; calm props that burst in then drift; elastic shape wipes (overshoot,
   jelly edge, squash out, bounce in) + 3-frame glitch; word-pop titles (2–3 frames apart, 15–20%
   overshoot) that dock as a pinned caption; optional brand mascot (run, hop, knock words away).
7. **One scene** (repeat per beat): compose from the kit like the bench, full frame and bigger (labels
   ≥ 20 px); density rule; ≥ 12 UI animations; camera never rests; shared-element morphs; the cursor
   never covers a label; text always readable; render strips including the hand-off into the next
   beat; fix; list the animations used.
8. **Music plan** for `ea launch music` (sections end on beat ids; ≥ 3 s each; times follow the OUTPUT film):
   ```json
   {"styles": ["instrumental hip-hop", "warm Rhodes", "punchy drums", "90 bpm", "clean modern mix", "great production quality"],
    "avoid": ["vocals", "lo-fi hiss"],
    "sections": [
      {"name": "intro hit", "until": "opener", "styles": ["single big hit", "short riser"]},
      {"name": "main groove", "until": "punchline", "styles": ["steady groove under UI demos"]},
      {"name": "stop-time drop", "until": "grid", "styles": ["drums drop out", "bass stab"]},
      {"name": "groove two", "until": "summary", "styles": ["busier hats", "extra percussion"]},
      {"name": "build and final hit", "until": "logo", "styles": ["build", "one final hit", "clean ending"]}
    ]}
   ```
9. **Voice-over lines** for `ea launch vo` (`offset` = picture frames after the beat starts):
   ```json
   [{"beat": "dashboard", "text": "See every money move the moment it happens.", "offset": 8}]
   ```
   Short, enthusiastic, explains the scene. Bright natural voice; lower stability = more emotion.
10. **Effects**: soft pops on word pops, whoosh + short glitch zap on each wipe, clicks on cursor clicks,
    sparse key taps while typing, blips on PIN presses / row arrivals, a chime on checks. Cues come from
    each scene's `T` timings (`cues` export), never typed by hand.
11. **Slow the film**: `playback` 2/3, audio outside the slowed picture, cue frames remapped, music
    re-fit and its hits re-detected in picture time (`ea launch music` / `stretch-music` do it).
12. **Export + verify**: render, normalise audio without re-encoding video, verify frame count,
    resolution, a sheet every 3 s and loudness from the FILE.
13. **Flyer** (promo still, 1080×1080) from the same kit: calm and premium, ~6 elements, one focal point,
    lots of whitespace, one accent, sentence case; three concepts compared at full and phone size; pick
    and polish; optional 5 s animated build. Motion can be loud; a static flyer must read in under a
    second. Render it as a 1-frame composition with `ea launch stills`.
