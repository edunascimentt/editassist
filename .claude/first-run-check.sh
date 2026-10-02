#!/usr/bin/env bash
# Committed with this repo. Runs at the start of every Claude Code session.
# First time on a machine (no .editassist/setup.json yet), it tells Claude to start the guided
# setup on the user's first message. Read-only: it tests for one file and prints a message.
# The editassist-setup skill writes the file when it finishes (or when the user skips it).
# Re-trigger: `uv run ea setup-done --reset` (or delete .editassist/setup.json).
set -u
ROOT="${CLAUDE_PROJECT_DIR:-.}"
[ -f "$ROOT/.editassist/setup.json" ] && exit 0

USER_MSG="editassist: first session on this machine — the guided setup will start with your first message (you can skip it)."
MODEL_CTX="FIRST RUN of editassist on this machine (.editassist/setup.json is missing). On the user's FIRST message in this session, before doing what they asked, invoke the editassist-setup skill. Open with one short line in the user's language saying this looks like the first time here and you'll set things up (dependencies, API keys, editors, preferences), and offer to skip. If they skip, run: uv run ea setup-done --skipped (if uv isn't installed yet, create .editassist/setup.json with {\"status\":\"skipped\"} yourself). Then continue with their request."

esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk 'NR>1{printf "\\n"} {printf "%s", $0}'; }
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' \
  "$(esc "$USER_MSG")" "$(esc "$MODEL_CTX")"
exit 0
