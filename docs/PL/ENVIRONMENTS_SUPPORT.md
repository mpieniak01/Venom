# Macierz wsparcia środowisk

Data stanu: **2026-02-28**

Ten dokument jest źródłem prawdy o tym, które środowiska są obecnie realnie wspierane.

Główne punkty wejścia:
- `README.md`
- `README_PL.md`

## Aktualny status wsparcia

| Środowisko | Status | Dojrzałość | Uwagi |
|---|---|---|---|
| `dev` | Wspierane | Gotowe do codziennej pracy inżynierskiej | Główne środowisko developmentu i testów automatycznych. |
| `preprod` | Wspierane (faza rollout) | Operacyjne, stabilizowane | Działa w modelu wspólny stack + separacja danych. Używane do smoke read-only i manualnego UAT. |
| `prod` | Planowane | Jeszcze nieaktywne | Na dziś tylko etap docelowy. Nie jest jeszcze rekomendowane ani zwalidowane operacyjnie. |

## Aktywny model konfiguracji

Obecny model operacyjny:
- wspólny stos techniczny (`dev` + `preprod`)
- logiczna separacja danych dla `preprod`

Pliki konfiguracji środowisk:
- runtime `dev`: `.env.dev` (lokalny, niecommitowany)
- szablon `dev`: `.env.dev.example` (bezpieczny do Git)
- runtime `preprod`: `.env.preprod` (lokalny, niecommitowany)
- szablon `preprod`: `.env.preprod.example` (bezpieczny do Git)

Reguła wyboru:
- aktywny plik env wybiera `Makefile` przez eksport `ENV_FILE`
- w kontrakcie runtime nie używamy już gołego `.env` / `.env.example`

Kluczowe zmienne środowiskowe:
- `ENVIRONMENT_ROLE=dev|preprod`
- `DB_SCHEMA=dev|preprod`
- `CACHE_NAMESPACE=venom|preprod`
- `QUEUE_NAMESPACE=venom|preprod`
- `STORAGE_PREFIX=` (dev) lub `preprod`
- `ALLOW_DATA_MUTATION=0|1`

## Reguły preprod (stan obecny)

Dla `ENVIRONMENT_ROLE=preprod`:
- `DB_SCHEMA=preprod`
- `CACHE_NAMESPACE=preprod`
- `QUEUE_NAMESPACE=preprod`
- `STORAGE_PREFIX=preprod`
- operacje destrukcyjne są blokowane, gdy `ALLOW_DATA_MUTATION=0`

Kontrakt modułów optional (obowiązkowy):
- `API_OPTIONAL_MODULES` akceptuje wyłącznie wpisy `manifest:/.../module.json`.
- każdy manifest modułu musi zawierać `backend.data_policy`:
  - `storage_mode=core_prefixed`
  - `mutation_guard=core_environment_policy`
  - `state_files=[...]`
- mutacje modułu optional w `preprod` podlegają tej samej globalnej blokadzie (`ALLOW_DATA_MUTATION=0`).

Komenda smoke read-only:
```bash
make test-preprod-readonly-smoke
```

Model egzekwowania testów:
- Domyślna ścieżka CI/testów waliduje zachowanie `dev` (`make pr-fast` / backend lite).
- `preprod` jest walidowane tylko dedykowanym zestawem smoke read-only.
- `tests/test_preprod_readonly_smoke.py` kończy się błędem poza `ENVIRONMENT_ROLE=preprod` albo przy `ALLOW_DATA_MUTATION != 0`.

## Jak uruchamiać testy (dev vs preprod)

Testy dev (domyślnie):
```bash
make test
make pr-fast
```

Testy dev (manualny pytest):
```bash
ENV_FILE=.env.dev ENV_EXAMPLE_FILE=.env.dev.example \
ENVIRONMENT_ROLE=dev DB_SCHEMA=dev CACHE_NAMESPACE=venom QUEUE_NAMESPACE=venom STORAGE_PREFIX= ALLOW_DATA_MUTATION=1 \
pytest -q
```

Testy preprod (tylko readonly):
```bash
make test-preprod-readonly-smoke
```

Testy preprod (manualny pytest, kontrakt readonly):
```bash
ENV_FILE=.env.preprod ENV_EXAMPLE_FILE=.env.preprod.example \
ENVIRONMENT_ROLE=preprod DB_SCHEMA=preprod CACHE_NAMESPACE=preprod QUEUE_NAMESPACE=preprod STORAGE_PREFIX=preprod ALLOW_DATA_MUTATION=0 \
pytest -q tests/test_preprod_readonly_smoke.py -m smoke
```

Reguły:
- Nie uruchamiamy pełnych/destrukcyjnych pakietów testowych na `preprod`.
- Przepływ test/deploy dla `prod` nie jest jeszcze zwalidowany i obecnie nie jest rekomendowany.

Komendy uruchomienia preprod:
```bash
make ensure-preprod-env-file
make start-preprod
make api-preprod
make web-preprod
make startpre
make apipre
make webpre
```

Komendy operacyjne preprod:
```bash
make preprod-backup
make preprod-restore TS=<timestamp>
make preprod-verify TS=<timestamp>
make preprod-drill
make preprod-readiness-check ACTOR=<id> TICKET=<id>
make preprod-audit ACTOR=<id> ACTION=<operacja> TICKET=<id> RESULT=<OK|FAIL>
```

Rekomendowany kolejny etap operacyjny:
Użyj `make preprod-drill` (komenda jest na liście powyżej), aby wykonać sekwencję backup + verify + smoke readonly.

## Powiązana dokumentacja

- Model preprod na wspólnym stacku:
  - `docs/PL/runbooks/preprod-shared-stack.md`
- Backup/restore:
  - `docs/PL/runbooks/preprod-backup-restore.md`
- Procedura UAT:
  - `docs/PL/runbooks/preprod-uat-procedure.md`
- Dostępy i audyt:
  - `docs/PL/runbooks/preprod-access-audit.md`
- Automatyzacja readiness:
  - `docs/PL/runbooks/preprod-readiness-automation.md`
- Checklista release:
  - `docs/PL/runbooks/preprod-release-checklist.md`
