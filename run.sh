#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [ -d "venv" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

PORT="${PORT:-8420}"

# Reload-on-change is right at a terminal and wrong for a service that should
# just stay up. WV_RELOAD=0 turns it off; the launchd job sets that.
if [ "${WV_RELOAD:-1}" = "0" ]; then
  exec uvicorn server.main:app --host 0.0.0.0 --port "$PORT"
else
  exec uvicorn server.main:app --host 0.0.0.0 --port "$PORT" --reload
fi
