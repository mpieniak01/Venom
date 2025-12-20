# 071: Model 2-etapowy QA (Internal QA → User QA)

## Cel
Wprowadzić dwustopniową ocenę odpowiedzi:
- **Internal QA** decyduje, czy odpowiedź w ogóle pokazać.
- **User QA** ocenia wartość odpowiedzi po jej wyświetleniu.

## Etap A: Internal QA (przed wyświetleniem)
**Wyjście:** `quality_gate` z jedną decyzją:
- ✅ PASS → pokaż odpowiedź normalnie
- ⚠️ WARN → pokaż, ale z badge “niepewne” + przycisk “sprawdź / dlaczego?”
- ❌ BLOCK → nie pokazuj odpowiedzi; pokaż komunikat + opcje retry

**Założenie:** brak wcześniejszego kontekstu (zero interakcji), więc ocena musi być samowystarczalna.

### Minimalne kryteria (MVP)
1. **Spójność logiczna**
   brak sprzeczności w 2–3 zdaniach, brak dygresji nie na temat.
2. **Relevance (zgodność z pytaniem)**
   odpowiedź trafia dokładnie w pytanie, nie w temat poboczny.
3. **Kompletność minimalna**
   użytkownik “może działać dalej” po lekturze (np. definicja + 1 przykład dla prostych pytań).
4. **Sygnały halucynacji**
   unika kategorycznych twierdzeń bez podstaw, brak “dziwnych detali” nie wynikających z pytania.
5. **Styl zgodny z profilem**
   krótko i prosto (core chat), bez lania wody.

**Skoring:** 0–100 i mapowanie na PASS/WARN/BLOCK.

## Etap B: User QA (po wyświetleniu)
Pozostaje obecny mechanizm:
- 👍 / 👎
- opcjonalny komentarz
- zapis dopiero po ocenie lub z domyślną blokadą przy 👎

**Klucz:** rozdzielić „czy pokazać” od „czy zapisać”.

### Knowledge Save – zasady
Zapis tylko jeśli:
- user da 👍 (albo ręcznie wymusi),
- i Internal QA nie dało BLOCK.

## UI (minimalny)
W boksie odpowiedzi:
- ✅ **Zweryfikowane** (PASS)
- ⚠️ **Niepewne** (WARN) + link “dlaczego?”
- ⛔ **Wstrzymane** (BLOCK) + przyciski: Retry / Doprecyzuj / Zmień model

## Retry – reguły automatyczne
- WARN przez niską spójność → retry innym modelem lub krótszą odpowiedzią.
- BLOCK przez brak relewancji → poproś użytkownika o doprecyzowanie.
- FAIL techniczny (np. brak runtime) → retry po naprawie/zmianie ścieżki.

## Status
- [ ] Internal QA + quality_gate (PASS/WARN/BLOCK)
- [ ] UI badge + minimalne CTA
- [ ] Mapowanie skoringu do decyzji
- [ ] Integracja z zapisem wiedzy (blokada przy BLOCK)

## Uwagi
- User QA jest już realizowane we wcześniejszym PR – tutaj chodzi o spójność całego flow.
