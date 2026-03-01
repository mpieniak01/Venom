# Pre-prod on Shared Stack (Data Isolation)

## Scope
- Shared technical stack (`dev` + `pre-prod` on same services).
- Hard data isolation through logical namespaces.
- `pre-prod` allows only read-only smoke automation and manual UAT.

## Required Environment Variables
- `ENVIRONMENT_ROLE=dev|preprod`
- `DB_SCHEMA=dev|preprod`
- `CACHE_NAMESPACE=venom|preprod`
- `QUEUE_NAMESPACE=venom|preprod`
- `STORAGE_PREFIX=` (dev) or `preprod`
- `ALLOW_DATA_MUTATION=0|1`

## Pre-prod Guard Rules
- `ENVIRONMENT_ROLE=preprod` requires:
- `DB_SCHEMA=preprod`
- `CACHE_NAMESPACE=preprod`
- `QUEUE_NAMESPACE=preprod`
- `STORAGE_PREFIX=preprod`
- Any destructive operation is blocked when `ALLOW_DATA_MUTATION=0`.
- Optional modules:
- `API_OPTIONAL_MODULES` must use `manifest:/.../module.json` entries only,
- module manifest must include `backend.data_policy`,
- mutating module endpoints must honor the global mutation guard.

## Optional Module Write Matrix
- Module data root: `data/modules/<storage_prefix_or_dev>/<module_id>/`.
- Example module state files:
- `runtime-state.json`
- `candidates-cache.json`
- `accounts-state.json`
- `monitoring-state.json`
- Not allowed: global non-namespaced paths (for example `/tmp/<module>/*`).

## Writer Matrix (Current)
- Queue/task metadata in Redis: `${CACHE_NAMESPACE}:task:*`
- ARQ queues/channels: `${QUEUE_NAMESPACE}:tasks:*`, `${QUEUE_NAMESPACE}:broadcast`
- Workspace data: `${WORKSPACE_ROOT}` (prefixed when `STORAGE_PREFIX=preprod`)
- Memory/vector/session data: `${MEMORY_ROOT}` (prefixed when `STORAGE_PREFIX=preprod`)
- Academy data: `${ACADEMY_TRAINING_DIR}`, `${ACADEMY_MODELS_DIR}`, `${ACADEMY_USER_DATA_DIR}`

## Read-only Smoke for Pre-prod
- Run: `make test-preprod-readonly-smoke`
- Contract:
- only GET/read endpoints
- no data mutation
- `ALLOW_DATA_MUTATION=0`

## Operational Notes
- Cleanup scripts are blocked by default in pre-prod:
- `scripts/dev/env_cleanup.sh`
- `scripts/dev/docker_cleanup.sh`
- To run destructive maintenance intentionally:
- set `ALLOW_DATA_MUTATION=1`
- run with auditable change window and rollback plan

## Related Runbooks
- `docs/runbooks/preprod-backup-restore.md`
- `docs/runbooks/preprod-uat-procedure.md`
- `docs/runbooks/preprod-access-audit.md`
- `docs/runbooks/preprod-release-checklist.md`
