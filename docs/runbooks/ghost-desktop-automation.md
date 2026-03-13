# Ghost Desktop Automation Runbook

This runbook defines the operator flow for safe execution of Ghost desktop automation scenarios (PyAutoGUI + vision fallback).

## 1. Scope

Use this runbook when running manual desktop automation in preprod/lab environments:

- Ghost API execution (`/api/v1/ghost/start|status|cancel`),
- hardware-in-loop validation scenarios,
- emergency stop and triage.

## 2. Preconditions

1. Environment:
- `ENABLE_GHOST_AGENT=True`
- `ENABLE_GHOST_API=True`
- `GHOST_RUNTIME_PROFILE=desktop_safe` (default for first run)

2. Host requirements:
- desktop session available (X11/Wayland/Windows desktop),
- active foreground window control,
- operator has emergency-stop access.

3. Governance:
- autonomy level allows desktop input mutations,
- audit stream is enabled.

## 3. Safe start checklist

1. Confirm no sensitive applications are focused.
2. Close unrelated windows and notifications.
3. Move mouse to neutral area (not screen corner `(0,0)`).
4. Open audit view and verify incoming Ghost events:
- `source=api.ghost`,
- `source=core.ghost`.
5. Start with `desktop_safe` profile.

## 4. Calibration

1. Verify display scale/DPI and resolution are stable.
2. Run one dry operator scenario with non-destructive target (local harness window).
3. Confirm:
- click coordinates are inside expected target region,
- keyboard focus lands on expected input element,
- fail-closed policy blocks unsafe fallback in `desktop_safe`.

## 5. Hardware-in-loop scenarios

Run manual HIL tests:

```bash
VENOM_GHOST_HIL=1 .venv/bin/pytest tests/test_ghost_agent_hil.py -v
```

Critical scenarios:

1. `desktop_safe` blocks fallback click when visual match is missing.
2. `desktop_power` allows fallback click, text entry, and submit via keyboard.

Expected result: test file passes with 2 scenarios.

## 6. Runtime execution via API

1. Start task:
- `POST /api/v1/ghost/start`
2. Poll runtime/task:
- `GET /api/v1/ghost/status`
3. Cancel if required:
- `POST /api/v1/ghost/cancel`

Operational rules:

1. Treat `status=failed` as hard stop and triage case.
2. For critical actions, keep `desktop_safe` unless explicitly approved.
3. Do not use `desktop_power` in production-like environments without explicit change record.

## 7. Emergency stop

Immediate stop options:

1. Call `POST /api/v1/ghost/cancel`.
2. Trigger physical fail-safe by moving cursor to corner `(0,0)`.

After stop:

1. Capture latest audit entries (`api.ghost`, `core.ghost`).
2. Record task id, profile, failure context.
3. Verify no lingering active task in `/ghost/status`.

## 8. Triage checklist

1. Identify failure phase:
- vision locate,
- input click/type/hotkey,
- verification.
2. Validate policy/autonomy gates and actor context.
3. Compare runtime profile (`desktop_safe` vs `desktop_power`) with expected behavior.
4. Attach evidence:
- audit entries,
- screenshots/video if available,
- HIL test output.

## 9. Closure criteria

1. HIL scenarios passed on target desktop setup.
2. API start/status/cancel path validated.
3. Emergency stop validated.
4. Audit evidence attached to change record.
