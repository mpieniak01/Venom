#!/usr/bin/env bash
set -euo pipefail

ACTOR="${1:-unknown}"
ACTION="${2:-manual-operation}"
TICKET="${3:-N/A}"
RESULT="${4:-OK}"
AUDIT_LOG="${AUDIT_LOG:-logs/preprod_audit.log}"

mkdir -p "$(dirname "${AUDIT_LOG}")"

timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '{"ts":"%s","actor":"%s","action":"%s","ticket":"%s","result":"%s"}\n' \
  "${timestamp}" "${ACTOR}" "${ACTION}" "${TICKET}" "${RESULT}" >> "${AUDIT_LOG}"

echo "✅ Audit event zapisany do ${AUDIT_LOG}"
