# Preprod Readiness Automation

## Goal
Run a repeatable release-readiness check for `preprod` with one command and a JSON report artifact.

## Command
```bash
make preprod-readiness-check ACTOR=<id> TICKET=<id>
```

## What it validates
1. Preprod guard config in `.env.preprod`:
- `ENVIRONMENT_ROLE=preprod`
- `DB_SCHEMA=preprod`
- `CACHE_NAMESPACE=preprod`
- `QUEUE_NAMESPACE=preprod`
- `STORAGE_PREFIX=preprod`
- `ALLOW_DATA_MUTATION=0`
2. Backup creation (`make preprod-backup`) and timestamp extraction.
3. Backup verification + readonly smoke (`make preprod-verify TS=<timestamp>`).
4. Audit entry (`make preprod-audit ...`) with result `OK|FAIL`.

## Output report
- Path: `logs/preprod_readiness_<UTC>.json`
- Includes:
  - global status (`pass|fail`)
  - backup timestamp
  - per-check details and command output snippets

## Useful options
Dry run (config checks only, no backup/verify):
```bash
make preprod-readiness-check DRY_RUN=1 RUN_AUDIT=0
```

Disable audit entry (not recommended in production operation):
```bash
make preprod-readiness-check RUN_AUDIT=0
```

## Acceptance criteria
1. Command exits with code `0`.
2. JSON report status is `pass`.
3. Backup timestamp is present.
4. `preprod-verify` check in report has status `pass`.
