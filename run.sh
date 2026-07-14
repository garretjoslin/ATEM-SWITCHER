#!/usr/bin/env bash
# One-command bootstrap + run for the Mic → Cam ATEM switcher.
# First run: creates a virtualenv and installs dependencies. Every run: starts the server.
# Override host/port:  HOST=0.0.0.0 PORT=8080 ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

# Find a Python 3.10+ interpreter (the code uses 3.10+ syntax).
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    ver="$("$c" -c 'import sys; print(sys.version_info[0] * 100 + sys.version_info[1])')"
    if [ "$ver" -ge 310 ]; then PY="$c"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "ERROR: need Python 3.10+ but none was found." >&2
  echo "Install it, e.g.:  brew install python@3.12" >&2
  exit 1
fi

# Create the venv + install deps if missing OR broken/incomplete.
# (Check for the interpreter itself, not just the .venv folder — a half-created venv
# would otherwise be skipped and then fail at exec time.)
if [ ! -x .venv/bin/python ]; then
  echo "Creating virtualenv with $PY ..."
  rm -rf .venv
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  echo "Installing dependencies ..."
  .venv/bin/python -m pip install -r requirements.txt
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-4590}"
echo "Starting mic-cam-switcher on http://$HOST:$PORT   (Ctrl-C to stop)"
exec .venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
