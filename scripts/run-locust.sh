#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${LOCUST_WEB_PORT:-8089}"
HOST="${LOCUST_WEB_HOST:-127.0.0.1}"
TARGET="${LOCUST_TARGET:-http://localhost:8000}"

if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -ti tcp:"${PORT}" 2>/dev/null || true)"
  if [[ -n "${PIDS}" ]]; then
    echo "⚠️  Port ${PORT} jest zajęty (PID: ${PIDS}) – zakańczam procesy."
    xargs -r kill <<<"${PIDS}" || true
    sleep 0.3
  fi
fi

echo "🚀 Panel Locusta: http://${HOST}:${PORT}"
echo "   TARGET API: ${TARGET}"
cd "${REPO_ROOT}"
exec locust \
  -f tests/perf/locustfile.py \
  --web-host "${HOST}" \
  --web-port "${PORT}" \
  --host "${TARGET}"
