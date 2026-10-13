#!/usr/bin/env bash
# editassist setup for macOS / Linux. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

have() { command -v "$1" >/dev/null 2>&1; }

if [[ "$(uname)" == "Darwin" ]] && ! have brew; then
  echo "Homebrew is required: https://brew.sh" >&2; exit 1
fi
install() {  # install <command> <brew formula> <apt package>
  have "$1" && return
  echo "installing $2 ..."
  if have brew; then brew install "$2"; elif have apt-get; then sudo apt-get install -y "$3"; else
    echo "please install $2 manually" >&2; exit 1; fi
}
install ffmpeg ffmpeg ffmpeg
install node node nodejs
if ! have uv; then
  echo "installing uv ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

uv sync
(cd remotion && npm install --no-audit --no-fund)

uv run ea memory --init >/dev/null  # memory-os global tier if installed, else gitignored memory/
[[ -f .env ]] || cp .env.example .env

# DaVinci Resolve MCP (live control of a running Resolve Studio); optional, skipped on failure
if [[ -d "/Applications/DaVinci Resolve" || -d /opt/resolve ]]; then
  uv run ea resolve-mcp --setup || echo "Resolve MCP setup failed: rerun later with 'uv run ea resolve-mcp --setup'"
fi

# Premiere Pro live bridge (editassist UXP panel): installed on request, it lets the agent edit Premiere
if [[ -d "/Applications/Adobe Premiere Pro 2026" || -d "/Applications/Adobe Premiere Pro 2025" ]]; then
  echo "Premiere Pro found: run 'uv run ea premiere install' to let editassist edit it live."
fi

uv run ea doctor || true
echo
echo "Done. Open this folder in Claude Code (\`claude\`) or Codex and describe the video you want."
