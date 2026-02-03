# 064: Feedback użytkownika (kciuk góra/dół + opis)

## Cel
Dodać mechanizm feedbacku użytkownika po wykonaniu zadania:
- kciuk w górę (sukces)
- kciuk w dół (problem) + krótki opis

Docelowo feedback steruje pętlą jakości odpowiedzi LLM:
- odpowiedź LLM → ocena użytkownika,
- kciuk w dół uruchamia rundę promptów pozycjonujących,
- kciuk w górę kończy iterację i zapisuje „sprawdzoną odpowiedź”
  jako sygnał do przewidywania w przyszłości (hidden prompts / skróty).

## Założenia
- Feedback nie może ujawniać danych poufnych w repo.
- Dane mogą być zapisywane lokalnie (np. `data/feedback/`).
- Feedback powiązany z `task_id` i intencją.

## Zakres
1. **Backend API**
   - Endpoint: `POST /api/v1/feedback`
   - Payload: `task_id`, `rating` (up/down), `comment` (opcjonalny)
   - Obsługa rundy doprecyzowania po ocenie „down”
   - Finalizacja po ocenie „up”

2. **Persistencja lokalna**
   - Zapisy do `data/feedback/feedback.jsonl` (poza gitem)

3. **UI**
   - Widoczne przy zakończonym zadaniu
   - Dla „down” wymuszony krótki opis
   - Dla „down” uruchomienie dodatkowej rundy promptów pozycjonujących
   - Dla „up” jasne potwierdzenie zakończenia iteracji

## Kryteria akceptacji
- Feedback zapisuje się lokalnie i nie trafia do gita.
- Widoczne w UI po zakończeniu zadania.
- Umożliwia szybki opis błędu przez użytkownika.
- Pętla feedbacku działa: ocena w dół → doprecyzowanie; ocena w górę → zakończenie.

## Status
Zakończone.

## Wykonane
- Dodano endpoint `POST /api/v1/feedback` z zapisem do `data/feedback/feedback.jsonl`.
- Ocena „down” uruchamia rundę doprecyzowania i zwraca nowe `task_id`.
- Dodano UI feedbacku w panelu „Szczegóły requestu”.
- Dodano endpoint `GET /api/v1/feedback/logs` i panel listy feedbacku w Cockpicie.
- Dodano metryki jakości (liczniki 👍/👎) w `/api/v1/metrics`.
- Kciuk w górę zapisuje parę do `data/learning/hidden_prompts.jsonl` (zalążek hidden prompts).
- Dodano testy feedbacku i logów (pytest).

## Do zrobienia
- Brak

## Uwagi przeniesione z 063
- Znany brak: pogoda wymaga LLM/połączenia (fallback do narzędzia niezaimplementowany).
