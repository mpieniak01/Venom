# Preprod na wspólnym stacku (separacja danych)

## Zakres
- Wspólny stack techniczny (`dev` + `preprod` na tych samych usługach).
- Twarda separacja danych przez namespace/schematy.
- Na `preprod` tylko smoke read-only i UAT manualny.

## Wymagane zmienne
- `ENVIRONMENT_ROLE=dev|preprod`
- `DB_SCHEMA=dev|preprod`
- `CACHE_NAMESPACE=venom|preprod`
- `QUEUE_NAMESPACE=venom|preprod`
- `STORAGE_PREFIX=` (dev) lub `preprod`
- `ALLOW_DATA_MUTATION=0|1`

## Guardy preprod
- Dla `ENVIRONMENT_ROLE=preprod` wymagane:
  - `DB_SCHEMA=preprod`
  - `CACHE_NAMESPACE=preprod`
  - `QUEUE_NAMESPACE=preprod`
  - `STORAGE_PREFIX=preprod`
- Operacje destrukcyjne są blokowane, gdy `ALLOW_DATA_MUTATION=0`.

## Smoke read-only
- Komenda:
```bash
make test-preprod-readonly-smoke
```

## Runbooki powiązane
- `docs/runbooks/preprod-backup-restore.md`
- `docs/runbooks/preprod-uat-procedure.md`
- `docs/runbooks/preprod-access-audit.md`
- `docs/runbooks/preprod-release-checklist.md`
