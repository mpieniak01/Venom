#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

upstream_ref=""
if upstream_ref="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"; then
  :
fi

changed_files=""
if [[ -n "$upstream_ref" ]]; then
  changed_files="$(git diff --name-only "${upstream_ref}...HEAD")"
else
  base_ref="$(git merge-base HEAD origin/main 2>/dev/null || git rev-list --max-parents=0 HEAD | tail -n1)"
  changed_files="$(git diff --name-only "${base_ref}...HEAD")"
fi

if [[ -z "${changed_files}" ]]; then
  echo "ℹ️ pre-push quality gate: brak zmian względem gałęzi bazowej, pomijam."
  exit 0
fi

if ! grep -Eq '^(venom_core/|web-next/|tests/|services/|scripts/|config/|Makefile|make/|\.github/workflows/)' <<<"${changed_files}"; then
  echo "ℹ️ pre-push quality gate: brak zmian kodu/testów/konfiguracji CI, pomijam."
  exit 0
fi

echo "🔒 pre-push quality gate: uruchamiam make pr-fast..."
make --no-print-directory pr-fast
echo "✅ pre-push quality gate: wszystkie bramki zielone."
