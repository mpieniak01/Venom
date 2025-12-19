# 064: Feedback użytkownika (kciuk góra/dół + opis)

## Cel
Dodać mechanizm feedbacku użytkownika po wykonaniu zadania:
- kciuk w górę (sukces)
- kciuk w dół (problem) + krótki opis

## Założenia
- Feedback nie może ujawniać danych poufnych w repo.
- Dane mogą być zapisywane lokalnie (np. `data/feedback/`).
- Feedback powiązany z `task_id` i intencją.

## Zakres
1. **Backend API**
   - Endpoint: `POST /api/v1/feedback`
   - Payload: `task_id`, `rating` (up/down), `comment` (opcjonalny)

2. **Persistencja lokalna**
   - Zapisy do `data/feedback/feedback.jsonl` (poza gitem)

3. **UI**
   - Widoczne przy zakończonym zadaniu
   - Dla „down” wymuszony krótki opis

## Kryteria akceptacji
- Feedback zapisuje się lokalnie i nie trafia do gita.
- Widoczne w UI po zakończeniu zadania.
- Umożliwia szybki opis błędu przez użytkownika.

## Uwagi przeniesione z 063
- Znany brak: pogoda wymaga LLM/połączenia (fallback do narzędzia niezaimplementowany).
