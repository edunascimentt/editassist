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

[[ -d memory ]] || cp -R memory.template memory
[[ -f .env ]] || cp .env.example .env

uv run ea doctor || true
echo
echo "Done. Open this folder in Claude Code (\`claude\`) or Codex and describe the video you want."
