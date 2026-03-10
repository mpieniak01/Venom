#!/usr/bin/env bash
set -euo pipefail

port="${1:-}"
if [[ -z "$port" ]]; then
  echo "Usage: $0 <tcp_port>" >&2
  exit 2
fi

if ! [[ "$port" =~ ^[0-9]+$ ]]; then
  echo "Invalid port: '$port'" >&2
  exit 2
fi

pids=""

if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
fi

if [[ -z "$pids" ]] && command -v fuser >/dev/null 2>&1; then
  pids="$(fuser -n tcp "$port" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)"
fi

if [[ -z "$pids" ]] && command -v ss >/dev/null 2>&1; then
  pids="$(
    ss -ltnp 2>/dev/null \
      | awk -v p="$port" '
          index($0, ":" p " ") {
            while (match($0, /pid=[0-9]+/)) {
              print substr($0, RSTART + 4, RLENGTH - 4)
              $0 = substr($0, RSTART + RLENGTH)
            }
          }
        ' \
      | sort -u || true
  )"
fi

if [[ -n "$pids" ]]; then
  printf '%s\n' "$pids" | tr -s ' ' '\n' | grep -E '^[0-9]+$' | sort -u
fi
