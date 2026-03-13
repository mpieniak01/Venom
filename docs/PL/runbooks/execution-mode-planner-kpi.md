# Runbook: KPI planera execution_mode (202A)

Runbook opisuje operacyjny triage dla jakosci klasyfikacji sciezek wykonania.

## Zakres

Stosuj runbook, gdy wystepuje:
- wzrost udzialu `gui_fallback`,
- spadek `success_rate`,
- niezerowe `retry_loop_rate`,
- wzrost `manual_intervention_rate`.

Endpoint operacyjny:
- `GET /api/v1/metrics/execution-mode`

## Kontrakt KPI

Wymagane pola:
- `kpi.total`
- `kpi.counts.api_skill|browser_automation|gui_fallback`
- `kpi.share_rate.api_skill|browser_automation|gui_fallback`
- `kpi.success_rate`
- `kpi.manual_intervention_rate`
- `kpi.retry_loop_rate`
- `alerts.gui_fallback_overuse.active|threshold|current|severity`

## Cele operacyjne

- `api_skill share_rate >= 80%` dla standardowych workloadow,
- `gui_fallback share_rate < 20%`,
- `retry_loop_rate == 0%` dla terminalnych blokad policy/autonomy,
- `manual_intervention_rate <= 10%`.

## Triage blednej klasyfikacji

1. Sprawdz metadane taska:
   - `context_history.execution_mode`
   - `context_history.fallback_reason`
   - `context_history.execution_mode_reason_code`
   - `context_history.execution_template`
   - `context_history.browser_profile`
   - `context_history.gui_fallback_contract`

2. Sprawdz trace:
   - `DecisionGate.execution_mode_selector`

3. Zweryfikuj gate kontraktu GUI fallback:
   - `entry_gate.api_skill_available == false`
   - `entry_gate.browser_stable_path_available == false`
   - `autonomy.required_level == elevated`
   - `safety.critical_steps_fail_closed == true`
   - `safety.terminal_blocks_retryable == false`

4. Przypisz ownera incydentu:
   - mapowanie template -> 202A.2,
   - kontrakt browser -> 202A.3,
   - hardening GUI -> 202A.4,
   - payload KPI/alert -> 202A.5.

## Weryfikacja po poprawce

1. Przechodza testy:
   - `tests/test_execution_mode_planner.py`
   - `tests/test_orchestrator_decision_gates.py`
   - `tests/test_metrics.py`
   - `tests/test_metrics_routes.py`
2. Przechodzi `make pr-fast`.
3. Endpoint `/api/v1/metrics/execution-mode` zwraca aktualny stan KPI i alertow.
