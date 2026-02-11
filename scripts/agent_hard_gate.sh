#!/usr/bin/env bash
set -euo pipefail

# Hook payload comes from stdin as JSON.
payload="$(cat || true)"
reason="$(python3 - <<'PY' "$payload"
import json, sys
raw = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    data = json.loads(raw) if raw else {}
except Exception:
    data = {}
print(data.get("reason", ""))
PY
)"

# Skip only when session clearly ended as cancel/error.
if [[ "${reason}" == "cancel" || "${reason}" == "cancelled" || "${reason}" == "error" || "${reason}" == "failed" ]]; then
  exit 0
fi

tmp_log="$(mktemp)"
trap 'rm -f "$tmp_log"' EXIT

run_gate() {
  local cmd="$1"
  echo "==> Running: ${cmd}" | tee -a "$tmp_log"
  if eval "${cmd}" 2>&1 | tee -a "$tmp_log"; then
    echo "RESULT: PASS :: ${cmd}" | tee -a "$tmp_log"
  else
    echo "RESULT: FAIL :: ${cmd}" | tee -a "$tmp_log"
    return 1
  fi
}

status=0
run_gate "make pr-fast" || status=1
run_gate "make check-new-code-coverage" || status=1

coverage_line="$(grep -E 'Changed lines coverage:' "$tmp_log" | tail -n 1 || true)"

echo
echo "=== Coding Agent Hard Gate Report ==="
echo "- make pr-fast: $([[ "$status" -eq 0 ]] && echo "PASS" || grep -q 'RESULT: FAIL :: make pr-fast' "$tmp_log" && echo "FAIL" || echo "PASS")"
echo "- make check-new-code-coverage: $([[ "$status" -eq 0 ]] && echo "PASS" || grep -q 'RESULT: FAIL :: make check-new-code-coverage' "$tmp_log" && echo "FAIL" || echo "PASS")"
if [[ -n "$coverage_line" ]]; then
  echo "- ${coverage_line}"
fi
echo "====================================="

if [[ "$status" -ne 0 ]]; then
  echo "Hard Gate failed. Fix issues and rerun gates before completion." >&2
  exit 2
fi
