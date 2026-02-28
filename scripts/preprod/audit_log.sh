#!/usr/bin/env bash
set -euo pipefail

ACTOR="${1:-unknown}"
ACTION="${2:-manual-operation}"
TICKET="${3:-N/A}"
RESULT="${4:-OK}"
AUDIT_LOG="${AUDIT_LOG:-logs/preprod_audit.log}"

mkdir -p "$(dirname "${AUDIT_LOG}")"

timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 - "${timestamp}" "${ACTOR}" "${ACTION}" "${TICKET}" "${RESULT}" >> "${AUDIT_LOG}" <<'PY'
import json
import sys

ts, actor, action, ticket, result = sys.argv[1:]
print(
    json.dumps(
        {
            "ts": ts,
            "actor": actor,
            "action": action,
            "ticket": ticket,
            "result": result,
        },
        ensure_ascii=False,
    )
)
PY

echo "✅ Audit event zapisany do ${AUDIT_LOG}"
