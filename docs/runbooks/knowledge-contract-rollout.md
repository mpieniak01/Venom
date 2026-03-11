# Runbook: Knowledge Contract Rollout (200B)

## Goal

Roll out canonical `KnowledgeEntry` contract safely:
- backend first (`GET /api/v1/knowledge/entries`),
- then UI consumers,
- with explicit validation and rollback path.

## Scope

- Canonical read endpoint: `GET /api/v1/knowledge/entries`
- Lessons mutation payload: `mutation.{target,action,source,affected_count,scope,filter}`
- Audit for successful lessons mutations:
  - `source=knowledge.lessons`
  - `action=mutation.applied`

## Phase 1: Backend-only rollout

1. Deploy backend with federated endpoint and mutation/audit contract.
2. Keep existing knowledge/memory/lessons endpoints as compatibility path.
3. Validate:
   - `GET /api/v1/knowledge/entries` returns entries from session/lessons/vector/graph.
   - `DELETE /api/v1/lessons/prune/latest?count=1` returns `mutation`.
   - Audit stream contains `knowledge.lessons / mutation.applied`.

## Phase 2: UI gradual adoption

1. Add read path in UI using `knowledge/entries` behind feature flag.
2. Compare old vs new sources in staging (count, source distribution, session filters).
3. Enable by default after parity checks pass.

## Phase 3: Contract hardening

1. Treat `knowledge/entries` as canonical read source for knowledge views.
2. Keep legacy endpoints for compatibility until explicit deprecation window.
3. Add release note before deprecating any legacy DTO dependency.

## Verification checklist

1. `make pr-fast` green.
2. Contract tests for `knowledge/entries` green.
3. Mutation guard tests (`403` canonical payload) green.
4. Mutation success audit checks green.
5. No critical Sonar findings in changed files.

## Rollback

1. Disable UI feature flag for `knowledge/entries`.
2. Continue using legacy endpoint paths in UI.
3. Keep backend deployed if mutation/audit contract remains compatible.
4. If necessary, rollback backend to last known good tag.

## Known risks

1. Partial source availability in federated read if one store is degraded.
2. Query cost increase for high `limit` without cache.
3. UI assumptions tied to legacy fields outside canonical DTO.
