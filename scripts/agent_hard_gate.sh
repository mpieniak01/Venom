#!/usr/bin/env bash
set -euo pipefail

# Hook payload comes from stdin as JSON.
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

# Explicit override for confirmed environment blocker (must be documented in PR).
if [[ "${HARD_GATE_ENV_BLOCKER:-0}" == "1" ]]; then
  echo "Hard Gate bypass enabled via HARD_GATE_ENV_BLOCKER=1 (environment blocker)." >&2
  exit 0
fi

# Skip only when session clearly ended as cancel/error.
if [[ "${reason}" == "cancel" || "${reason}" == "cancelled" || "${reason}" == "error" || "${reason}" == "failed" ]]; then
  exit 0
fi

# Skip hard gate for markdown-only change sets.
collect_changed_files() {
  {
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | sed '/^$/d' | sort -u
}

mapfile -t changed_files < <(collect_changed_files)
if [[ "${#changed_files[@]}" -gt 0 ]]; then
  markdown_only=1
  for file_path in "${changed_files[@]}"; do
    if [[ "${file_path}" != *.md ]]; then
      markdown_only=0
      break
    fi
  done
  if [[ "${markdown_only}" -eq 1 ]]; then
    echo "Hard Gate skipped: markdown-only change set (*.md)." >&2
    exit 0
  fi
fi

tmp_log="$(mktemp)"
trap 'rm -f "$tmp_log"' EXIT

run_gate() {
  echo "==> Running: $*" | tee -a "$tmp_log"
  if "$@" 2>&1 | tee -a "$tmp_log"; then
    echo "RESULT: PASS :: $*" | tee -a "$tmp_log"
  else
    echo "RESULT: FAIL :: $*" | tee -a "$tmp_log"
    return 1
  fi
}

status_pr_fast=0
run_gate make pr-fast || status_pr_fast=1

status=$((status_pr_fast))

coverage_line="$(grep -E 'Changed lines coverage:' "$tmp_log" | tail -n 1 || true)"

echo
echo "=== Coding Agent Hard Gate Report ==="
if [[ "$status_pr_fast" -eq 0 ]]; then
  echo "- make pr-fast: PASS"
else
  echo "- make pr-fast: FAIL"
fi
if [[ -n "$coverage_line" ]]; then
  echo "- ${coverage_line}"
fi
echo "====================================="

if [[ "$status" -ne 0 ]]; then
  echo "Hard Gate failed. Fix issues and rerun gates before completion." >&2
  exit 2
fi
