# Workflow Control Plane & Composer - Dokumentacja

## Przegląd

Ten dokument definiuje kontrakt API dla Workflow Control Plane oraz interfejs wizualnego Kompozytora. Zapewnia on centralne zarządzanie konfiguracją całego stosu Venom.

## Wizualny Kompozytor (UX)

Ekran Workflow Control wprowadza **Wizualny Kompozytor** oparty o React Flow.

### Tory (Swimlanes)
Diagram jest podzielony na domeny:
1. **Decision & Intent**: Strategia (Heurystyka/LLM) i Klasyfikacja Intencji.
2. **Kernel & Embedding**: Silnik Wykonawczy (Python/Docker) i Embeddings.
3. **Runtime & Provider**: Serwer LLM (Ollama/vLLM) i Dostawca Modelu (Lokalny/Chmura).

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

Zwraca aktualny stan całego systemu (runtime, provider, config).

## Macierz Kompatybilności

Control Plane waliduje kompatybilność między:

1. **Kernel × Runtime**
2. **Runtime × Provider**
3. **Provider × Model**
4. **Embedding × Provider**

Szczegóły payloadów JSON znajdują się w wersji angielskiej dokumentacji.
