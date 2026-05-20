#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${MODEL:-qwen2.5-coder:7b}"
USER_PROMPT="${PROMPT:-Przeanalizuj stan repo i zaproponuj kolejny najmniejszy sensowny krok.}"

cd "$ROOT_DIR"

if ! command -v codex >/dev/null 2>&1; then
  echo "❌ codex not found in PATH"
  exit 127
fi

branch="$(git branch --show-current)"
status_short_branch="$(git status --short --branch)"
diff_shortstat="$(git diff --shortstat || true)"
head_short="$(git rev-parse --short HEAD)"

read -r -d '' FULL_PROMPT <<EOF || true
Repo truth preflight (terminal source of truth):
- branch: ${branch}
- head: ${head_short}
- git status --short --branch:
${status_short_branch}
- git diff --shortstat:
${diff_shortstat}

Rules:
1. Treat the preflight as authoritative for current repo state.
2. If you claim repo state, reference the preflight fields above.
3. If additional verification is needed, use terminal tools instead of guessing.
4. Return a concise operational response.

User task:
${USER_PROMPT}
EOF

echo "🧭 Running repo-truth-first agent session"
echo "model=${MODEL}"

exec codex exec \
  --json \
  --oss \
  --local-provider ollama \
  -m "${MODEL}" \
  --cd "$ROOT_DIR" \
  --sandbox workspace-write \
  "$FULL_PROMPT"
