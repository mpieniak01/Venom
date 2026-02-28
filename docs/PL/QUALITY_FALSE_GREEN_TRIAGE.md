# Polityka triage false-green (pokrycie new-code)

## Cel
Ograniczyć sytuacje "zielono, ale ryzykownie", gdy bramki przechodzą mimo realnego ryzyka regresji.

## Zakres
Polityka dotyczy backendowych PR uruchamianych przez:
- `make pr-fast`
- `make check-new-code-coverage`
- bramkę Sonar new-code

## Główne sygnały false-green
1. Bramka coverage raportuje `No coverable changed lines found (after exclusions).`
2. Istotne zmiany konfiguracji/runtime przy minimalnym lub zerowym przyroście testów.
3. Nowe testy pokrywają wyłącznie happy-path bez ścieżek edge/error.
4. Dryf grup testowych: przeniesienia między `ci-lite` i `sonar-new-code` bez uzasadnienia.

## Przepływ triage
1. Zbierz kontekst bramki:
   - `NEW_CODE_DIFF_BASE`
   - lista zmienionych plików
   - lista testów wybranych przez bramkę coverage
2. Sklasyfikuj anomalię:
   - `DIFF_SCOPE_MISMATCH`: zmienione pliki nie wpadają do pokrywalnego zakresu Python.
   - `TEST_SELECTION_GAP`: brak istotnych testów w wybranym secie.
   - `BRANCH_GAP`: jest line coverage, ale brakuje gałęzi/error path.
3. Zastosuj mitigację:
   - dopisz lekkie testy dla brakujących gałęzi/error paths,
   - dodaj/popraw przypisanie lane (`config/testing/lane_assignments.yaml`),
   - zaktualizuj `config/pytest-groups/sonar-new-code.txt`, jeśli luka jest systemowa.
4. Uruchom ponownie:
   - `make check-new-code-coverage`
   - `make pr-fast`
5. Zapisz wynik triage w opisie PR, jeśli anomalia wystąpiła.

## Obowiązkowe triggery eskalacji
Eskalacja przed merge jest wymagana, gdy:
1. Powtarza się `No coverable changed lines found` dla backendowego PR ze zmianą kodu.
2. Zmieniono krytyczne moduły (`venom_core/core`, `venom_core/api/routes`, `venom_core/execution`) bez istotnego przyrostu testów.
3. Wykryto naruszenie kontraktów lane przez `make test-lane-contracts-check`.

## Odpowiedzialność
- Właściciel główny: backend platform/quality reviewers.
- Autor PR odpowiada za triage anomalii, gdy wystąpi trigger.
