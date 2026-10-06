---
name: recap
description: ONE highlights/recap/sizzle video of an event, training, day or place (30-90 s), cut to music with a few spoken lines carrying the story. Use for "vídeo de highlights do evento", "recap", "aftermovie", "sizzle", "resumo do dia", "highlights com música". For several short clips cut from a long talk, use the highlight skill instead.
---
# recap

Structure that works: hook line → title over logo/brand shots → montage → line → montage → ... →
payoff line (best reaction) → end title on a brand shot until the music's natural end.

1. ingest (`--proxies`), transcribe, then `ea scenes <p> --frames 6` and READ every overview sheet
   (visual-index skill). Note: log footage (color skill step 0), slow-motion clips (`capture_fps`),
   vertical footage (deliverable 1080x1920). Grade early so every later look is at the real image.
2. Story from the transcripts: 4-7 lines of 2-6 s each that make sense alone and in sequence. Hook
   = the strongest claim; payoff = an emotional reaction or a result ("parabéns, tá incrível").
   Get word times with `ea find` / the transcript json; never guess. Drop lines whose picture doesn't
   show the speaker unless you cover them with listeners (b-roll over voice is fine).
3. Music: music skill. Start it so its ending lands on the video end; `ea beats` for the grid.
4. Build `timeline.json` (format in `src/editassist/timeline.py`):
   - A1 = only the spoken lines (montage clips stay silent: their room tone fights the music).
   - V1 per line = the same clip, held to the next beat so every following cut lands on the music.
   - Montage shots fill 2 beats (energetic) or 4 beats (title/opening); slow-motion clips at speed
     `fps / capture_fps`; faces, hands, logos, wide room, people reacting. No shot twice.
   - Line edges: pad 0-0.08 s but never into a neighbouring word (qa flags it).
   - Titles (motion-graphics, `y` below the logo), SFX (sfx skill: whoosh into titles, a riser before
     the payoff, at -9 to -15 dB), fade out at the end. Music `duck: true`.
   A small Python builder in `work/build.py` that lays this out from a list is easier to revise than
   hand-edited json; keep it with the project.
5. subtitles (`bold`, 3 words, accent = title colour), render preview, qa with `--render`, then LOOK at
   ~20 frames of the render (text overflow, titles over logos, captions over faces).
6. NLE: export-nle (`--open --current` for the project already open in Resolve).
