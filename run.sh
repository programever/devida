#!/usr/bin/env bash
# One DeViDa run. Same command by hand or from the systemd timer.
#   ./run.sh                 build today and publish the page
#   ./run.sh --dry-run       build everything, publish nothing
#   ./run.sh --skip-voice    content only, no audio, no publish
#   ./run.sh --publish-only  rebuild the page from days already on this box
#   ./run.sh --force         build today again from scratch
#   ./run.sh --date 2026-09-15   a different day
set -euo pipefail
cd "$(dirname "$0")"

# systemd user units get a bare PATH, and claude/node live under ~/.local and nvm.
export PATH="$HOME/.local/bin:$PATH"

if [ ! -x .venv/bin/python ]; then
  echo "no .venv — run ./setup.sh first" >&2
  exit 2
fi

exec .venv/bin/python -m pipeline.main "$@"
