## Zasady pracy z kodem — Venom v2

1. Komunikacja:
   - Kod i komentarze po polsku (chyba że to specyficzny kod zewnętrzny).
   - Komentarze tylko jeśli logika jest złożona — nie nadpisujemy „komentarzami-śmieciami”.

2. Format / styl / lint / pre-commit:
   - Używamy pre-commit + Black + Ruff + isort / inne, aby kod wyglądał spójnie.
   - Nie ładujemy ciężkich zależności ani modeli w hookach. Hooki mają być szybkie.

3. Testy:
   - Testy jednostkowe / logiczne: `pytest`, możliwie z mockami gdzie sens — szybkie i deterministyczne. Nie zależne od GPU / modeli.
   - Testy integracyjne, inference, ML — tylko na żądanie / przy odpowiedniej konfiguracji (GPU, onnx). W CI / workflow osobna ścieżka.

4. Konfiguracja / dane wrażliwe:
   - `.env` nie do repo. Konfiguracja — `config.py` + `Settings`, z domyślnymi wartościami i fallbackami.
   - Sekrety, klucze, ścieżki do modeli — przez env lub konfigurację, nigdy twardo wpisane.

5. Praca z agentami / Copilot:
   - Jeśli używasz Copilot / AI do generacji kodu — traktuj wygenerowany kod jak patch:
       - ręcznie przeglądnij, popraw styl, przetestuj logicznie, dodaj testy.
       - nie commituj „na ślepo” — review nadal obowiązkowe.
   - Używaj mocków / stubów przy testach generowanego kodu, jeśli integracje zewnętrzne / modelem są ciężkie.

6. Dokumentacja zadań i planowanie:
   - Każde zadanie opisywane w `docs/_to_do`, z numerem, celem, DoD, notatkami.
   - Po wykonaniu → przeniesione do `docs/_done`.

7. Workflow git / PR / commit:
   - Commit message: `type(scope): krótki opis` (`feat`, `fix`, `docs`, `test`, …).
   - Przed commitem: `pre-commit run`.
   - PR musi mieć opis zmiany, uzasadnienie, kroki testów / regresji (jeśli dotyczy).
   - Po mergu: usuń branch, zaktualizuj `CHANGELOG.md` (jeśli wprowadzony).

8. CI / automatyzacja:
   - CI pipeline (np. w `.github/workflows`) uruchamia lint + testy lekkie. Cięższe joby (GPU, onnx) opcjonalne — osobne joby lub marker „heavy”.
