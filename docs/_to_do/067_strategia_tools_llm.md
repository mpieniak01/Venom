# 067: Strategia Tool vs LLM + proces nauki potrzeb użytkownika

## Cel
Ten PR przygotowuje grunt pod strategię opartą o feedback użytkownika (PR 064).
Docelowa pętla jakości odpowiedzi (LLM → ocena → doprecyzowanie → ocena)
powinna być opisana i wdrożona przede wszystkim w PR 064.
W PR 067 skupiamy się na warstwie routingu i na sygnałach do nauki.

## Status
Zakończone.

## Wykonane
- Dodano regułę tool-required vs LLM-only oraz krok `DecisionGate.tool_requirement`.
- Wprowadzono metryki routingu (LLM-only, tool-required, learning logged).
- Dodano zapis procesu nauki dla LLM-only do `data/learning/requests.jsonl`.
- Dodano endpoint `GET /api/v1/learning/logs` do podglądu logów nauki.
- Zmieniono fallback intencji na `GENERAL_CHAT` (LLM zamiast `UNSUPPORTED_TASK`).
- Dodano fallback na `UNSUPPORTED_TASK` gdy wymagany tool nie ma agenta.
- Dodano panel „Logi nauki” w Cockpicie (UI).
- Zaktualizowano `TOOL_REQUIRED_INTENTS` o intencje systemowe.
- Zaktualizowano dokumentację w `docs/REQUEST_TRACING_GUIDE.md`.
- Dodano minimalny audyt logów nauki (filtrowanie po intent/success/tag).
- Spięto pętlę feedbacku z PR 064 (oceny i dodatkowe rundy promptów).
- Dodano widok listy feedbacków i metryki jakości.
- Dodano zalążek hidden prompts (logowanie kciuka w górę).
- Dodano endpoint i UI podglądu hidden prompts + agregację (deduplikacja, score).
- Wpięto hidden prompts do budowania kontekstu LLM-only.
- Dodano filtrowanie hidden prompts w UI oraz aktywację/wyłączenie.
- Dodano deduplikację na etapie zapisu (hash promptu).
- Dodano trwałe przechowywanie aktywnych hidden prompts oraz API sterowania.
- Aktywne hidden prompts mają priorytet w budowaniu kontekstu.
- Dodano audit trail aktywacji (kto, kiedy).
- Dodano dropdown aktywnego hidden promptu per intencja.
- Dodano testy hidden prompts (aggregacja, aktywne priorytety).

## Do zrobienia
- Brak

## Analiza obecnego stanu
- Istnieją narzędzia (skills) i `UnsupportedAgent` dla braków w toolingu.
- Brakuje spójnej, jawnej reguły „tool required” vs „LLM only”.
- Nie ma stałego procesu zapisu „potrzeby użytkownika” po odpowiedzi LLM.
- Feedback użytkownika (PR 064) jest wpięty w pętlę jakości odpowiedzi LLM.

## Zakres zmian (przygotowanie pod PR 064)
1. **Routing i decyzje**
   - Jednoznaczny warunek: gdy nie potrzeba toola → LLM.
   - Gdy potrzeba toola i brak dopasowania → `UnsupportedAgent`.
   - Utrzymać logi decyzji w tracerze (czytelne kroki).

2. **Rejestr narzędzi i mapowanie potrzeb**
   - Spójne mapowanie intencja → tool (lub brak).
   - Metadane: czy intencja wymaga danych „tu i teraz”.

3. **Proces nauki po LLM**
   - Po odpowiedzi LLM zapisujemy:
     - potrzebę użytkownika (what),
     - kontekst i wynik (so what),
     - sugerowany skrót na przyszłość (how to faster).
   - Persistencja lokalna (np. `data/learning/requests.jsonl`, poza gitem).

4. **Obserwowalność**
   - Metryki i logi: liczba requestów LLM, liczba `UnsupportedAgent`,
     top brakujących tooli, top intencji bez toola.

5. **Dokumentacja**
   - Dodać sekcję „Reguła tool vs LLM” i „Proces nauki” w docs.

6. **Integracja z feedbackiem (PR 064)**
   - Opis i API feedbacku są domeną PR 064.
   - W PR 067 tylko sygnalizujemy potrzebę spięcia z pętlą feedbacku.

## Kryteria akceptacji
- Każdy request jest jednoznacznie sklasyfikowany: tool-required albo LLM.
- Jeśli tool-required bez narzędzia → `UnsupportedAgent` + logi.
- Jeśli LLM-only → odpowiedź LLM + zapis do procesu nauki.
- W logach/tracerze widać decyzję i ścieżkę.
- Dane nauki są lokalne i nie trafiają do repo.
- Pętla feedbacku jest opisana i wdrażana w PR 064.

## Proponowane pliki do zmiany
- `venom_core/core/intent_manager.py` (decyzja: tool required vs LLM)
- `venom_core/core/orchestrator.py` (routing + hook nauki po LLM)
- `venom_core/core/tracer.py` (spójne kroki i statusy decyzji)
- `venom_core/core/metrics.py` (metryki: tool vs LLM, brak tooli)
- `docs/REQUEST_TRACING_GUIDE.md` (opis strategii)
- `docs/_to_do/064_feedback_uzytkownika.md` (spięcie z procesem nauki)

## Ryzyka
- Fałszywa klasyfikacja „tool required” może blokować proste pytania.
- Zbyt agresywna nauka może generować szum w danych.

## Notatki
- Proces nauki może być prostym zapisem JSONL na start; później można
  podłączyć analizę i priorytetyzację tooli.
- Feedback w dół nie oznacza błędu systemu, tylko brak dopasowania lub brak
  kontekstu — traktujemy go jako dane do kolejnej rundy doprecyzowania (PR 064).
