# Procedura UAT na preprod (wspólny stack)

## Cel
Testy akceptacyjne użytkownika na danych realnych bez automatycznych mutacji danych.

## Warunki wejścia
- Deploy na `preprod` zakończony sukcesem.
- `ENVIRONMENT_ROLE=preprod`
- `ALLOW_DATA_MUTATION=0`
- Smoke read-only:
```bash
make test-preprod-readonly-smoke
```

## Zakres UAT
- Krytyczne ścieżki użytkownika.
- Integracje i konfiguracje docelowe.
- Brak testów destrukcyjnych.

## Kryteria wyjścia
- 100% scenariuszy krytycznych: PASS.
- Brak otwartych blockerów.
- Raport UAT zatwierdzony przez ownera.
