# ZADANIE 057: Monitoring backendu LLM (Ollama vs vLLM)

## Kontekst
- Venom działa jednocześnie z dwoma serwerami LLM: Ollama (`phi3:mini`) i vLLM (`models/gemma-3-4b-it`).
- Panel `/api/v1/models` pokazuje listę lokalnych modeli, ale brak informacji w UI/logach, który serwer i konkretny model obsłużył dany request.
- Przy błędach (np. 404 z vLLM) trudno ustalić, czy zapytanie w ogóle trafiło do właściwego endpointu.

## Problem
- Requesty do LLM przechodzą przez Semantic Kernel i `KernelBuilder`, ale nie są tagowane nazwą serwisu (`OpenAIChatCompletion.service_id`), więc telemetria / logi panelu nie wiedzą, czy odpowiedział Ollama, vLLM czy fallback cloud.
- Panel w sekcji „Modele” pokazuje tylko lokalną listę katalogów. Brak informacji o aktywnym modelu i serwerze obsługującym zadania.

## Wymagania
1. **Logowanie źródła LLM** – każda odpowiedź powinna zawierać `llm_provider` (np. `ollama`, `vllm`, `openai`) i `model_name` (np. `phi3:mini`, `models/gemma-3-4b-it`).
   - Informacje dołączamy do `TaskResponse` (payload SSE) oraz `RequestTracer`.
   - Dane muszą być dostępne w `/api/v1/history/requests` i w logach backendu.
2. **Telemetria panelu** – w sekcji „Modele” dodać boks z aktualnie używanym modelem (np. „Aktywny: Gemma 3 (vLLM @ 8001)”).
   - Jeśli routing wybiera inny model (np. fallback cloud), UI powinno pokazywać zmianę.
3. **Alerty** – jeśli LLM zwróci 404/500, dashboard powinien wyświetlić ostrzeżenie z nazwą modelu i endpointu, który zawiódł.
   - Ułatwi to debugowanie w scenariuszach jak 57f1d421-019f-4453-becd-5a141e221e73.

## Zadania
1. **Instrumentacja backendu**
   - W `KernelBuilder`/`IntentManager` przechwyć service_id i dodaj do kontekstu zadania (`state_manager.add_log`, `TaskResponse`).
   - Rozszerz `TaskResponse` (oraz SSE) o pole `llm_provider`, `llm_model`.
2. **API / ModelManager**
   - `/api/v1/models` powinno oznaczać model „aktywny” (na podstawie `LLM_MODEL_NAME`) i mapować `models/…` ↔ friendly name.
3. **UI (web-next)**
   - Sekcja „Modele” pokazuje aktywny model, serwis (`OLLAMA`, `vLLM`) i status (OK / błąd).
   - Dodać banner ostrzegawczy, gdy backend sygnalizuje `llm_provider_error`.
4. **Testy**
   - Jednostkowe: nowy field w `TaskResponse`, trace, `/api/v1/models`.
   - E2E: symulacja błędu LLM (np. wyłączenie vLLM) i weryfikacja komunikatu na UI.
5. **Serwery LLM (nowy box)**
   - API `/api/v1/system/llm-servers` udostępnia listę runtime (co najmniej vLLM i Ollama) + akcje `start/stop/restart`.
   - UI w sekcji głównej dodaje panel „Serwery LLM” powyżej „Modele” (nad Live Feed, obok „Cockpit AI”) oraz przenosi istniejący box „Modele” w tę samą sekcję.
   - Panel wyświetla status (online/offline), endpoint i aktywne komendy (przyciski Start/Stop/Restart tylko gdy `supports[action]=true`).
   - `llm_status` musi pochodzić z realnego health-checku (np. `GET /v1/models` dla vLLM, `GET /api/tags` dla Ollamy), a nie z wartości „unknown”. Brak statusu powinien skutkować próbą pingowania endpointu i zwróceniem `online/offline` wraz z komunikatem błędu.
6. **Diagnoza Legacy UI**
   - Playwright `chat-latency – Legacy Cockpit` traktować jako optional (skip kiedy brak odpowiedzi <20s).
  - Legacy UI korzysta z SSE, ale widok nie pokazuje nowych wiadomości – przeanalizować `web/static/js/app.js`, `templates/index.html` i strumień.
  - Dokumentacja (plik 57) powinna zawierać aktualny status diagnostyki oraz odnośnik do logów testu.
7. **Modele per serwer LLM**
   - `/api/v1/models` musi rozróżniać modele przypisane do vLLM (lokalne katalogi HF) i Ollama (API 11434) – odpowiedź powinna zawierać strukturę grupującą po `provider`.
   - Panel „Modele” w kokpicie pokazuje dwie kolumny/listy: modele vLLM oraz modele Ollama, wraz z informacją, który serwer je obsługuje i jakie akcje są dostępne (np. aktywacja, instalacja).
   - Instalacja/usuwanie modeli powinno jasno wskazywać, którego runtime dotyczy (np. formularz instalacji domyślnie dla Ollama, a dla vLLM link do instrukcji/Makefile); dokumentacja w panelu powinna to sygnalizować.

## Status wdrożenia
- Instrumentacja backendu i `StateManagera` gotowa – `TaskResponse`, SSE `/tasks/{id}/stream` i `RequestTracer` dostarczają `llm_provider/model/endpoint`, a `state_manager.context_history["llm_runtime"]` trzyma metadane runtime.
- `ModelManager` skanuje `./models`, rozpoznaje aktywny katalog i `/api/v1/models` zwraca blok `active` z opisem runtime (provider, endpoint, friendly label).
- Backend dodał `ServiceRegistry` dla serwerów LLM oraz `LlmServerController`, który odpala komendy powłoki (konfigurowane przez zmienne `.env`: `VLLM_START_COMMAND`, `OLLAMA_*`, itd.). Endpointy `/api/v1/system/llm-servers` i `POST /{name}/{action}` działają i mają testy (`tests/test_llm_server_controller.py`).
- Frontend: nowe hooki `useLlmServers`, `controlLlmServer`, obsługa `llmActionPending`, alertów SSE oraz panel „Serwery LLM” + przeniesiony box „Modele” nad sekcję Live Feed (layout w `cockpit-home.tsx`); usunięto stary panel „Modele” z dolnej sekcji, pozostawiając tam jedynie „Zasoby”, by uniknąć duplikacji informacji. Panel korzysta już z komend w `.env`, więc pokazuje listę runtime zamiast „Brak danych”.
- Repozytorium zawiera skrypty `scripts/llm/vllm_service.sh` i `scripts/llm/ollama_service.sh`, a `.env` ma uzupełnione `VLLM_*_COMMAND` / `OLLAMA_*_COMMAND`, dzięki czemu przyciski Start/Stop/Restart działają out-of-the-box (logi w `logs/vllm.log` i `logs/ollama.log`).
- Testy jednostkowe dla controllerów dodane; `pytest tests/test_llm_server_controller.py` przechodzi.
- Playwright `npm run test:perf -- --project=chat-latency`: scenariusz Next Cockpit OK, Legacy jest oznaczony jako optional.
- TODO: przebudować `ModelManager` + `/api/v1/models`, aby modele były grupowane per provider (vLLM vs Ollama) i panel UI potrafił zarządzać oboma zestawami – obecnie UI zakłada jeden wspólny bucket i nie pokazuje, z którego runtime pochodzi dany model.
- Panel „Serwery LLM” otrzymuje już statusy z realnych health-checków – `/api/v1/system/llm-servers` pingnuje `health_url` dla vLLM (`/v1/models`) i Ollamy (`/api/tags`), przekazując `status`, `latency_ms` oraz ewentualny `error_message`. Dzięki temu UI pokazuje realny stan zamiast `unknown`.

## Diagnoza Legacy UI
- Objaw: Legacy Cockpit (FastAPI templating) nie renderuje odpowiedzi – screenshot/test-results (`test-results/...Legacy.../error-context.md`).
- Websocket otrzymuje `AGENT_ACTION`, ale DOM `.chat-messages` nie aktualizuje się – do przeanalizowania `web/static/js/app.js` (obsługa `appendMessage`) i połączenie ze strumieniem `/ws`.
- Tymczasowe obejście: test perf Legacy ma `optional=true`, więc pipeline przechodzi, ale UI nadal do poprawy.

## Działania bieżące
- Restart usług (Next + Legacy) i powtórne `npm run test:perf -- --project=chat-latency` – Legacy może być pominięty, ale status trzeba raportować.
- Sprawdzić w panelu czy „Serwery LLM” poprawnie odświeża statusy, szczególnie gdy brak komend w `.env`.
- Przygotować debug legacy UI (sprawdzić strumień SSE vs. websocket, ewentualnie dodać logging).

## Priorytet
- Wysoki – bez tej informacji trudno diagnozować błędy w środowisku hybrydowym.
- Idealnie zamknąć przed kolejnym sprintem wydajnościowym.
