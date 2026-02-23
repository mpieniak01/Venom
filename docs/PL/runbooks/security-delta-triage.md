# Triage Delta Security (operacyjnie)

Ten runbook definiuje kto, kiedy i jak klasyfikuje deltę podatności zależności z:
- `make security-delta-scan`
- workflow nightly: `.github/workflows/security-delta-nightly.yml`

## 1. Odpowiedzialność

1. Właściciel główny: maintainerzy repo odpowiedzialni za aktualizacje zależności.
2. Właściciel zapasowy: inżynier on-duty utrzymania release.

## 2. Częstotliwość triage

1. Skan nightly: codziennie (artefakt `security-delta-latest.json`).
2. Skan ręczny: przed wydaniem i po większych bumpach zależności.
3. Tryb incydentowy: natychmiast po publikacji CVE dotykającego runtime.

## 3. Reguły klasyfikacji

1. `critical` lub `high` w zależnościach produkcyjnych:
   - klasyfikacja `P1`,
   - natychmiastowy scoped PR security.
2. `moderate` w zależnościach produkcyjnych:
   - klasyfikacja `P2`,
   - naprawa w najbliższym oknie maintenance.
3. `low`/`info`:
   - klasyfikacja `P3`,
   - monitoring i naprawa opportunistic.
4. Znaleziska wyłącznie dev/tooling:
   - klasyfikować osobno od ryzyka runtime,
   - naprawiać bez destabilizacji CI.

## 4. SLA (docelowe)

1. `P1` (`critical/high`, prod): triage do 24h, fix/mitigacja do 72h.
2. `P2` (`moderate`, prod): triage do 3 dni roboczych, fix do 14 dni.
3. `P3` (`low/info` lub dev-only): triage do 14 dni, fix w regularnym cyklu bumpów.

## 5. Przepływ decyzji

1. Odtwórz wynik lokalnie:
```bash
make security-delta-scan
```
2. Potwierdź zakres (prod vs dev-only, transitive vs direct).
3. Zweryfikuj kandydata fixa (dry-run resolver, jeśli potrzebny).
4. Wprowadź minimalny scoped bump.
5. Uruchom ponownie:
   - `make security-delta-scan`
   - obowiązkowe gate'y release przed merge/push.

## 6. Szablon raportu (aktualizacja backlogu 170)

1. Data/godzina skanu.
2. Podsumowanie delty (`python`, `web`, rozkład severity).
3. Klasyfikacja (`zamkniete / do realizacji / do monitoringu`).
4. Klasa SLA (`P1/P2/P3`) i właściciel.
5. Link do PR lub notatka o mitigacji.
