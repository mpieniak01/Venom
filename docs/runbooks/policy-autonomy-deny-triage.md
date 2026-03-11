# Policy/Autonomy Deny Triage

This runbook defines a deterministic triage flow for blocked or degraded operations enforced by backend policy/autonomy gates.

## 1. Scope

Use this runbook when API/UI shows a deny/degraded response containing:

- `decision` (`block` or `degraded_allow`)
- `reason_code`
- `user_message`
- `technical_context`

Applies to:

- Route-level deny (`api.permission`, `policy.blocked.route`, `autonomy.blocked`)
- Orchestrator/task-pipeline deny (`core.policy.*`, `core.autonomy.*`)

## 2. Quick classification

1. Read `decision`.
2. Read `reason_code`.
3. Read `technical_context.operation` and `technical_context.enforcement_mode`.

Interpretation:

- `decision=block`: operation denied by policy/autonomy. For autonomy hard-mode denies, treat as terminal (`technical_context.terminal=true`, `retryable=false`).
- `decision=degraded_allow`: operation was allowed in soft mode; treat as policy drift signal.
- Route-level `PERMISSION_DENIED` can be retryable after fixing preconditions (localhost/admin header/token).

## 3. Audit stream checks

Inspect latest audit entries for the affected session/task:

1. `source`
2. `action`
3. `status`
4. `details.reason_code`
5. `details.technical_context`

Expected patterns:

- Policy route deny: `source=api.permission`, `action=policy.blocked.route`, `status=blocked`
- Autonomy hard deny: `source=core.autonomy` or `api.permission`, `action=autonomy.blocked`, `status=blocked`
- Autonomy soft allow: `source=core.autonomy`, `action=autonomy.degraded_allow`, `status=degraded`

## 4. Reason-code to action map

1. `AUTONOMY_PERMISSION_DENIED`
- Verify current autonomy level (`/api/v1/system/autonomy`).
- Verify operation requirement (`technical_context.required_level*` if present).
- If production policy requires strict blocking: set `AUTONOMY_ENFORCEMENT_MODE=hard`.

2. `PERMISSION_DENIED`
- Validate route guard preconditions (localhost/admin header/token).
- Validate actor identity mapping (`x-authenticated-user`, `x-user`, client host).

3. `POLICY_*`
- Check policy gate settings and forced runtime/tool inputs.
- Confirm expected provider/tool matrix for given environment profile.

## 5. Soft/hard enforcement validation

Check runtime configuration:

- `AUTONOMY_ENFORCEMENT_MODE=hard` -> hard block
- `AUTONOMY_ENFORCEMENT_MODE=soft` -> degraded allow

Validation checklist:

1. Decision matches mode (`block` for hard, `degraded_allow` for soft).
2. Audit action/status matches mode.
3. `technical_context.retryable=false` for autonomy denies.
4. No retry loop for the same blocked operation.

## 6. UI contract verification

UI must only present backend contract, not enforce autonomy rules locally.

Verify:

1. UI renders `user_message`.
2. UI exposes deny/degraded status.
3. UI does not transform `decision`/`reason_code` semantics.

## 7. Incident closure checklist

1. Root cause identified (`policy`, `autonomy`, `configuration`, or `actor context`).
2. Required config change applied (if any).
3. Regression test added/updated (unit/integration/contract).
4. Audit evidence attached (action/status/reason_code/operation).
5. `make pr-fast` green for code changes.
