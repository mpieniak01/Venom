# Venom Cockpit – Next.js frontend (MVP)

Szkielet nowego frontendu Venom (Cockpit, Flow Inspector, Brain, War Room).

## Wymagania
- Node 18.19+ (rekomendacja: 20.x)
- Działający backend FastAPI Venoma (domyślnie `http://localhost:8000`)

## Instalacja
```bash
cd web-next
npm install
```

## Konfiguracja
Ustaw adres backendu i WebSocket (nie commitujemy):
```bash
# .env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000
```

W dev można użyć proxy z `next.config.ts` (`API_PROXY_TARGET` lub `NEXT_PUBLIC_API_BASE`).

## Uruchomienie
```bash
npm run dev    # http://localhost:3000
npm run build
npm run start
```

## Struktura
- `app/` – strony: Cockpit `/`, Flow `/flow`, Brain `/brain`, Strategy `/strategy`
- `components/ui` – panele, karty, badge
- `lib/env.ts` – źródło adresów API/WS (env + fallback)
- `lib/api-client.ts` – fetch z obsługą błędów
- `lib/ws-client.ts` – klient WebSocket z autoreconnect
- `next.config.ts` – proxy do FastAPI (dev), output `standalone`

## Funkcje dostępne w Cockpit (Next)
- Telemetria WS (`/ws/events`) z auto-reconnect
- Zadania: wysyłanie / listowanie (`/api/v1/tasks`), Lab Mode toggle
- Kolejka: status + akcje pause/resume/purge/emergency stop (`/api/v1/queue/*`)
- Modele: lista / switch / instalacja (`/api/v1/models*`)
- Git: status + sync/undo (`/api/v1/git/*`)
- Cost Mode & Autonomy (`/api/v1/system/cost-mode`, `/api/v1/system/autonomy`)
- Tokenomics (`/api/v1/metrics/tokens`), usługi systemowe (`/api/v1/system/services`)
- Historia: ostatnie requesty + detail (`/api/v1/history/requests`)

## Kolejne kroki
- Dynamic import bibliotek (Chart.js, mermaid, Cytoscape) w trybie CSR.
- Testy E2E (Playwright) dla kluczowych ścieżek Cockpitu.
