# 072: Strojenie modelu LLM (panel główny)

## Cel
Udostępnić sterowanie parametrami generacji konkretnego modelu LLM z poziomu
ekranu głównego (Cockpit), wraz z walidacją i podglądem aktualnych ustawień.

## Stan obecny w kodzie (po analizie)
- UI: istnieje `DynamicParameterForm` z obsługą schema (float/int/bool/enum/list),
  ale nie jest wpięty w Cockpit.
- API: jest endpoint `GET /api/v1/models/{model}/config` zwracający
  `generation_schema` (z `ModelRegistry`), dostępny w `fetchModelConfig`.
- Backend: `ModelRegistry` buduje `generation_schema` dla modeli (Ollama ma
  detekcję Llama3 i zawęża zakres temperatury).
- Brak endpointu do zapisu parametrów (brak `POST/PATCH` per model/runtime).

## Zakres
1. **Parametry modelu**
   - Pobranie i wyświetlenie parametrów możliwych do sterowania (schema).
   - Obsługa wartości domyślnych i ograniczeń (min/max, enum).
   - Walidacja przed zapisem.

2. **UI w Cockpit**
   - Sekcja „Strojenie modelu” na ekranie głównym.
   - Kontrolki powiązane z parametrami (slidery, selecty, inputy).
   - Przycisk „Zastosuj” + status (sukces/błąd).

3. **Backend/API**
   - Endpoint do pobrania schematu parametrów modelu.
   - Endpoint do aktualizacji parametrów (per model / per runtime).

4. **Telemetria**
   - Log zdarzeń zmiany parametrów (kto, kiedy, model, różnice).
   - Metryka liczby zmian parametrów.

## Kryteria akceptacji
- Parametry modelu są widoczne i edytowalne w Cockpit.
- Zmiana parametrów jest walidowana i zapisywana.
- UI pokazuje potwierdzenie powodzenia/odrzucenia.
- Schemat parametrów jest spójny z faktycznymi możliwościami runtime.

## Do zrobienia
1. **Backend: zapis parametrów**
   - Dodać `POST/PATCH /api/v1/models/{model}/config` zapisujący wybrane wartości.
   - Zapisać wartości w config (np. `config_manager` + SETTINGS) per runtime.
   - W `generation_params_adapter.py` uwzględnić override’y z configu.
2. **UI: Cockpit**
   - Dodać sekcję „Strojenie modelu” pod aktywnym modelem.
   - Wywołać `fetchModelConfig` i podać schema do `DynamicParameterForm`.
   - Dodać przycisk „Zastosuj” i akcję zapisu przez nowy endpoint.
3. **Spójność z runtime**
   - Parametry zapisywać per runtime (`ollama`, `vllm`) i per model.
   - Obsługa fallbacku: brak schema => informacja + blokada zapisu.
4. **Telemetria**
   - Zdarzenie zmiany parametrów (model, runtime, diff, user_id).
   - Licznik zmian (metryki).

## Proponowane pliki do zmiany
- `web-next/components/cockpit/cockpit-home.tsx`
- `web-next/components/ui/dynamic-parameter-form.tsx`
- `web-next/hooks/use-api.ts`
- `venom_core/api/routes/models.py`
- `venom_core/core/generation_params_adapter.py`
- `docs/CONFIG_PANEL.md`

## Zależności / uwagi dla wykonawcy
- UI już ma komponent formularza, brakuje tylko podłączenia.
- Endpoint `GET /api/v1/models/{model}/config` już istnieje.
- Brakuje trwałego storage dla override’ów (config lub osobny plik JSON).
- Weryfikować min/max/enum po stronie backendu (nie ufać tylko UI).
