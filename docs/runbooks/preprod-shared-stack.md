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
