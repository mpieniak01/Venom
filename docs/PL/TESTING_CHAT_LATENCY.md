# Testowanie czasu reakcji chatu

Dokument opisuje jak zmierzyć wydajność pipeline’u czatu Venoma w dwóch obszarach:

1. **Frontend (UI)** – czas od wysłania promptu do pojawienia się odpowiedzi w Cockpicie.
2. **Backend (API/SSE)** – czas trwania zadania (`task_update` → `task_finished`), skalowanie równoległe i obciążenie.

## Wymagania
- Uruchomiony backend (`make start-dev` lub `make start-prod`).
- Uruchomiony Next (`make start-dev` / `make start-prod`).
- Node 18.19+ (Playwright) i Python środowiska testowego (`pip install -r requirements.txt` + `pip install locust`).

## Playwright: latencja UI

Plik: `web-next/tests/perf/chat-latency.spec.ts`
Konfiguracja: `web-next/playwright.perf.config.ts`

```bash
npm --prefix web-next run test:perf
```

Test:
1. Otwiera Next Cockpit.
2. Wysyła prompt „benchmark latency”.
3. Oczekuje na nowy bąbelek odpowiedzi i mierzy czas.
4. Sprawdza budżet (domyślnie ≤ 15s – wartości konfigurowalne).

Artefakty (screenshoty/wideo) zapisują się do `web-next/test-results/` i są ignorowane przez git.

## Pytest: backendowy pipeline SSE

Pliki:
- `tests/perf/chat_pipeline.py` – helpery (submit_task, stream_task, pomiar).
- `tests/perf/test_chat_pipeline.py` – testy:
  - `test_chat_pipeline_smoke_latency`
  - `test_chat_pipeline_parallel_batch`

Uruchomienie:

```bash
pytest tests/perf/test_chat_pipeline.py -m performance
```

Parametry (w pliku):
- `STREAM_TIMEOUT` – maksymalny czas oczekiwania na `task_finished`.
- `PIPELINE_CONCURRENCY` – liczba równoległych zadań.
- `PIPELINE_BATCH_BUDGET_SECONDS` – budżet dla najwolniejszego zadania.

## Locust: test obciążeniowy (manualny)

Plik: `tests/perf/locustfile.py`

Uruchomienie pomocniczego skryptu:

```bash
./scripts/run-locust.sh
```

Skrypt:
- ubija poprzednie instancje nasłuchujące na porcie 8089,
- uruchamia Locusta z `LOCUST_WEB_HOST`/`LOCUST_WEB_PORT` (domyślnie `127.0.0.1:8089`),
- informuje w logu gdzie dostępny jest panel.

W panelu ustaw liczbę użytkowników, tempo narastania oraz adresy (domyślnie `http://localhost:8000`). Scenariusz `ChatUser` symuluje żądani → SSE.

## Archiwizacja wyników

```
./scripts/archive-perf-results.sh
```

Tworzy `perf-artifacts/<timestamp>/` i kopiuje:
- `test-results/`, `web-next/test-results/`,
- `playwright-report/`,
- logi Locusta (`locust.stats.csv`, `locust.failure.csv` jeśli istnieją).

## Uwagi
- Repozytorium jest lokalnym eksperymentem – artefakty testów NIE są szyfrowane, ale są ignorowane (`.gitignore`) i przechowywane lokalnie.
- Wydajnościowe testy nie są jeszcze podpięte pod CI – wykonujemy je ręcznie przed wydaniem.

## Referencyjne wyniki (ostatni przebieg)
| Data (UTC) | Test | Wynik |
| --- | --- | --- |
| 2026-01-05 | `tests/perf/chat-latency.spec.ts` (Next Cockpit) | PASS, 4.0s |
