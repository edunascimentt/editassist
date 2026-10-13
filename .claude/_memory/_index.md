# _index.md — project memory index

> Index for `.claude/_memory/`. One line per file. `_` prefix sorts it first.
> Read this to know what's here, then open the file you need.
>
> **SHARED TIER.** These files are committed and read by everyone with repo access.
> Nothing personal: no personal emails, no `/Users/<someone>/` paths, no account logins,
> org/team IDs, or secrets. Personal context belongs in the author's private global
> memory (`~/.memory-os/memory/`). Run `memory-os check` before sharing.

- [project.md](project.md) — what editassist is, stack, how to run/test, constraints
- [focus.md](focus.md) — priorities + the list of things NOT yet verified (Windows, NLE imports, live APIs)
- [facts.md](facts.md) — where things live, conventions (posix json paths, ffmpeg cwd), hard-won gotchas (launch template, two real Resolve edits)
- [people.md](people.md) — roles: owner, collaborator
- [decisions.md](decisions.md) — append-only: engine design, timeline format, bundling, bake, Higgsfield, Resolve MCP, memory tiers, client prefs

- **2026-10-13 (3):** `ea resolve-subs`: re-break captions on live Resolve timelines to a max line length (podcast cortes: 15 chars x 2 lines); Resolve cue line break = U+2028, relative ImportMedia paths place nothing, subtitle style y is from the bottom.
- **2026-10-13 (2):** Premiere bridge full pass (90/90 live MCP checks): LUT/speed/whip as rendered copies, captions as alpha layer + .srt, push-in Position keyframes, offline relink, ripple with linked halves, `ea premiere export`; `ea render` push-in + letterbox bugs fixed.
- **2026-10-13:** Premiere live bridge: UXP panel (`premiere_uxp/`) + hub/MCP (`ea premiere-mcp`, `ea premiere …`), timeline.json built live as a sequence (`premiere_native`), premiere-live skill; verified live on macOS Premiere 26.3.2 (frame-exact cuts, framing = ea render, fades, live ops).
- **BUILT (2026-10-01):** full pipeline + 28 skills + tests/CI. **2026-10-02:** Resolve MCP, memory-os, product-launch skill (`templates/launch/`, `ea launch`).
- **2026-10-10:** podcast episodes trimmed + intro on V2 in Resolve: `ea transcribe --head/--tail/--span` (partial, mergeable transcripts); Resolve 21.0 has no AddKeyframe (fades baked as alpha ProRes); MCP add_track auto-archives and moves the pool's current folder. Season reel (9:16): crops reach Resolve as Zoom + Pan (no bake), reformat splits at camera cuts, `--lines` captions kept as written, generated graphics need `setsar=1`. Reel v2: zoom-through transitions (`whip`), bake --to, subtitles re-placed when the playhead move fails.
- **2026-10-09 (4):** client review of the inauguração: `ea shake` catches gentle hand-held + short slow-mo shots, off-centre zooms reach Resolve (Pan/Tilt), `ea beats` gives the natural `end`, captions join split numbers and break at cut-out sentences, `ea vocab --add` repeatable; recap skill: hook montage first.
- **2026-10-09 (3):** per-client preferences (`ea client`, `<memory>/clients/<slug>/preferences.md`, general vs client rule in style-profile/review/CLAUDE.md); skills catalogue page.
- **2026-10-09 (2):** `sync` skill (34): pull + deps install, commit, push to `main` for colleagues; `.gitattributes` union merge for facts/decisions/people.
- **2026-10-09:** timeline slots (`ea timeline save/load`): several videos per project, captions stamped per timeline; qa overlay-past-picture check; render trims loudness to target; Resolve timelines filed in bin `TIMELINES FINAIS`.
- **2026-10-08:** transcription dictionary (`ea vocab`, <memory>/vocabulary.md), parallel/atomic proxies, Resolve native build frame-exact at 59.94->23.976 + sets timeline fps, qa/shake false positives fixed.
- **2026-10-07:** dual-mic stereo: `ea level` picks the voice channel (`channel` clip field), bake/render play it centred.
- **2026-10-06 (3):** after user feedback: `ea level`, `ea shake`, `export --template`, frame-exact native build, qa black-flash check, phrase captions + `--fix`.
- **2026-10-06 (2):** client car reel: resolve_native speed conform at any rate, zoom, gain copies, LUTs from Resolve LUT folders; render flash-frame fix; symlink path normalisation.
- **2026-10-06:** first real edit; then self-improvement pass: native Resolve fallback + `--current`, NTSC fcpx fix, ducking stem on export, render ducking bug fixed, qa audio checks, `scenes --frames`, `recap` skill (33), CLAUDE.md step 6.
- **2026-10-05:** `preferences-quiz` skill (32 skills); repo public on GitHub; memory-os vendored in `vendor/memory-os/` (`ea memory --install`); desktop app in `app/` (Electron, Claude API key / Codex).
