#!/usr/bin/env bash
# Create .venv and install what the code needs. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  echo "creating .venv with python3 ($(python3 --version))"
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo "python packages installed"

for tool in ffmpeg ffprobe git; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done
echo "ffmpeg, ffprobe and git are here"

if [ ! -x "$HOME/.local/bin/claude" ] && ! command -v claude >/dev/null; then
  echo "warning: the claude command was not found; writing the content will fail" >&2
fi

echo "setup OK — try:  ./run.sh --skip-voice"
