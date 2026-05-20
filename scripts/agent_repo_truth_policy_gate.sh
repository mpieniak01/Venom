#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "🔒 Repo-truth policy gate (sessionEnd)"

if ! command -v jq >/dev/null 2>&1; then
  echo "❌ Missing jq"
  echo "Install jq or run the gate in an environment that provides it."
  exit 2
fi

DECISION_REPORT="test-results/235/decision_gate.json"
PR237_REPORT="test-results/237/agent_decision_gate.json"

if [[ ! -f "$DECISION_REPORT" ]]; then
  echo "❌ Missing $DECISION_REPORT"
  echo "Run: make local-first-decision-gate STRICT_REPO_TRUTH=1"
  exit 2
fi

if [[ ! -f "$PR237_REPORT" ]]; then
  echo "❌ Missing $PR237_REPORT"
  echo "Run: make local-first-agent-decision-gate"
  exit 2
fi

decision_verdict="$(jq -r '.verdict // "missing"' "$DECISION_REPORT")"
pr237_verdict="$(jq -r '.verdict // "missing"' "$PR237_REPORT")"

if [[ "$decision_verdict" != "pass" ]]; then
  echo "❌ Repo-truth strict gate failed: $DECISION_REPORT verdict=$decision_verdict"
  exit 2
fi

if [[ "$pr237_verdict" != "pass" ]]; then
  echo "❌ PR237 decision gate failed: $PR237_REPORT verdict=$pr237_verdict"
  exit 2
fi

echo "✅ Repo-truth policy gate passed"
