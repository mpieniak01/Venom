#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${PR_BASE_REF:-origin/main}"
VENV="${VENV:-.venv}"
DIFF_BASE="$BASE_REF"
DIFF_BASE_REASON="explicit base ref"

backend_changed=0
frontend_changed=0

if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  if MERGE_BASE="$(git merge-base HEAD "$BASE_REF" 2>/dev/null)"; then
    DIFF_BASE="$MERGE_BASE"
    DIFF_BASE_REASON="merge-base with ${BASE_REF}"
    CHANGED_FILES="$(git diff --name-only "${MERGE_BASE}...HEAD")"
  else
    echo "⚠️ Cannot resolve merge-base with '$BASE_REF' (shallow/grafted history)."
    DIFF_BASE="HEAD~1"
    DIFF_BASE_REASON="fallback because merge-base is unavailable"
    CHANGED_FILES="$(git diff --name-only HEAD~1..HEAD)"
  fi
else
  echo "⚠️ Base ref '$BASE_REF' not found. Falling back to HEAD~1."
  DIFF_BASE="HEAD~1"
  DIFF_BASE_REASON="fallback because base ref is unavailable"
  CHANGED_FILES="$(git diff --name-only HEAD~1..HEAD)"
fi

if [[ -z "${CHANGED_FILES}" ]]; then
  echo "ℹ️ No changes detected against base. Running minimal backend gate."
  backend_changed=1
fi

while IFS= read -r file; do
  [[ -z "$file" ]] && continue

  case "$file" in
    web-next/*)
      frontend_changed=1
      ;;
    *)
      ;;
  esac

  case "$file" in
    venom_core/*|tests/*|scripts/*|config/pytest-groups/*|Makefile|pytest.ini|sonar-project.properties|requirements*.txt)
      backend_changed=1
      ;;
    *)
      ;;
  esac
done <<< "$CHANGED_FILES"

echo "🔎 PR fast check scope:"
echo "  - backend_changed=${backend_changed}"
echo "  - frontend_changed=${frontend_changed}"
echo "  - base_ref=${BASE_REF}"
echo "  - diff_base=${DIFF_BASE}"
echo "  - diff_base_reason=${DIFF_BASE_REASON}"

if [[ "$backend_changed" -eq 1 ]]; then
  echo "▶ Backend fast lane: compile + ci-lite audit + changed-lines coverage gate"
  PYTHON_BIN="python3"
  if [[ -x "${VENV}/bin/python" ]]; then
    PYTHON_BIN="${VENV}/bin/python"
  fi
  "${PYTHON_BIN}" -m compileall -q venom_core scripts tests
  make ci-lite-preflight
  make audit-ci-lite
  make check-new-code-coverage \
    NEW_CODE_INCLUDE_BASELINE=1 \
    NEW_CODE_BASELINE_GROUP=config/pytest-groups/ci-lite.txt \
    NEW_CODE_TEST_GROUP=config/pytest-groups/sonar-new-code.txt \
    NEW_CODE_COV_TARGET=venom_core \
    NEW_CODE_COVERAGE_MIN=0 \
    NEW_CODE_DIFF_BASE="${DIFF_BASE}"
fi

if [[ "$frontend_changed" -eq 1 ]]; then
  echo "▶ Frontend fast lane: lint + ci-lite unit tests"
  npm --prefix web-next run lint
  npm --prefix web-next run test:unit:ci-lite
fi

if [[ "$backend_changed" -eq 0 ]] && [[ "$frontend_changed" -eq 0 ]]; then
  echo "ℹ️ Only docs/meta changes detected. No test lane required."
fi

echo "✅ PR fast check passed."
