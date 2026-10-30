# Environment Support Matrix

Status snapshot date: **2026-10-30**

This document is the source of truth for which environments are currently supported in practice.

Main entry points:
- `README.md`
- `README_PL.md`

## Current Support Status

| Environment | Status | Maturity | Notes |
|---|---|---|---|
| `dev` | Supported | Production-ready for engineering work | Main development/testing environment used daily. |
| `preprod` | Supported (rollout phase) | Operational, stabilizing | Started as shared-stack + data isolation model. Used for read-only smoke + manual UAT. |
| `prod` | Planned | Not active yet | Target environment only. Not recommended and not validated for operational use yet. |

## Active Configuration Model

Current operational model:
- default Full/dev with Turbopack; Full/Light × dev/preprod are the four active combinations
- shared source/installations, independent processes and data/log/PID/build/provider-state paths
- prod retained but unused; [launch contract](STACK_PROFILES.md)

Environment config files:
- `dev` runtime: `.env.dev` (local, not committed)
- `dev` template: `.env.dev.example` (safe for Git)
- `preprod` runtime: `.env.preprod` (local, not committed)
- `preprod` template: `.env.preprod.example` (safe for Git)

Selection rule:
- select PROFILE=full|light and ENVIRONMENT=dev|preprod through Make
- scripts/dev/stack_profile.py merges dotenv as data and applies profile/isolation rules once
- Light forces background pause and no LLM warmup; preprod forces read-only
- shell helpers retain the resolved values with dotenv --no-override
- effective priority: `make VAR=...` / exported env > value from `ENV_FILE` > script default
- runtime-domain keys (`ACTIVE_LLM_SERVER`, `VLLM_*`, `OLLAMA_*`) belong to `.env*` as source-of-truth
- no bare `.env` / `.env.example` in runtime contract

Operational note:
- `VLLM_ENDPOINT` in `Makefile` intentionally defaults to empty; stack startup resolves it from `.env*` and only then falls back to script default (`http://127.0.0.1:8001/v1`).

Key environment variables:
- `ENVIRONMENT_ROLE=dev|preprod`
- `DB_SCHEMA=dev|preprod`
- `CACHE_NAMESPACE=venom|preprod`
- `QUEUE_NAMESPACE=venom|preprod`
- `STORAGE_PREFIX=` (dev) or `preprod`
- `ALLOW_DATA_MUTATION=0|1`

## Preprod Rules (Current)

For `ENVIRONMENT_ROLE=preprod`:
- `DB_SCHEMA=preprod`
- `CACHE_NAMESPACE=preprod`
- `QUEUE_NAMESPACE=preprod`
- `STORAGE_PREFIX=preprod`
- destructive operations blocked when `ALLOW_DATA_MUTATION=0`

Optional modules contract (mandatory):
- `API_OPTIONAL_MODULES` accepts only `manifest:/.../module.json` entries.
- each module manifest must include `backend.data_policy`:
  - `storage_mode=core_prefixed`
  - `mutation_guard=core_environment_policy`
  - `state_files=[...]`
- optional-module mutations in `preprod` are subject to the same global block (`ALLOW_DATA_MUTATION=0`).

Read-only smoke command:
```bash
make test-preprod-readonly-smoke
```

Test enforcement model:
- Default CI/test lane validates `dev` behavior (`make pr-fast` / backend lite checks).
- `preprod` is validated only by dedicated read-only smoke lane.
- `tests/test_preprod_readonly_smoke.py` hard-fails outside `ENVIRONMENT_ROLE=preprod` or when `ALLOW_DATA_MUTATION != 0`.

## How To Run Tests (dev vs preprod)

Dev tests (default):
```bash
make test
make pr-fast
```

Dev tests (manual pytest):
```bash
ENV_FILE=.env.dev ENV_EXAMPLE_FILE=.env.dev.example \
ENVIRONMENT_ROLE=dev DB_SCHEMA=dev CACHE_NAMESPACE=venom QUEUE_NAMESPACE=venom STORAGE_PREFIX= ALLOW_DATA_MUTATION=1 \
pytest -q
```

Preprod tests (readonly only):
```bash
make test-preprod-readonly-smoke
```

Preprod tests (manual pytest, readonly contract):
```bash
ENV_FILE=.env.preprod ENV_EXAMPLE_FILE=.env.preprod.example \
ENVIRONMENT_ROLE=preprod DB_SCHEMA=preprod CACHE_NAMESPACE=preprod QUEUE_NAMESPACE=preprod STORAGE_PREFIX=preprod ALLOW_DATA_MUTATION=0 \
pytest -q tests/test_preprod_readonly_smoke.py -m smoke
```

Rules:
- Do not run full/destructive test suites against `preprod`.
- `prod` test/deploy flow is not validated yet and is currently not recommended.

Preprod startup commands:
```bash
make ensure-preprod-env-file
make stack-plan ENVIRONMENT=preprod PROFILE=full
make start ENVIRONMENT=preprod PROFILE=full
make start ENVIRONMENT=preprod PROFILE=light
make status ENVIRONMENT=preprod
make stop ENVIRONMENT=preprod
```

Old preprod aliases delegate to this contract and are scheduled for removal after migration.
Preprod keeps its database, cache/queue namespaces and logs. UI/API ports, PID records,
Next dist artifacts and mutable OpenRouter/Vast state are isolated. Stop never kills the
other environment or the shared LLM. Full and Light in the same environment share data.

Preprod operation commands:
```bash
make preprod-backup
make preprod-restore TS=<timestamp>
make preprod-verify TS=<timestamp>
make preprod-drill
make preprod-readiness-check ACTOR=<id> TICKET=<id>
make preprod-audit ACTOR=<id> ACTION=<operation> TICKET=<id> RESULT=<OK|FAIL>
```

Recommended next-stage operational drill:
Use `make preprod-drill` (listed above) to execute backup + verify + readonly smoke in one flow.

## Related Documentation

- Shared-stack preprod model:
  - `docs/runbooks/preprod-shared-stack.md`
- Backup/restore:
  - `docs/runbooks/preprod-backup-restore.md`
- UAT procedure:
  - `docs/runbooks/preprod-uat-procedure.md`
- Access and audit:
  - `docs/runbooks/preprod-access-audit.md`
- Readiness automation:
  - `docs/runbooks/preprod-readiness-automation.md`
- Release checklist:
  - `docs/runbooks/preprod-release-checklist.md`
