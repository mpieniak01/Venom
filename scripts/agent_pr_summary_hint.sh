#!/usr/bin/env bash
set -euo pipefail

reason="$(
  cat | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw) if raw else {}
except Exception:
    data = {}
print(data.get("reason", ""))
'
)"

if [[ "${reason}" == "cancel" || "${reason}" == "cancelled" || "${reason}" == "error" || "${reason}" == "failed" ]]; then
  exit 0
fi

cat <<'TXT'
Reminder: Fill PR report sections from .github/pull_request_template.md:
- Quality Gates
- Commands run + pass/fail
- Changed-lines coverage %
- Risks/limitations/skips with justification
TXT
