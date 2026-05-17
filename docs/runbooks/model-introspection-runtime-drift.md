# Model Introspection Runtime Drift Runbook (EN)

## Scope

Use this runbook when `/inspector/model-introspection` reports:

1. `R0_MODEL_DRIFT`, or
2. `Analysis skipped` with `MODEL_DRIFT_DETECTED`, or
3. mixed model identity across runtime/backend/UI.

Target: restore consistent runtime model identity in under 2 minutes.

## Preconditions

1. Stack is started by `make start` (or UI startup flow).
2. Operator has access to UI and shell on the host.
3. No parallel manual runtime switches are performed during recovery.

## 2-minute recovery procedure

1. Open `/inspector/model-introspection`.
2. Click `Odśwież snapshot` and confirm drift is present (`drift present` / `R0_MODEL_DRIFT`).
3. Perform exactly one controlled model switch from UI (runtime/model selector).
4. Wait for switch completion and click `Odśwież snapshot` again.
5. Verify:
   - `drift clean`,
   - one active runtime/model label across summary/results/runtime context.
6. Run analysis again with the same prompt.

Expected result:

1. analysis is not skipped,
2. `MODEL_DRIFT_DETECTED` is absent,
3. operator conclusion no longer shows `R0_MODEL_DRIFT`.

## Hard checks (if still failing)

1. `make status` must show one active stack/runtime.
2. Runtime endpoint must be healthy (`/health` on active runtime host:port).
3. `GET /api/v1/system/llm-runtime/active` must return one coherent identity.

If identity is still split:

1. stop ad-hoc runtime processes started outside `make start`/UI,
2. perform one controlled switch from UI again,
3. refresh snapshot and re-run analysis.

## Do / Don't

Do:

1. use one source of truth for switching (`make start` or UI),
2. verify drift state before analysis runs.

Don't:

1. edit `.env*` to force runtime state during active session,
2. run parallel manual runtime restarts during diagnosis,
3. rely on bootstrap values as live runtime truth.
