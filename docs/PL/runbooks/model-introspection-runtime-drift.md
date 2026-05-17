# Runbook: rozjazd runtime w Model Introspection (PL)

## Zakres

Użyj tego runbooka, gdy `/inspector/model-introspection` pokazuje:

1. `R0_MODEL_DRIFT`, albo
2. `Analysis skipped` z `MODEL_DRIFT_DETECTED`, albo
3. różne tożsamości modelu między runtime/backend/UI.

Cel: przywrócić spójny aktywny model w czasie < 2 min.

## Warunki wejściowe

1. Stos uruchomiony przez `make start` (lub kontrolowany flow UI).
2. Operator ma dostęp do UI i shella hosta.
3. W trakcie naprawy nikt nie wykonuje równoległych, ręcznych przełączeń runtime.

## Procedura naprawcza (< 2 min)

1. Otwórz `/inspector/model-introspection`.
2. Kliknij `Odśwież snapshot` i potwierdź rozjazd (`drift present` / `R0_MODEL_DRIFT`).
3. Wykonaj dokładnie jedno kontrolowane przełączenie modelu z UI (selektor runtime/modelu).
4. Poczekaj na zakończenie przełączenia i kliknij ponownie `Odśwież snapshot`.
5. Zweryfikuj:
   - `drift clean`,
   - jedna etykieta aktywnego runtime/modelu w summary/results/runtime context.
6. Uruchom analizę ponownie na tym samym promptcie.

Oczekiwany wynik:

1. analiza nie jest pominięta (`skipped`),
2. brak `MODEL_DRIFT_DETECTED`,
3. brak `R0_MODEL_DRIFT` w werdykcie operatora.

## Twarde kontrole (jeśli nadal fail)

1. `make status` musi pokazać jeden aktywny stos/runtime.
2. Endpoint runtime musi być healthy (`/health` na aktywnym host:port).
3. `GET /api/v1/system/llm-runtime/active` musi zwracać jedną spójną tożsamość modelu.

Jeśli nadal jest rozjazd:

1. zatrzymaj procesy runtime uruchomione poza `make start`/UI,
2. wykonaj jeszcze jedno kontrolowane przełączenie z UI,
3. odśwież snapshot i ponów analizę.

## Do / Don't

Rób:

1. przełączaj model jednym kanałem prawdy (`make start` albo UI),
2. sprawdzaj drift przed każdym runem live analysis.

Nie rób:

1. wymuszania aktywnego runtime przez edycję `.env*` podczas działania sesji,
2. ręcznych, równoległych restartów runtime podczas diagnostyki,
3. traktowania wartości bootstrapowych jako live runtime truth.
