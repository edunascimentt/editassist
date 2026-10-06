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
- [facts.md](facts.md) — where things live, conventions (posix json paths, ffmpeg cwd), 22 hard-won gotchas (incl. launch template)
- [people.md](people.md) — roles: owner, collaborator
- [decisions.md](decisions.md) — append-only: engine design, timeline format, bundling, bake, Higgsfield, Resolve MCP, memory tiers

- **BUILT (2026-10-01):** full pipeline + 28 skills + tests/CI. **2026-10-02:** Resolve MCP, memory-os, product-launch skill (`templates/launch/`, `ea launch`).
- **2026-10-06:** first real edit; then self-improvement pass: native Resolve fallback + `--current`, NTSC fcpx fix, ducking stem on export, render ducking bug fixed, qa audio checks, `scenes --frames`, `recap` skill (33), CLAUDE.md step 6.
- **2026-10-05:** `preferences-quiz` skill (32 skills); repo public on GitHub; memory-os vendored in `vendor/memory-os/` (`ea memory --install`); desktop app in `app/` (Electron, Claude API key / Codex).
