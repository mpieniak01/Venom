# 072: Strojenie modelu LLM (panel główny)
Status: wykonane

## Cel
Udostępnić sterowanie parametrami generacji konkretnego modelu LLM z poziomu
ekranu głównego (Cockpit), wraz z walidacją i podglądem aktualnych ustawień.

## Stan obecny w kodzie
- UI: istnieje `DynamicParameterForm` (schema float/int/bool/enum/list), brak podpięcia w Cockpit.
- API: istnieje `GET /api/v1/models/{model}/config` (`generation_schema`, `fetchModelConfig`).
- Backend: `ModelRegistry` buduje `generation_schema` (Ollama ma detekcję Llama3).

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
5. **UX odpowiedzi LLM**
   - Przejście na streaming lub synchroniczne pobranie pierwszej porcji odpowiedzi
     z serwera LLM.
   - Dopuszczalna inna wydajna metoda „pierwszego kontaktu” z użytkownikiem,
     poprawiająca wrażenia (time-to-first-token).

## Kryteria akceptacji
- Parametry modelu są widoczne i edytowalne w Cockpit.
- Zmiana parametrów jest walidowana i zapisywana.
- UI pokazuje potwierdzenie powodzenia/odrzucenia.
- Schemat parametrów jest spójny z faktycznymi możliwościami runtime.
- UX: użytkownik widzi pierwszą część odpowiedzi szybko (streaming/first chunk).

## Postęp realizacji
- [x] Backend: zapis/odczyt override per runtime/model + walidacja.
- [x] UI: panel strojenia w Cockpit, `DynamicParameterForm`, `updateModelConfig`.
- [x] Dokumentacja: `MODEL_GENERATION_OVERRIDES` w `docs/CONFIG_PANEL.md`.
- [x] Runtime: domyślne wartości z manifestów (Ollama) i `generation_config.json` (vLLM).
- [x] UX: streaming/first chunk + metryka time-to-first-token.

## Scenariusze testowe
1. **Pobranie schematu**
   - Otwórz panel strojenia.
   - Oczekiwane: schema i wartości bieżące w formularzu.
2. **Zapis parametrów**
   - Zmień temperaturę i max_tokens, kliknij „Zastosuj”.
   - Oczekiwane: toast sukcesu, zapis w `MODEL_GENERATION_OVERRIDES`.
3. **Reset do domyślnych**
   - Kliknij „Resetuj” i „Zastosuj”.
   - Oczekiwane: usunięcie override’ów dla modelu/runtime.
4. **Walidacja**
   - Ustaw wartość poza zakresem.
   - Oczekiwane: błąd 400 i komunikat walidacyjny.
5. **Runtime**
   - Zmień aktywny runtime (ollama/vllm) i sprawdź, że override’y są per runtime.
6. **UX first token**
   - Wyślij zapytanie i potwierdź widoczny szybki pierwszy chunk/stream.

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
- Weryfikować min/max/enum po stronie backendu (nie ufać tylko UI).

## Finalna analiza
- UX first token zrealizowany przez streaming i logowanie pierwszego fragmentu.
- Metryka time-to-first-token dostępna w `metrics` (średnia + próbki).
