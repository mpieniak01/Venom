# Global API Traffic Control (Anti-Spam / Anti-Ban)

## Goal
Venom uses a global traffic-control layer to protect:
1. External API providers from accidental request storms and bans.
2. Internal backend API from frontend/client bursts and loops.

This mechanism is part of core, so it applies uniformly to current and future modules.

## Control model

### 1. Outbound (external APIs)
- Policy scope: `provider` + `HTTP method` (for example `github:get`, `openai:post`).
- Rate limiting: token-bucket per scope.
- Retry: exponential backoff + jitter with max attempts.
- Circuit breaker: open/half-open/closed per scope.
- Global anti-loop guard:
  - hard cap requests/minute,
  - degraded mode cooldown when caps/failures are exceeded.

### 2. Inbound (web-next -> venom_core)
- Policy scope starts from endpoint group (`chat`, `memory`, `workflow`, ...).
- Additional keying to avoid global blocking:
  - per actor (`X-Actor`/`X-User-Id`),
  - then per session (`X-Session-Id`),
  - then per client IP fallback.
- Limit responses return `429` with `Retry-After`.

## Observability
- Read-only endpoints:
  - `GET /api/v1/traffic-control/status`
  - `GET /api/v1/traffic-control/metrics/{scope}`
- Exposed metrics include:
  - `2xx/4xx/5xx/429`,
  - retries,
  - circuit state,
  - active scopes.

## Logging policy (privacy-first)
- Detailed traffic-control logging is opt-in:
  - `ENABLE_TRAFFIC_CONTROL_LOGGING=false` by default.
- Optional log path:
  - `TRAFFIC_CONTROL_LOG_DIR=/tmp/venom/traffic-control`
- Rotation/retention model:
  - time rotation every 24h,
  - retention window 3 days,
  - size budget guard (`log_max_size_mb` in config).

## Configuration quick start
Use `.env`:

```env
ENABLE_TRAFFIC_CONTROL_LOGGING=false
TRAFFIC_CONTROL_LOG_DIR=/tmp/venom/traffic-control
```

## Relation to modules
- Modules (for example Brand Studio) do not implement independent anti-ban engines in core paths.
- They inherit the same global guardrails when using core HTTP/API paths.
- Module-level connector specifics can exist, but global protection remains centralized in Venom core.
