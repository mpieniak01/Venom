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
