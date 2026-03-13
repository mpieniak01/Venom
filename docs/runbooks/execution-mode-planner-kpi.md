# Runbook: Execution Mode Planner KPI (202A)

This runbook defines operational triage for execution-mode planning quality.

## Scope

Use this runbook when monitoring or investigating:
- abnormal growth in `gui_fallback` usage,
- drop in planner `success_rate`,
- non-zero `retry_loop_rate`,
- increase in `manual_intervention_rate`.

Primary endpoint:
- `GET /api/v1/metrics/execution-mode`

## KPI Contract

Expected payload sections:
- `kpi.total`
- `kpi.counts.api_skill|browser_automation|gui_fallback`
- `kpi.share_rate.api_skill|browser_automation|gui_fallback`
- `kpi.success_rate`
- `kpi.manual_intervention_rate`
- `kpi.retry_loop_rate`
- `alerts.gui_fallback_overuse.active|threshold|current|severity`

## SLO Targets

Default operational targets:
- `api_skill share_rate >= 80%` for standard workloads,
- `gui_fallback share_rate < 20%`,
- `retry_loop_rate == 0%` for terminal policy/autonomy blocks,
- `manual_intervention_rate <= 10%`.

## Alert Rules

### GUI Fallback Overuse

Condition:
- `alerts.gui_fallback_overuse.active == true`

Severity:
- `high`

Immediate response:
1. Verify if workload changed (desktop-heavy or vision-heavy tasks).
2. Check planner route distribution (`kpi.share_rate`).
3. Confirm API/skill templates are still matched for top intents.

## Triage: Misclassification of execution_mode

### Step 1: Confirm decision metadata on task

Inspect task context:
- `context_history.execution_mode`
- `context_history.fallback_reason`
- `context_history.execution_mode_reason_code`
- `context_history.execution_template`
- `context_history.browser_profile`
- `context_history.gui_fallback_contract`

Inspect trace:
- `DecisionGate.execution_mode_selector`

### Step 2: Validate deterministic routing inputs

Check if request had:
- forced tool requiring GUI (`ui`, `desktop`, `vision`, `ghost`),
- browser intent (`RESEARCH`, `KNOWLEDGE_SEARCH`, `E2E_TESTING`),
- API/skill intent (`VERSION_CONTROL`, `FILE_OPERATION`, `DOCUMENTATION`, etc.).

If forced tool or intent changed unexpectedly, classify as input issue.

### Step 3: Validate fallback contract gates

For `gui_fallback` ensure contract fields are present:
- `entry_gate.api_skill_available == false`
- `entry_gate.browser_stable_path_available == false`
- `autonomy.required_level == elevated`
- `safety.critical_steps_fail_closed == true`
- `safety.terminal_blocks_retryable == false`

If any required field is missing, classify as contract regression.

### Step 4: Map to owner and action

- Template mapping regression -> Planner owner (202A.2)
- Browser profile/contract regression -> Browser path owner (202A.3)
- GUI gate/autonomy regression -> Governance owner (202A.4)
- Metrics payload/alert regression -> Observability owner (202A.5)

## Remediation Matrix

- `gui_fallback` too high + stable API tasks available:
  - expand API template mapping,
  - tighten browser/GUI eligibility.

- `retry_loop_rate > 0`:
  - enforce terminal block no-retry policy,
  - verify fail-closed behavior for critical steps.

- `manual_intervention_rate` high:
  - inspect top fallback reasons,
  - add deterministic route rule or template.

## Verification Checklist After Fix

1. Targeted tests pass:
   - `tests/test_execution_mode_planner.py`
   - `tests/test_orchestrator_decision_gates.py`
   - `tests/test_metrics.py`
   - `tests/test_metrics_routes.py`
2. `make pr-fast` passes.
3. `GET /api/v1/metrics/execution-mode` returns updated KPI and alert state.
4. No regressions in task response contract (`execution_mode`, `fallback_reason`).
