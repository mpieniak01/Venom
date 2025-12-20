# 069: Selektor serwera LLM + spójne zarządzanie modelami

## Cel
Uprościć i ujednolicić zarządzanie serwerami LLM i modelami:
- jeden aktywny serwer naraz (brak równoległych runtime),
- wybór serwera jako `select` w UI,
- automatyczna aktywacja ostatnio wybranego modelu po starcie serwera,
- spójne przełączanie modelu zależne od aktywnego runtime.

## Zakres
1. **UI**
   - [x] Pole `select` do wyboru aktywnego serwera LLM.
   - [x] Blokada uruchomienia drugiego serwera (start → stop innych).
   - [x] Widoczna informacja: aktywny runtime + aktywny model.
   - [x] Statusy uruchomienia/wyłączenia pobierane z backendu (bez zgadywania w UI).

2. **Backend**
   - [x] Endpoint do ustawienia aktywnego runtime (start/stop innych).
   - [x] Zapisywanie „last selected model” per runtime.
   - [x] Po starcie runtime: auto-aktywacja ostatniego modelu.
   - [x] Potwierdzenie statusu po komendzie (czy serwer się uruchomił i czy poprzedni został zatrzymany).
   - [x] Potwierdzenie stanu aktywnego modelu po zmianie (z backendu).
   - [x] Rozdzielenie endpointów vLLM/Ollama (VLLM_ENDPOINT zamiast LLM_LOCAL_ENDPOINT).

3. **Kontrakt danych**
   - [x] Struktura: active_runtime + last_model_per_runtime.
   - [x] Walidacja: brak zmiany jeśli model nie istnieje na danym runtime.

4. **Bezpieczeństwo**
   - [x] Fail-fast, gdy model nie istnieje na docelowym serwerze.
   - [x] Fallback do poprzedniego modelu, jeśli model z `.env` nie istnieje.

## Kryteria akceptacji
- W UI można wybrać aktywny serwer LLM jako `select`.
- W danym momencie działa tylko jeden serwer LLM.
- Po starcie serwera automatycznie aktywuje się ostatnio wybrany model.
- Zmiana modelu działa tylko na aktywnym runtime.
- Jeśli model nie istnieje na serwerze, zmiana jest blokowana.
- UI pokazuje stan uruchomienia serwera i aktywnego modelu wyłącznie na podstawie backendu.

## Status
Zrealizowano backend i UI. UI korzysta z `/api/v1/system/llm-servers/active`, a backend wybiera model:
ostatni → poprzedni → błąd.

## Proponowane pliki do zmiany
- `web-next/components/config/services-panel.tsx` (select serwera)
- `web-next/hooks/use-api.ts` (nowe endpointy runtime)
- `venom_core/api/routes/system.py` lub `venom_core/api/routes/models.py` (runtime switch + last model)
- `venom_core/services/config_manager.py` (persist last model per runtime)
- `venom_core/utils/llm_runtime.py` (aktywny runtime)

## Uwagi
- Zmieniamy logikę tak, by nie było jednocześnie uruchomionych dwóch serwerów LLM.
- Last model per runtime powinien być odtwarzany po restarcie backendu.
