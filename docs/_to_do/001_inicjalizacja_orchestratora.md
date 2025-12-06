# 001 – Inicjalizacja modułu Orchestrator

## Cel
Utworzenie minimalnej wersji `core/orchestrator.py`, która:
- przyjmuje zadanie,
- zapisuje je w stanie,
- zwraca prostą odpowiedź kontrolną,
- przygotuje fundament pod dalsze organy Venoma.

## Zakres prac
1. Utworzyć klasę `Orchestrator`.
2. Dodać metodę `submit_task(text: str) -> dict`.
3. Powiązać orchestrator z FastAPI w `main.py`.
4. Napisać test w `tests/`:
   - sprawdzający, czy orchestrator akceptuje zadanie,
   - oraz zwraca poprawną strukturę JSON.

## Kryteria akceptacji (Definition of Done)
- Moduł działa i ładuje się przy starcie aplikacji.
- Testy przechodzą (`pytest` → 100% zielono).
- Kod zgodny z `ruff`.

## Notatki
To zadanie przygotowuje grunt pod:
- Intent Manager (`002_intent_manager`),
- Policy Engine (`003_policy_engine`),
- Architektura pipeline’ów zadań.
