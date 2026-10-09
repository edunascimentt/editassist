---
name: sync
description: Sync this editassist checkout with the team on GitHub, both ways. Pulls what colleagues pushed (code, skills, project memory) and installs any new dependencies, then commits everything new here (tools, skills, tests, .claude/_memory) and pushes it so the others get it. Use for "commita e dá push", "sobe tudo", "sincroniza o repo", "puxa as novidades", "atualiza o editassist", "sync", "push", "pull", or at the end of a session that changed the repo.
---
# sync

Two-way sync: **pull first, then push**. Colleagues update from `main`, so finished work must
land on `origin/main`, not just on a feature branch. Run every step from the repo root.

What travels and what doesn't:
- Travels (committed): `src/`, `.claude/skills/`, `tests/`, `remotion/`, `templates/`, `app/`,
  `memory.template/`, docs, and the shared project memory `.claude/_memory/`.
- Never travels: `projects/` (user media and edits), `.env` and `.editassist/` (API keys), the
  private editing memory (`uv run ea memory` folder, `~/.memory-os/`), `memory/`. They are
  gitignored; never `git add -f` them. A lesson that would help colleagues (a tool gotcha, not
  someone's taste) goes into `.claude/_memory/facts.md` first, written without personal data.

## 1. Look

```
git fetch origin --prune
git status --short
git branch --show-current
git log --oneline @{u}..HEAD; git log --oneline HEAD..@{u}     # unpushed / not yet pulled
git log --oneline HEAD..origin/main                            # main moved since this branch
```

Nothing local and nothing new on the remote: say "already in sync" and stop.
A rebase or merge already in progress (`git status` says so): finish or abort it before anything else.

## 2. Check before committing (only when there are local changes)

- Read `git diff` and the untracked files (`git status --short`, `??`). Open each new file you
  didn't write in this session before adding it.
- Secrets: `git diff HEAD | grep -nE "sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|(api|secret)[_-]?key\s*[:=]\s*['\"][^'\"]{12,}"`
  plus the same grep over new untracked files. Any hit: stop and show the user the file and line
  (never the value). Media files (`.mp4`, `.mov`, `.wav`...) outside `assets/`: stop and ask.
- Shared memory: `bash vendor/memory-os/bin/memory-os check` (no personal emails, `/Users/<name>/`
  paths, logins, IDs). Fix what it reports in `.claude/_memory/`, then re-run.
- Code changed (`src/`, `tests/`, `pyproject.toml`): `uv run pytest -q` (~1 min). Red: fix it or
  tell the user; never push a red suite to `main`. Memory/docs/skill-text only: skip tests.

## 3. Commit

Stage everything: `git add -A`, then `git status --short` to confirm nothing ignored-on-purpose
slipped in. Split into a few commits when the changes are clearly unrelated (one feature, the
memory update, a skill); otherwise one commit. Message style matches the log:
`feat: ...`, `fix: ...`, `docs: ...`, `chore(memory): ...`, a short body with what changed and why,
ending with the attribution lines the session gives for commits.

## 4. Pull

```
git pull --rebase origin <current-branch>        # only when that branch exists on origin
git merge origin/main                            # on a feature branch, when main moved
```

Conflicts:
- `.claude/_memory/facts.md`, `decisions.md`, `people.md` use `merge=union` (`.gitattributes`), so
  both sides' lines are kept. Afterwards scan them for a line that now appears twice or two lines that
  contradict each other; dedupe and keep the newer fact (decisions.md: never edit an old entry).
- `_index.md`, `focus.md`, code, skills: open the file, keep both sides' intent, `git add` it, then
  `git rebase --continue` / commit the merge. Not sure what a colleague meant: ask the user, don't
  drop their change.
- `uv.lock` conflict: take theirs (`git checkout --theirs uv.lock`), then `uv lock`.

## 5. Install what the pull brought

Compare against where you were before pulling (`ORIG_HEAD`, or the commit noted in step 1):
`git diff --name-only <before> HEAD`, then:

| Changed | Run |
|---|---|
| `pyproject.toml`, `uv.lock` | `uv sync` (add `--extra <name>` the user had installed, e.g. `dev`) |
| `remotion/package*.json` | `npm ci --prefix remotion` |
| `app/package*.json` | `npm ci --prefix app` (only if the user runs the desktop app) |
| `vendor/memory-os/` | `uv run ea memory --install` (updates the system files, never the memory) |
| `memory.template/` | `uv run ea memory --init` (adds new template files, keeps the user's own) |
| `.mcp.json` | tell the user to restart Claude Code to reload the Resolve MCP |

Then `uv run ea doctor` and read its JSON. Re-run the tests if step 2 skipped them and code came in.

## 6. Push

```
git push origin HEAD                      # first push of a new branch: git push -u origin HEAD
```

On a feature branch, publish it to `main` so colleagues get it:
- `git merge-base --is-ancestor origin/main HEAD` must succeed (step 4 merged main in), then
  `git push origin HEAD:main` (a fast-forward; never `--force`).
- Update the local `main`: `git fetch origin main:main` (from a feature branch).
- If the user prefers review first, open a PR instead: `gh pr create --base main` (body ends with
  the session's PR attribution line). Ask once and save the answer to `<memory>/preferences.md`.

Push rejected (someone pushed meanwhile): go back to step 4, never force.

## 7. Report

Tell the user in a few lines: what came in from colleagues (`git log --oneline <before>..<pulled>`,
grouped by author), what you pushed (commit subjects), what you installed, and anything left
undone (a conflict you asked about, a failing test).
