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
has_frontend_change=0
has_backend_change=0
has_python_tests_change=0
if [[ "${#changed_files[@]}" -gt 0 ]]; then
  markdown_only=1
  for file_path in "${changed_files[@]}"; do
    if [[ "${file_path}" == web-next/* ]]; then
      has_frontend_change=1
    fi
    if [[ "${file_path}" == venom_core/* || "${file_path}" == scripts/* || "${file_path}" == make/* || "${file_path}" == config/testing/* || "${file_path}" == config/pytest-groups/* ]]; then
      has_backend_change=1
    fi
    if [[ "${file_path}" == tests/* && "${file_path}" == *.py ]]; then
      has_python_tests_change=1
      has_backend_change=1
    fi
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
commands_executed=()
routing_decisions=()

run_gate() {
  local cmd=("$@")
  local cmd_str="${cmd[*]}"
  commands_executed+=("$cmd_str")
  echo "==> Running: ${cmd_str}" | tee -a "$tmp_log"
  if "${cmd[@]}" 2>&1 | tee -a "$tmp_log"; then
    echo "RESULT: PASS :: ${cmd_str}" | tee -a "$tmp_log"
  else
    echo "RESULT: FAIL :: ${cmd_str}" | tee -a "$tmp_log"
    return 1
  fi
}

status_frontend_ci=0
status_frontend_lint=0
status_test_catalog=0
status_test_groups=0
status_new_code_diag=0
status_pr_fast=0

if [[ "$has_frontend_change" -eq 1 ]]; then
  routing_decisions+=("frontend_scope=true")
  run_gate npm --prefix web-next ci || status_frontend_ci=1
  if [[ "$status_frontend_ci" -eq 0 ]]; then
    run_gate npm --prefix web-next run lint || status_frontend_lint=1
  fi
else
  routing_decisions+=("frontend_scope=false")
fi

if [[ "$has_backend_change" -eq 1 || "$has_python_tests_change" -eq 1 ]]; then
  routing_decisions+=("python_scope=true")
  run_gate make test-catalog-check || status_test_catalog=1
  run_gate make test-groups-check || status_test_groups=1
  run_gate make check-new-code-coverage-diagnostics || status_new_code_diag=1
else
  routing_decisions+=("python_scope=false")
fi

run_gate make pr-fast || status_pr_fast=1

status=$((status_frontend_ci + status_frontend_lint + status_test_catalog + status_test_groups + status_new_code_diag + status_pr_fast))

coverage_line="$(grep -E 'Changed lines coverage:' "$tmp_log" | tail -n 1 || true)"

echo
echo "=== Coding Agent Hard Gate Report ==="
echo "- routing:"
for decision in "${routing_decisions[@]}"; do
  echo "  * ${decision}"
done
echo "- executed commands:"
for command in "${commands_executed[@]}"; do
  echo "  * ${command}"
done
if [[ "$status_frontend_ci" -eq 0 ]]; then
  echo "- npm --prefix web-next ci: PASS/SKIP"
else
  echo "- npm --prefix web-next ci: FAIL"
fi
if [[ "$status_frontend_lint" -eq 0 ]]; then
  echo "- npm --prefix web-next run lint: PASS/SKIP"
else
  echo "- npm --prefix web-next run lint: FAIL"
fi
if [[ "$status_test_catalog" -eq 0 ]]; then
  echo "- make test-catalog-check: PASS/SKIP"
else
  echo "- make test-catalog-check: FAIL"
fi
if [[ "$status_test_groups" -eq 0 ]]; then
  echo "- make test-groups-check: PASS/SKIP"
else
  echo "- make test-groups-check: FAIL"
fi
if [[ "$status_new_code_diag" -eq 0 ]]; then
  echo "- make check-new-code-coverage-diagnostics: PASS/SKIP"
else
  echo "- make check-new-code-coverage-diagnostics: FAIL"
fi
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
  echo "Hard Gate failed. Resolve failures, then rerun targeted gates and make pr-fast." >&2
  exit 2
fi
