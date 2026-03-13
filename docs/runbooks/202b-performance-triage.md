# Runbook: 202B Local Runtime Performance Triage

## Scope
This runbook covers the optimization stages delivered under 202B:
- execution planners hot path,
- orchestrator dispatch batching,
- submit-path routing payload deduplication,
- routing decision cache,
- policy risk-context allocation reduction.

## Entry Conditions
Use this runbook when at least one of the following is observed:
- noticeable latency increase in task submit or dispatch path,
- memory growth/regression during local runtime load,
- failures in the 202B regression gate,
- unstable behavior after tuning changes.

## Quick Triage (5-10 minutes)
1. Verify service baseline health.
```bash
curl -s http://127.0.0.1:8000/health | cat
```
2. Run the dedicated quality gate.
```bash
make test-202b-gate
```
3. If gate fails, identify the failing stage by test group:
- planner: tests/test_execution_mode_planner*.py
- dispatch/policy: tests/test_orchestrator_decision_gates.py, tests/test_policy_gate_integration.py
- routing: tests/test_routing_integration*.py, tests/test_routing_contract.py

## Diagnostic Matrix

### Symptom: Routing stage regression
Signals:
- failures in tests/test_routing_integration*.py
- increased routing decision latency
Actions:
1. Re-run routing-only check:
```bash
.venv/bin/pytest tests/test_routing_integration.py tests/test_routing_integration_perf.py -q
```
2. Temporarily disable router cache and re-check:
```bash
VENOM_ROUTER_CACHE_ENABLED=0 .venv/bin/pytest tests/test_routing_integration.py tests/test_routing_integration_perf.py -q
```
3. If disabling cache stabilizes behavior, keep cache disabled operationally and prepare code-level rollback.

### Symptom: Dispatch/policy stage regression
Signals:
- failures in tests/test_orchestrator_decision_gates.py
- failures in tests/test_policy_gate_integration.py
Actions:
1. Validate dispatch path:
```bash
.venv/bin/pytest tests/test_orchestrator_decision_gates.py tests/test_orchestrator_core_scenarios.py -q
```
2. Validate policy and risk context:
```bash
.venv/bin/pytest tests/test_policy_gate_integration.py tests/test_orchestrator_risk_context_perf.py -q
```

### Symptom: Planner stage regression
Signals:
- failures in tests/test_execution_mode_planner.py
- planner micro-perf degradation
Actions:
1. Re-run planner checks:
```bash
.venv/bin/pytest tests/test_execution_mode_planner.py tests/test_execution_mode_planner_perf.py -q
```

## Rollback Strategy

### Level 1: Operational rollback (no code revert)
Use when issue is routing-cache related and immediate stabilization is required.
1. Disable router cache:
```bash
export VENOM_ROUTER_CACHE_ENABLED=0
```
2. Restart backend.
3. Re-run quick gate subset:
```bash
.venv/bin/pytest tests/test_routing_integration.py tests/test_routing_integration_perf.py -q
```

### Level 2: Stage rollback (code revert for a single hot path)
Use when one stage is unstable and needs isolation.
1. Revert only affected files from the change set.
2. Run stage-specific tests plus shared gate:
```bash
make test-202b-gate
```
3. If green, keep other 202B stages active.

### Level 3: Full 202B rollback
Use if multiple hot paths regress simultaneously.
1. Revert all 202B optimization commits.
2. Run full 202B gate:
```bash
make test-202b-gate
```
3. Confirm baseline stability before reintroducing stages incrementally.

## Exit Criteria
A triage incident is closed only if:
1. make test-202b-gate returns green,
2. no critical regressions are present in stage-specific suites,
3. selected rollback/mitigation is documented in the issue or PR.

## Reporting Template
- Incident ID:
- Trigger:
- Failed tests:
- Mitigation level used (1/2/3):
- Final gate result:
- Follow-up action:
