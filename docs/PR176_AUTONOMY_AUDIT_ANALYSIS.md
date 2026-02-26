# 176 - Autonomia vs Audyt: analiza powiązania i poziomu raportowania

## Cel
Zweryfikować, czy:
1. egzekwowanie autonomii jest spięte z audytem,
2. audyt raportuje poziom autonomii, na którym zaszła decyzja (allow/block/change).

## Krótka odpowiedź (stan na 2026-02-26)
1. **Powiązanie autonomia -> audyt jest niepełne.**
2. **Poziom autonomii nie jest raportowany konsekwentnie w audit stream.**
3. **Policy gate jest sprawdzany w orchestratorze, ale nie ma dedykowanego wpisu audytowego z kontekstem policy/autonomy.**

## Wyniki analizy kodu

### A. Gdzie autonomia jest realnie egzekwowana
1. `autonomy_enforcement` blokuje mutacje przez `PermissionError`:
   - `require_file_write_permission`, `require_shell_permission`, `require_core_patch_permission`
   - plik: `venom_core/core/autonomy_enforcement.py`
2. `PermissionGuard` trzyma poziom i uprawnienia:
   - `set_level`, `check_permission`, `can_write_files`, `can_execute_shell`
   - plik: `venom_core/core/permission_guard.py`
3. Krytyczne ścieżki mutujące używają gate:
   - `CoreSkill.hot_patch/rollback` -> `require_core_patch_permission`
   - `McpManagerSkill.import_mcp_tool/_run_shell` -> `require_shell_permission`

Wniosek: gate działa technicznie, ale działa głównie jako wyjątek runtime.

### B. Gdzie działa audyt
1. Kanoniczny stream audytu:
   - serwis: `venom_core/services/audit_stream.py`
   - API: `GET/POST /api/v1/audit/stream` (`venom_core/api/routes/audit_stream.py`)
2. Globalny middleware HTTP publikuje tylko metadane requestu:
   - `source=core.http`, `action=http.<method>`, `status_code`, `http_path`
   - plik: `venom_core/main.py` (middleware `audit_http_requests`)
3. Admin audit jest mirrorowany do kanonicznego streamu:
   - `venom_core/core/admin_audit.py`

Wniosek: audit stream jest obecny i spójny technicznie, ale nie ma dedykowanej semantyki dla zdarzeń autonomii.

### C. Spięcie autonomy <-> audit (luki)
1. Zmiana poziomu autonomii (`POST /api/v1/system/autonomy`) nie publikuje zdarzenia audytowego z:
   - `old_level`, `new_level`, `actor`, `reason`.
2. Blokada `AutonomyViolation` nie jest publikowana do audit stream jako osobne zdarzenie security/governance.
3. Policy block (`policy_gate`) zapisuje:
   - `state_manager` context,
   - `request_tracer` step,
   - metrykę `policy_blocked_count`,
   ale nie publikuje wpisu do `audit_stream`.
4. `RoutingDecision.policy_gate_passed` jest ustawiane na stałe `True` w integracji routingu, więc raport nie niesie rzeczywistego stanu policy.

## Czy to jest sprawdzane testami
1. Tak, są testy egzekucji blokad (np. `tests/security/test_autonomy_enforcement.py`), ale koncentrują się na wyjątku/blokadzie.
2. Brakuje testów, które wymagają obecności wpisu audytowego po:
   - zmianie poziomu autonomii,
   - blokadzie autonomy,
   - blokadzie policy gate.

## Ocena ryzyka
1. **Compliance/Auditability gap**: decyzje bezpieczeństwa nie są jednoznacznie audytowalne w jednym strumieniu.
2. **Forensics gap**: w incydencie nie ma prostego timeline:
   - kto podniósł poziom,
   - na jakim poziomie operacja została zablokowana,
   - jaka reguła policy/autonomy zadziałała.
3. **Observability gap**: UI audytu pokazuje requesty HTTP, ale nie semantykę decyzji autonomii.

## Zakres proponowany do PR 176 (implementacyjny)
1. Dodać canonical eventy audytowe dla autonomii:
   - `action=autonomy.level_changed`
   - `details`: `old_level`, `old_level_name`, `new_level`, `new_level_name`, `actor`, `source`.
2. Dodać canonical eventy dla blokad:
   - `action=autonomy.blocked`
   - `details`: `operation`, `required_level`, `required_level_name`, `current_level`, `current_level_name`, `skill_name`, `task_id/session_id` (jeśli dostępne).
3. Dodać audit eventy dla policy gate block:
   - `action=policy.blocked.before_provider` i `policy.blocked.before_tool`
   - `details`: `reason_code`, `intent`, `planned_provider`, `forced_tool`, `session_id`.
4. Naprawić raportowanie kontraktu routingowego:
   - `policy_gate_passed` nie może być stale `True`; ma wynikać z realnej decyzji policy.

## Testy do dodania w PR 176
1. `POST /system/autonomy` tworzy wpis `autonomy.level_changed` w `audit_stream`.
2. Blokada core patch na poziomie < ROOT tworzy wpis `autonomy.blocked`.
3. Blokada policy przed provider i przed tool tworzy wpisy `policy.blocked.*`.
4. Wpis audytowy zawiera poziom wykonania (co najmniej `current_level` + `current_level_name`).

## Definicja ukończenia PR 176
1. Każda decyzja deny (autonomy/policy) ma wpis w kanonicznym audycie.
2. Każda zmiana poziomu autonomii ma wpis audytowy z poprzednim i nowym poziomem.
3. Audit UI (`/api/v1/audit/stream`) pozwala filtrować po `action=autonomy.*` i `policy.*`.
4. Testy regresyjne autonomy/policy + audit przechodzą.
