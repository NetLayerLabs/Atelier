#!/usr/bin/env bash
# Start the Atelier backend (port 8787) and frontend (port 3100) together. Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8787}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Free it or set BACKEND_PORT / FRONTEND_PORT." >&2
    exit 1
  fi
done

[ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && pnpm install)

trap 'kill 0' EXIT INT TERM
(cd "$ROOT/backend" && PUBLIC_BASE_URL="http://localhost:$BACKEND_PORT" \
  uv run uvicorn app.main:app --port "$BACKEND_PORT") &
(cd "$ROOT/frontend" && NEXT_PUBLIC_API_BASE="http://localhost:$BACKEND_PORT" \
  pnpm exec next dev -p "$FRONTEND_PORT") &

echo "Atelier: http://localhost:$FRONTEND_PORT  (API http://localhost:$BACKEND_PORT/docs)"
wait
