# Workflow Control Plane & Composer - Dokumentacja

## Przegląd

Ten dokument definiuje kontrakt API dla Workflow Control Plane oraz interfejs wizualnego Kompozytora. Zapewnia on centralne zarządzanie konfiguracją całego stosu Venom.

Przewodnik operatorski (UX, źródła lokalne/chmura, troubleshooting): `docs/PL/THE_WORKFLOW_CONTROL.md`.

## Wizualny Kompozytor (UX)

Ekran Workflow Control wprowadza **Wizualny Kompozytor** oparty o React Flow.

### Tory (Swimlanes)
Diagram jest podzielony na domeny:
1. **Decision & Intent**: Strategia (Heurystyka/LLM) i Klasyfikacja Intencji.
2. **Kernel & Embedding**: Silnik Wykonawczy (Python/Docker) i Embeddings.
3. **Runtime & Provider**: Serwer LLM (Ollama/vLLM/ONNX) i Dostawca Modelu (Lokalny/Chmura).

### Zasady Łączenia
Kompozytor wymusza poprawne połączenia:
- `decision_strategy` -> `intent_mode`
- `intent_mode` -> `embedding_model` (jeśli wymagane)
- `runtime` -> `provider`
- `provider` -> `model`

Nieprawidłowe połączenia są blokowane z konkretnym `reason_code`.

## Kontrakt API

Wszystkie endpointy są prefiksowane: `/api/v1/workflow/control`

### Tryby Zastosowania (Apply Modes)

| Tryb | Wartość | Opis |
|------|---------|------|
| HOT_SWAP | `hot_swap` | Zmiana zastosowana natychmiast bez restartu |
| RESTART_REQUIRED | `restart_required` | Zmiana wymaga restartu usługi |
| REJECTED | `rejected` | Zmiana odrzucona z powodu błędu walidacji |

## Endpointy

### 1. Planowanie Zmian (Plan)

**Endpoint:** `POST /plan`

Planuje zmiany konfiguracji i waliduje kompatybilność przed zastosowaniem.

### 2. Zastosowanie Zmian (Apply)

**Endpoint:** `POST /apply`

Aplikuje wcześniej zaplanowane zmiany używając biletu wykonania (execution ticket).

### 3. Stan Systemu (State)

**Endpoint:** `GET /state`

Zwraca kanoniczny stan operatorski dla Workflow Control.

**Parametry zapytania:**
- `request_id` (opcjonalny) - jawny wybór targetu requestu.

Bez `request_id` backend stosuje fallback:
1. najnowszy aktywny request,
2. ostatni request,
3. brak aktywnego targetu.

**Sekcje odpowiedzi (204A):**
1. `system_state`
2. `meta`
3. `workflow_target`
4. `config_fields[]`
5. `runtime_services[]`
6. `execution_steps[]`
7. `graph.nodes[]` / `graph.edges[]`
8. `allowed_actions`

### 4. Brama akcji runtime

**Endpoint:** `POST /runtime/{service_id}/{action}`

Wspólna brama sterowania usługami runtime.

Dostępne akcje:
1. `start`
2. `stop`
3. `restart`

### 5. Brama operacji workflow

**Endpoint:** `POST /workflow/{request_id}/{operation}`

Wspólna brama operacji workflow dla wskazanego requestu.

Dostępne operacje:
1. `pause`
2. `resume`
3. `cancel`
4. `retry`
5. `dry_run`

## Macierz Kompatybilności

Control Plane waliduje kompatybilność między:

1. **Kernel × Runtime**
2. **Runtime × Provider**
3. **Provider × Model**
4. **Embedding × Provider**

Szczegóły pełnych payloadów JSON oraz przykłady odpowiedzi znajdują się w:
`docs/WORKFLOW_CONTROL_PLANE_API.md`.
