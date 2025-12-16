# ZADANIE 057 (DONE): Testy czasu reakcji i wydajności chatu

## Cel
Stworzyć zestaw testów E2E/integracyjnych, które mierzą czas reakcji pipeline’u chatowego:
- porównanie nowego Cockpitu (Next) ze starym panelem (FastAPI/Jinja),
- pomiary backendowego SSE (task_update → task_finished),
- obciążenie heurystyczne (Locust) – ręcznie sterowane.

## Artefakty
1. **Playwright (Next vs Legacy)**
   - Konfiguracja `web-next/playwright.perf.config.ts`.
   - Scenariusz `web-next/tests/perf/chat-latency.spec.ts`:
     - otwiera Next Cockpit oraz stary panel (osobne przeglądarki),
     - wysyła prompt i czeka na nowe bąbelki odpowiedzi,
     - mierzy czas i asercje (`toBeLessThanOrEqual` dla budżetów),
     - zapisuje logi/screenshoty do `web-next/test-results/` (ignorowane w git).
   - Komenda: `npm --prefix web-next run test:perf`.

2. **Pytest (pipeline FastAPI)**
   - Moduł pomocniczy `tests/perf/chat_pipeline.py` (submit_task, stream_task, pomiary).
   - Testy `tests/perf/test_chat_pipeline.py`:
     - `test_chat_pipeline_smoke_latency` – mierzy czas pojedynczego zadania (timeout 25s).
     - `test_chat_pipeline_parallel_batch` – batch równoległy (domyślnie 3 zadania, budżet 6s).
   - Znacznik `@pytest.mark.performance` + aktualizacja `pytest.ini`.

3. **Locust (opcjonalne obciążenie)**
   - Skrypt `tests/perf/locustfile.py` symuluje użytkownika chatu (HTTP + SSE).
   - Uruchomienie przez `./scripts/run-locust.sh` (ustawia port/host, pilnuje aby panel działał mimo przerwania).
   - Panel dostępny na `http://127.0.0.1:8089`.

4. **Archiwizacja wyników**
   - `scripts/archive-perf-results.sh` kopiuje katalogi `test-results/`, `playwright-report/` i logi do `perf-artifacts/<timestamp>/`, aby łatwo dzielić się wynikami bez bałaganu w repo.

## Integracja z dokumentacją
- README – sekcja „Czas reakcji i wydajności chatu” zawiera wszystkie komendy (`npm --prefix web-next run test:perf`, `pytest ...`, `locust ...`).
- `docs/DEPLOYMENT_NEXT.md` – wskazuje kiedy uruchamiać testy (po `make start-prod`).
- Dane i wyniki są otwarte – Venom to lokalna instancja, dlatego artefakty nie są szyfrowane, lecz ignorowane w git przez wzorce `**/test-results/`, `perf-artifacts/`, itp.

## Status
✅ Testy gotowe do lokalnego uruchamiania (bez CI). Wyniki przechowujemy w katalogach ignorowanych przez git, aby uniknąć przypadkowego commitowania screenshotów czy logów z sekretami.
