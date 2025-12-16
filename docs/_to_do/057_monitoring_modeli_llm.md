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

## Status wdrożenia
- Instrumentacja backendu i StateManagera gotowa – `TaskResponse`, SSE `/tasks/{id}/stream` oraz `RequestTracer` dostarczają `llm_provider/model/endpoint`, a `state_manager.context_history["llm_runtime"]` trzyma metadane runtime.
- `/api/v1/models` zwraca także `active` z opisem runtime i zaznacza aktywny katalog/model, a ModelManager skanuje też `./models`.
- Frontend raportuje aktywny runtime w panelu „Modele”, pokazuje źródło w historii requestów i przy błędach wykorzystuje czerwony banner SSE.
- Testy: dodane jednostkowe przypadki dla merge kontekstu oraz rozpoznania modeli w katalogu `./models`. `pytest ...test_state_manager_update_context_merges tests/test_model_manager.py::test_model_manager_list_local_models_workspace_folder` przeszły.

## Działania bieżące
- UI i API już konsolidują obsługę nowych pól; pozostało przetestować scenariusz E2E (np. symulacja 404 z vLLM) i włączyć telemetrię alertów.
- Pre-commit zgłasza ostrzeżenie dla `black` i `ruff`:
  - `black` używa mutable `rev` (https://pre-commit.com/#using-the-latest-version-for-a-repository) i podczas `pre-commit` wykonał `black` na `tests/perf/test_chat_pipeline.py`.
  - `ruff-format` również edytuje pliki, więc należy ponownie uruchomić `pre-commit` lub `pre-commit autoupdate`, jeśli chcemy odświeżyć referencje hooków.

## Priorytet
- Wysoki – bez tej informacji trudno diagnozować błędy w środowisku hybrydowym.
- Idealnie zamknąć przed kolejnym sprintem wydajnościowym.
