# 166 - Zakładka Modele: katalog zdalny GPT/Gemini + mapa spięć usług/modeli/endpointów

## Cel
Rozwinąć `http://localhost:3000/models` o pełny widok modeli zdalnych (OpenAI GPT + Google Gemini), tak aby:
1. było widać realnie aktywne integracje,
2. było widać jakie usługi Venom są spięte z jakimi modelami i endpointami,
3. operator mógł świadomie zarządzać routingiem lokalny vs zdalny.

## Kontekst (stan obecny)
1. Zakładka `/models` ma dziś dwa taby: `News` i `Models`.
2. Obsługuje głównie katalog/operacje lokalne (`ollama`, `huggingface`, runtime `ollama/vllm`).
3. Częściowa integracja providerów zdalnych istnieje w systemie (provider governance, slash aliases), ale nie ma dedykowanego panelu operacyjnego i mapy spięć per endpoint/usługa.

## Zakres PR (Venom)
### A. Nowa zakładka UI: `Modele zdalne`
1. Dodać trzeci tab w `/models` obok `News` i `Models`.
2. Sekcje w tabie:
   - `Provider status` (OpenAI / Google): dostępność, ostatni test, błąd, latency.
   - `Remote models catalog` (pobierane dynamicznie z API providera, bez hardkodowania na sztywno).
   - `Connectivity map` (usługa Venom -> endpoint -> provider -> model -> status).
   - `Policy/runtime` (czy flow używa local-first, fallback chain, limity/rate class).

### B. Backend API w core pod tab `Modele zdalne`
1. `GET /api/v1/models/remote/providers`
   - status integracji providerów (`configured`, `reachable`, `degraded`, `disabled`),
   - metryki health-check.
2. `GET /api/v1/models/remote/catalog?provider=openai|google`
   - lista modeli + capability flags,
   - źródło danych: endpointy `list models` providera.
3. `GET /api/v1/models/remote/connectivity`
   - relacje: `service_id`, `endpoint`, `http_method`, `provider`, `model`, `routing_mode`, `fallback_order`.
4. `POST /api/v1/models/remote/validate`
   - wymuszony test połączenia dla wybranego provider/model,
   - zapis wyniku do audytu technicznego core.

### C. Model danych i kontrakt
1. Wprowadzić spójne typy TS/Pydantic:
   - `RemoteProviderStatus`,
   - `RemoteModelInfo`,
   - `ServiceModelBinding`.
2. Unikać „martwych” list modeli: identyfikatory modeli trzymane dynamicznie po `list models` + cache TTL.
3. Dla kompatybilności operacyjnej dodać `model_alias` (wewnętrzna nazwa stabilna) -> `provider_model_name` (aktualna nazwa u dostawcy).

### D. UX i operacyjność
1. Filtrowanie connectivity map po:
   - providerze,
   - usłudze API,
   - stanie (`ok/warning/fail/degraded`).
2. Jednoliniowe wpisy i spójna paleta badge jak w `Konfiguracja -> Audyt`.
3. Widok „co jest spięte” ma być czytelny bez otwierania devtools:
   - np. `Tasks API | POST /api/v1/tasks | OPENAI | gpt-5.x | ACTIVE`.

## Zakres poza PR
1. Bez przebudowy logiki wykonania promptów/agentów.
2. Bez migracji danych historycznych.
3. Bez zmiany istniejących endpointów lokalnych modeli (Ollama/HF) poza niezbędnym refactorem współdzielonych typów.

## Źródła i założenia (zweryfikowane 2024-02-21)
1. OpenAI API reference:
   - `GET /v1/models` (listowanie modeli),
   - `POST /v1/responses` (główny endpoint generacji multimodal/tooling).
2. Google Gemini API:
   - `GET /v1beta/models` i `GET /v1beta/{name=models/*}`,
   - metadata modelu zawiera m.in. `inputTokenLimit`, `outputTokenLimit`, `supportedGenerationMethods`.
3. Ze względu na częste zmiany nazw i preview/stable, UI nie opiera się na stałej liście modeli.

## Kryteria akceptacji
1. `/models` ma nowy tab `Modele zdalne` z 4 sekcjami: status, katalog, mapa spięć, walidacja.
2. Lista modeli OpenAI/Gemini ładuje się z endpointów agregujących core i pokazuje timestamp odświeżenia + źródło.
3. Operator widzi jednoznacznie „która usługa używa którego modelu i endpointu”.
4. Błędy providerów nie wywracają całego panelu (degradacja częściowa + komunikat per sekcja).
5. Zmiany mają testy kontraktu API + testy UI dla stanów: `ok`, `provider down`, `empty catalog`.

## Plan wdrożenia (iteracyjny)
1. Iteracja 1: backend status + catalog + cache TTL.
2. Iteracja 2: connectivity map (powiązanie z `/config` Mapa API).
3. Iteracja 3: UI tab + filtry + i18n pl/en/de.
4. Iteracja 4: testy i audyt techniczny walidacji providerów.

## Ryzyka
1. Rozjazd nazw modeli między providerami i aliasami wewnętrznymi.
2. Rate-limit przy częstym odświeżaniu list modeli.
3. Częściowa niedostępność providerów (potrzebny circuit-breaker i cache fallback).

## DoD
1. PR zawiera endpointy, UI tab, testy oraz i18n.
2. Dokumentacja użytkowa `/docs/llm-models` ma sekcję „Modele zdalne”.
3. Hard gate’y dla kodu przechodzą (`make pr-fast`, `make check-new-code-coverage`).

## Linki referencyjne
1. OpenAI Models API: https://developers.openai.com/api/reference/resources/models/methods/list
2. OpenAI Responses API: https://developers.openai.com/api/reference/resources/responses/methods/create
3. Gemini Models guide: https://ai.google.dev/gemini-api/docs/models
4. Gemini Models API reference: https://ai.google.dev/api/models
5. Google AI Studio (punkt wejścia): https://ai.google.dev/aistudio?hl=pl
