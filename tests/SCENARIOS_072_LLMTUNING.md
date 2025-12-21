## Scenariusze testowe: 072 Strojenie modelu LLM (Cockpit)

### 1) UI — otwarcie panelu strojenia
Kroki:
1. Wejdź na Cockpit (`/`).
2. Kliknij przycisk „Strojenie”.

Oczekiwane:
- Otwiera się panel „Parametry Generacji”.
- Widoczne są kontrolki parametrów (jeśli schema istnieje).

### 2) API — pobranie schematu i wartości
Kroki:
1. Wywołaj `GET /api/v1/models/{model}/config`.

Oczekiwane:
- `generation_schema` jest zwracany.
- `current_values` zawiera domyślne wartości (z manifestu/Ollama lub generation_config/vLLM).

### 3) Zapis override’ów
Kroki:
1. Zmień temperaturę i `max_tokens`.
2. Kliknij „Zastosuj”.

Oczekiwane:
- Toast sukcesu w UI.
- `MODEL_GENERATION_OVERRIDES` w `.env` ma zapis per runtime/model.

### 4) Reset i czyszczenie override’ów
Kroki:
1. Kliknij „Resetuj”.
2. Kliknij „Zastosuj”.

Oczekiwane:
- Override dla modelu/runtime zostaje usunięty.

### 5) Walidacja backendu
Kroki:
1. Wyślij `POST /api/v1/models/{model}/config` z wartością poza zakresem.

Oczekiwane:
- HTTP 400 + komunikat walidacyjny.

### 6) Źródła defaultów
Kroki:
1. Dla Ollama: sprawdź manifest i blob `params`.
2. Dla vLLM: sprawdź `generation_config.json`.

Oczekiwane:
- UI pokazuje wartości zgodne z tymi źródłami.
