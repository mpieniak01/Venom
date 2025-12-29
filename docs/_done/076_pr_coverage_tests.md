# 076: PR coverage + testy o wysokim ROI
Status: zrobione

## Cel
Podniesc jakosc coverage przez odciecie szumu oraz szybkie testy jednostkowe
o wysokim zwrocie (bez E2E).

## Zakres
1) Odetnij “szum” od coverage (to daje natychmiastowy wzrost jakosci raportu)
   - Do `.coveragerc` lub `pyproject.toml` dodaj wykluczenia dla:
     - `__init__.py` (puste eksporty)
     - plikow startowych (`main.py`) jesli to tylko glue
     - kodu “manual CLI / debug” (jesli istnieje)
   - Przykladowa logika (bez wklejania na sile):
     - `exclude: if __name__ == "__main__":`
     - `pragma: no cover`
     - logging‑only / debug branches
   - Efekt: coverage mierzy to, co ma sens, a nie boilerplate.

2) Uderz w 5 plikow o najwiekszym wplywie (bez E2E)
   - Priorytety:
     - `venom_core/services/runtime_controller.py`
     - `venom_core/api/routes/system.py`
     - `venom_core/main.py`
     - `venom_core/api/audio_stream.py`
     - `venom_core/agents/executive.py`
   - Testuj:
     - czyste funkcje / adaptery / decyzje
     - reszte mockuj

3) Dwie klasy testow, ktore podbijaja coverage “tanio”
   - testy sciezek decyzyjnych (routing, wybor modelu, permission guard, intent manager)
   - testy walidacji/kontraktow (schema validators, request parsing, error mapping)

## Kryteria akceptacji
- Coverage raportuje realnie istotne fragmenty (bez boilerplate).
- Jest widoczny wzrost coverage w kluczowych modulach.
- Testy sa jednostkowe/mokowane (brak E2E).

## Kryteria wyjscia
- `.coveragerc` lub `pyproject.toml` zawiera nowe reguly exclude i sa one udokumentowane w raporcie.
- Dodane sa testy dla wskazanych obszarow (lub jasno opisane ograniczenia).
- Raport coverage pokazuje poprawa w wytypowanych plikach.

## Format raportu (PR 076)
Plik raportu: `docs/_done/076_pr_coverage_tests_report.md`
- `Cel i zakres`
- `Zmiany w coverage` (co wykluczono, z uzasadnieniem)
- `Nowe testy` (lista plikow + co testuja)
- `Wplyw na coverage` (przed/po lub opisowo, bez E2E)
- `Ryzyka i ograniczenia` (co pominięto i dlaczego)
