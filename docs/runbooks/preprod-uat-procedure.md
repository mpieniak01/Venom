# Pre-prod UAT Procedure (Shared Stack)

## Cel
Prowadzić testy akceptacyjne użytkownika na danych realnych bez mutacji automatycznej.

## Warunki wejścia
- Deploy na `preprod` zakończony sukcesem.
- `ENVIRONMENT_ROLE=preprod`
- `ALLOW_DATA_MUTATION=0`
- Smoke read-only:
```bash
make test-preprod-readonly-smoke
```

## Zakres UAT
- Kluczowe ścieżki użytkownika z produktu.
- Weryfikacja konfiguracji i integracji produkcyjnych.
- Brak testów destrukcyjnych i masowych resetów danych.

## Przebieg
1. Przygotowanie danych i kont testowych użytkowników biznesowych.
2. Wykonanie scenariuszy UAT (happy path + krytyczne edge cases).
3. Rejestracja wyników:
- PASS
- FAIL
- BLOCKED
4. Zgłoszenia defektów z priorytetem i ownerem.
5. Retest po poprawkach.

## Kryteria wyjścia
- 100% scenariuszy krytycznych: PASS.
- Brak otwartych defektów blokujących release.
- Raport UAT zatwierdzony przez właściciela produktu.

## Wzór raportu UAT
- Wersja builda:
- Data i okno testowe:
- Lista scenariuszy + wynik:
- Defekty (ID, priorytet, status):
- Decyzja: GO / NO-GO
- Akceptujący:
