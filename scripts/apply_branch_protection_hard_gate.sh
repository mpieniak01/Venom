#!/usr/bin/env bash
set -euo pipefail

# Applies branch protection hard-gate policy for main branch.
# Requires: gh CLI authenticated with repo admin permissions.

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required. Install GitHub CLI first." >&2
  exit 1
fi

repo="${1:-}"
if [[ -z "${repo}" ]]; then
  repo="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
fi

if [[ -z "${repo}" ]]; then
  echo "Unable to resolve repository. Pass 'owner/repo' as first argument." >&2
  exit 1
fi

echo "Applying branch protection to ${repo} (branch: main)"

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${repo}/branches/main/protection" \
  -f required_status_checks.strict=true \
  -f required_status_checks.contexts[]="Backend lite (pytest)" \
  -f required_status_checks.contexts[]="Frontend lite (lint)" \
  -f required_status_checks.contexts[]="SonarCloud Scan" \
  -f required_status_checks.contexts[]="Quick validator (syntax + CI-lite deps)" \
  -f enforce_admins=true \
  -f required_pull_request_reviews.dismiss_stale_reviews=true \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  # Keep restrictions unset intentionally: repo-level contributor permissions
  # and PR requirement are the primary controls in this policy.
  -F restrictions= \
  -f allow_force_pushes=false \
  -f allow_deletions=false \
  -f block_creations=false \
  -f required_conversation_resolution=true \
  -f lock_branch=false \
  -f allow_fork_syncing=true >/dev/null

echo "Branch protection applied successfully."
