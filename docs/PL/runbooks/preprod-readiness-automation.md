# Automatyzacja readiness preprod

## Cel
Uruchamiać powtarzalną weryfikację gotowości release dla `preprod` jedną komendą z artefaktem raportu JSON.

## Komenda
```bash
make preprod-readiness-check ACTOR=<id> TICKET=<id>
```

## Co jest sprawdzane
1. Guard config w `.env.preprod`:
- `ENVIRONMENT_ROLE=preprod`
- `DB_SCHEMA=preprod`
- `CACHE_NAMESPACE=preprod`
- `QUEUE_NAMESPACE=preprod`
- `STORAGE_PREFIX=preprod`
- `ALLOW_DATA_MUTATION=0`
2. Utworzenie backupu (`make preprod-backup`) i odczyt timestampu.
3. Weryfikacja backupu + smoke readonly (`make preprod-verify TS=<timestamp>`).
4. Wpis audytowy (`make preprod-audit ...`) z wynikiem `OK|FAIL`.

## Raport wyjściowy
- Ścieżka: `logs/preprod_readiness_<UTC>.json`
- Zawiera:
  - status globalny (`pass|fail`)
  - timestamp backupu
  - szczegóły per check + fragmenty outputu komend

## Przydatne opcje
Tryb dry-run (tylko walidacja konfiguracji, bez backup/verify):
```bash
make preprod-readiness-check DRY_RUN=1 RUN_AUDIT=0
```

Wyłączenie wpisu audytowego (niezalecane operacyjnie):
```bash
make preprod-readiness-check RUN_AUDIT=0
```

## Kryteria akceptacji
1. Komenda kończy się kodem `0`.
2. Status raportu JSON to `pass`.
3. Raport zawiera timestamp backupu.
4. Check `preprod-verify` w raporcie ma status `pass`.
