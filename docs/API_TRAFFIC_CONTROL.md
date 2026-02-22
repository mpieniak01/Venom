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

## Integration contract for new modules

For every new connector/module that calls external APIs:

1. Use `TrafficControlledHttpClient` from:
   - `venom_core.infrastructure.traffic_control.http_client`
2. Set a stable provider key (for example `openai`, `github`, `my_module_api`).
3. Do not call external APIs with raw `httpx/aiohttp/requests` in core paths.
4. Keep healthchecks/benchmarks/localhost probes separate from external outbound traffic.

### Required patterns

Synchronous:
```python
from venom_core.infrastructure.traffic_control.http_client import TrafficControlledHttpClient

with TrafficControlledHttpClient(provider="my_module_api", timeout=20.0) as client:
    resp = client.get("https://api.example.com/v1/items")
    data = resp.json()
```

Asynchronous:
```python
from venom_core.infrastructure.traffic_control.http_client import TrafficControlledHttpClient

async with TrafficControlledHttpClient(provider="my_module_api", timeout=20.0) as client:
    resp = await client.aget("https://api.example.com/v1/items")
    data = resp.json()
```

Streaming (SSE/chunked):
```python
from venom_core.infrastructure.traffic_control.http_client import TrafficControlledHttpClient

async with TrafficControlledHttpClient(provider="my_module_api", timeout=None) as client:
    async with client.astream("POST", "https://api.example.com/v1/stream", json=payload) as resp:
        async for line in resp.aiter_lines():
            ...
```

## Performance verification (2026-02-22)

Quick runtime benchmark (`TrafficController.check_outbound_request + record_outbound_response`):
- Single-thread: about `313k ops/s` (`200k` ops in `0.64s`).
- 8 threads, same scope: about `22k ops/s`.
- 8 threads, distinct scopes: about `11k ops/s`.

Interpretation:
1. The central point is not a bottleneck for normal Venom runtime flow (async, IO-bound workloads, practical RPS far below these values).
2. Under synthetic heavy multi-thread contention, lock pressure is visible by design (consistent state/counters/circuit tracking).
3. This trade-off is accepted for correctness and unified guardrails in core.
