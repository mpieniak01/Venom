# Triage blokad Policy/Autonomy

Runbook definiuje deterministyczny przebieg diagnozy operacji zablokowanych lub przepuszczonych w trybie degradacji przez backendowe bramki policy/autonomy.

## 1. Zakres

Stosuj, gdy API/UI pokazuje odpowiedź deny/degraded zawierającą:

- `decision` (`block` lub `degraded_allow`)
- `reason_code`
- `user_message`
- `technical_context`

Dotyczy:

- blokad route-level (`api.permission`, `policy.blocked.route`, `autonomy.blocked`)
- blokad orchestratora/task-pipeline (`core.policy.*`, `core.autonomy.*`)

## 2. Szybka klasyfikacja

1. Odczytaj `decision`.
2. Odczytaj `reason_code`.
3. Odczytaj `technical_context.operation` i `technical_context.enforcement_mode`.

Interpretacja:

- `decision=block`: terminalna blokada tej operacji (`technical_context.terminal=true`, `retryable=false`).
- `decision=degraded_allow`: operacja przeszła w trybie miękkim; traktuj jako sygnał driftu polityki.

## 3. Kontrola audit stream

Sprawdź ostatnie wpisy audytu dla danej sesji/taska:

1. `source`
2. `action`
3. `status`
4. `details.reason_code`
5. `details.technical_context`

Oczekiwane wzorce:

- blokada policy route-level: `source=api.permission`, `action=policy.blocked.route`, `status=blocked`
- blokada autonomy hard: `source=core.autonomy` lub `api.permission`, `action=autonomy.blocked`, `status=blocked`
- przepuszczenie autonomy soft: `source=core.autonomy`, `action=autonomy.degraded_allow`, `status=degraded`

## 4. Mapowanie reason-code -> akcja

1. `AUTONOMY_PERMISSION_DENIED`
- Zweryfikuj aktualny poziom autonomii (`/api/v1/system/autonomy`).
- Zweryfikuj wymagania operacji (`technical_context.required_level*`, jeśli obecne).
- Jeśli środowisko wymaga twardej egzekucji: ustaw `AUTONOMY_ENFORCEMENT_MODE=hard`.

2. `PERMISSION_DENIED`
- Sprawdź preconditions guardów route-level (localhost/admin header/token).
- Zweryfikuj mapowanie aktora (`x-authenticated-user`, `x-user`, client host).

3. `POLICY_*`
- Sprawdź konfigurację policy gate i wymuszenia runtime/tool.
- Potwierdź macierz provider/tool dla aktywnego profilu środowiska.

## 5. Walidacja trybu soft/hard

Sprawdź konfigurację runtime:

- `AUTONOMY_ENFORCEMENT_MODE=hard` -> twarda blokada
- `AUTONOMY_ENFORCEMENT_MODE=soft` -> przepuszczenie w degradacji

Checklista walidacyjna:

1. Decyzja zgodna z trybem (`block` dla hard, `degraded_allow` dla soft).
2. Audit `action/status` zgodny z trybem.
3. `technical_context.retryable=false` dla blokad autonomii.
4. Brak retry-loop dla tej samej zablokowanej operacji.

## 6. Weryfikacja kontraktu UI

UI ma prezentować kontrakt backendu, nie egzekwować autonomii lokalnie.

Zweryfikuj:

1. UI renderuje `user_message`.
2. UI pokazuje status deny/degraded.
3. UI nie zmienia semantyki `decision`/`reason_code`.

## 7. Checklista zamknięcia incydentu

1. Zidentyfikowano root cause (`policy`, `autonomy`, `configuration`, `actor context`).
2. Wdrożono wymaganą zmianę konfiguracji (jeśli potrzebna).
3. Dodano/zaktualizowano test regresyjny (unit/integration/contract).
4. Dołączono dowód z audytu (action/status/reason_code/operation).
5. `make pr-fast` zielone dla zmian kodu.
