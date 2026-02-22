# Globalna kontrola ruchu API (anti-spam / anti-ban)

## Cel
Venom używa globalnej warstwy kontroli ruchu, aby chronić:
1. Zewnętrzne API przed przypadkowym zalaniem i banami.
2. Wewnętrzne API backendu przed burstami i pętlami z frontendu/klienta.

To mechanizm core, więc działa spójnie dla obecnych i przyszłych modułów.

## Model kontroli

### 1. Outbound (zewnętrzne API)
- Zakres polityki: `provider` + `metoda HTTP` (np. `github:get`, `openai:post`).
- Rate limiting: token-bucket per scope.
- Retry: exponential backoff + jitter z limitem prób.
- Circuit breaker: open/half-open/closed per scope.
- Globalny anti-loop guard:
  - twardy limit requestów/min,
  - tryb degraded z cooldownem po przekroczeniu limitów/błędów.

### 2. Inbound (web-next -> venom_core)
- Zakres polityki zaczyna się od grupy endpointów (`chat`, `memory`, `workflow`, ...).
- Dodatkowe kluczowanie, żeby nie blokować całości:
  - per actor (`X-Actor`/`X-User-Id`),
  - potem per sesja (`X-Session-Id`),
  - potem fallback per IP klienta.
- Przy limicie zwracane jest `429` z nagłówkiem `Retry-After`.

## Obserwowalność
- Endpointy read-only:
  - `GET /api/v1/traffic-control/status`
  - `GET /api/v1/traffic-control/metrics/{scope}`
- Udostępniane metryki:
  - `2xx/4xx/5xx/429`,
  - retry,
  - stan circuit breaker,
  - aktywne scope.

## Polityka logowania (privacy-first)
- Szczegółowe logowanie traffic-control jest opt-in:
  - domyślnie `ENABLE_TRAFFIC_CONTROL_LOGGING=false`.
- Opcjonalna ścieżka logów:
  - `TRAFFIC_CONTROL_LOG_DIR=/tmp/venom/traffic-control`
- Model rotacji/retencji:
  - rotacja czasowa co 24h,
  - retencja 3 dni,
  - dodatkowy guard budżetu rozmiaru (`log_max_size_mb` w config).

## Szybki start konfiguracji
W `.env`:

```env
ENABLE_TRAFFIC_CONTROL_LOGGING=false
TRAFFIC_CONTROL_LOG_DIR=/tmp/venom/traffic-control
```

## Relacja z modułami
- Moduły (np. Brand Studio) nie implementują osobnego silnika anti-ban w ścieżkach core.
- Dziedziczą globalne guardraile podczas użycia ścieżek HTTP/API core.
- Modułowe szczegóły connectorów mogą istnieć, ale ochrona globalna pozostaje scentralizowana w Venom core.

## Kontrakt integracyjny dla nowych modułów

Dla każdego nowego connectora/modułu, który wywołuje zewnętrzne API:

1. Używaj `TrafficControlledHttpClient` z:
   - `venom_core.infrastructure.traffic_control.http_client`
2. Ustaw stabilny klucz providera (np. `openai`, `github`, `my_module_api`).
3. Nie wywołuj zewnętrznych API bezpośrednio przez `httpx/aiohttp/requests` w ścieżkach core.
4. Healthchecki/benchmarki/probe localhost trzymaj poza ścieżką zewnętrznego outbound.

### Wymagane wzorce

Synchronicznie:
```python
from venom_core.infrastructure.traffic_control.http_client import TrafficControlledHttpClient

with TrafficControlledHttpClient(provider="my_module_api", timeout=20.0) as client:
    resp = client.get("https://api.example.com/v1/items")
    data = resp.json()
```

Asynchronicznie:
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

## Weryfikacja wydajności (2026-02-22)

Szybki benchmark runtime (`TrafficController.check_outbound_request + record_outbound_response`):
- Single-thread: około `313k ops/s` (`200k` operacji w `0.64s`).
- 8 wątków, ten sam scope: około `22k ops/s`.
- 8 wątków, różne scope: około `11k ops/s`.

Interpretacja:
1. Centralny punkt nie jest wąskim gardłem dla normalnego przepływu Venom (async, IO-bound, praktyczne RPS dużo niższe niż powyżej).
2. Przy sztucznym, mocno wielowątkowym obciążeniu kontencja locków jest widoczna zgodnie z założeniem (spójny stan/liczniki/circuit tracking).
3. Ten kompromis jest akceptowany na rzecz poprawności i jednolitych guardraili w core.
