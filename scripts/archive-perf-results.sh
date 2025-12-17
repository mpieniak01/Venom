#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${1:-perf-artifacts}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="${REPO_ROOT}/${DEST_DIR}/${TIMESTAMP}"

mkdir -p "${TARGET}"

copy_if_exists() {
  local path="$1"
  local label="$2"
  if [ -d "${path}" ] || [ -f "${path}" ]; then
    echo "📁 Archiwizuję ${label} -> ${TARGET}/$(basename "${path}")"
    cp -a "${path}" "${TARGET}/"
  fi
}

copy_if_exists "${REPO_ROOT}/test-results" "test-results"
copy_if_exists "${REPO_ROOT}/playwright-report" "playwright-report"
copy_if_exists "${REPO_ROOT}/web-next/test-results" "web-next/test-results"
copy_if_exists "${REPO_ROOT}/web-next/playwright-report" "web-next/playwright-report"
copy_if_exists "${REPO_ROOT}/locust.stats.csv" "locust.stats.csv"
copy_if_exists "${REPO_ROOT}/locust.failures.csv" "locust.failures.csv"

echo "✅ Artefakty zapisane w ${TARGET}"
