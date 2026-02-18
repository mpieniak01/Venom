# Rider-Pi Lifecycle Runbook

## Scope
This runbook defines minimum operational lifecycle for Rider-Pi bridge used by Venom IoT integration.

## Health Check
1. Call `GET /api/v1/iot/status`.
2. Expect `connected=true`.
3. For SSH mode validate optional telemetry (`cpu_temp`, `memory`, `disk`).
4. If telemetry is empty but `connected=true`, treat as degraded and continue with reconnect procedure.

## Reconnect Procedure
1. Call `POST /api/v1/iot/reconnect`.
2. If `connected=true`, verify `GET /api/v1/iot/status` again.
3. If `connected=false` after retries:
   - validate network path to Rider-Pi host,
   - verify SSH daemon/pigpio service on Rider-Pi,
   - rotate credentials/keys if auth changed.

## Safety Rails
1. Prefer read-only commands for diagnostics.
2. Use emergency procedures (`reboot`, `shutdown`, `reset_gpio`) only with explicit operator approval.
3. Do not run shell commands from user input without allow-listing.
4. Store incident notes in ops log with timestamp and operator id.

## Monitoring Minimum
1. Poll `GET /api/v1/iot/status` periodically.
2. Alert if disconnected for more than 3 consecutive checks.
3. Alert if reconnect endpoint fails in all attempts.
