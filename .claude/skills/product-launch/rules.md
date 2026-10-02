# Rules (measurable — give rules, not vibes)

| Rule | Check |
|---|---|
| UI demos fill ≥ 50% of the film (aim ~75%) | `ea launch audit` demo_share |
| Inside a demo, something meaningful moves in every 8-frame window | `audit --motion` frozen_windows = 0 |
| ≥ 12 distinct UI animations per demo (rows stagger, number roll, field types, dropdown, camera push, toast…: each counts once) | list them in your scene summary |
| No frame without readable text: titles dock as a pinned caption during demos | `stills --every 6` sweep |
| A title stays settled ≥ 1 s before it leaves | audit "pace" |
| Words pop 2–3 frames apart, 15–20% overshoot, slight tilt; scale overshoot capped so words never collide | built into `stage/Title.tsx` |
| Sentence case, never all caps; one accent word per line | audit "copy" |
| Only palette colours; only brand fonts; every glyph exists in the font | audit "colour" / "font" |
| The cursor never covers a label: press on a button's edge, park the cursor in empty space | stills review |
| Numbers finish rolling before any hold | stills review (garbled digits on a still = mid-roll) |
| Calm background, loud foreground: props density ≤ 1, slow drift | stills review |
| Contrast, not chaos: violent hits, then short clean holds; everything lands crisp | stills review |
| Big moves land on the music's hits (`src/music-hits.json`) | cue frames vs hits |
| A sound on every visible action; no pile-ups within 2 frames; nothing clipping | Soundtrack dedup + `verify` |
| Audio −16 LUFS integrated, true peak < −1 dBTP | `ea launch verify` |
| Labels ≥ 20 px on screen (≥ 28 px if the film will be watched on phones) | stills at 100% |
| 9:16: no text in the top 200 px or bottom 250 px | `stills --size 1080x1920` |

## Vibe → rule (how to translate the user's feedback)
- "I need to see a lot of UI animation" → raise UI share to ~75% and enforce the density rule.
- "There are blank moments" → pinned caption on every demo + a stills sweep every 6 frames.
- "Make the transitions more fun" → elastic: overshoot past cover, wobbly edge, squash out, bounce in, 3-frame glitch.
- "Too much going on in the background" → halve prop count and speed, keep foreground animation.
- "It's too fast" → `playback` 0.6667 (1.5x slower) before touching any animation.
- "Crazier" → stronger hits AND cleaner holds; never more background motion.
