# Launch film template

Created by `uv run ea launch new <project>`; driven by the product-launch skill.

- `src/film.json`: size, fps, `playback` (0.6667 = whole picture 1.5x slower, audio unchanged), font name
- `src/beats.json`: the storyboard (contract for every scene)
- `src/brand/`: `palette.json` (the only allowed colours), theme (fonts from `public/fonts/Brand-*.ttf`), Logo
- `src/kit/`: UI pieces, all pure functions of the frame. Freeze once scenes start.
- `src/stage/`: floods, elastic wipes + glitch, word-pop titles that dock as captions, calm props
- `src/scenes/`: one file per demo beat (timings in `T`, sound `cues` exported from them); register in `index.ts`
- `src/audio/Soundtrack.tsx`: music (ducked under voice), voice lines, SFX from cues; outside the slowed picture
- `src/audio.json`, `src/music-hits.json`: written by `ea launch music | vo | sfx-kit`
- `scripts/stills.mjs`: renders frames as JPEG stills (used by `ea launch stills`)

`npm run studio` previews live; `uv run ea launch render <project>` renders and verifies.
