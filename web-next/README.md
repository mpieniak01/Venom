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
- `app/` – strony: Cockpit `/`, Inspector `/inspector`, Brain `/brain`, Strategy `/strategy`
- `components/ui` – panele, karty, badge
- `lib/env.ts` – źródło adresów API/WS (env + fallback)
- `lib/api-client.ts` – fetch z obsługą błędów
- `lib/ws-client.ts` – klient WebSocket z autoreconnect
- `next.config.ts` – proxy do FastAPI (dev), output `standalone`

## Stack UI
- Tailwind CSS 4 + autorski `tailwind.config.ts` (ciemny motyw, glassmorphism)
- shadcn/ui (Sheet, Accordion) na bazie Radix UI
- `framer-motion` (animacje chatu), `@tremor/react` (karty KPI)
- `react-zoom-pan-pinch` w Inspectorze (nawigacja po Mermaid)
- `lucide-react` (ikony), `tailwindcss-animate`

## Funkcje dostępne w Cockpit (Next)
- Telemetria WS (`/ws/events`) z auto-reconnect
- Zadania: wysyłanie / listowanie (`/api/v1/tasks`), Lab Mode toggle
- Kolejka: status + akcje pause/resume/purge/emergency stop (`/api/v1/queue/*`)
- Modele: lista / switch / instalacja (`/api/v1/models*`)
- Git: status + sync/undo (`/api/v1/git/*`)
- Cost Mode & Autonomy (`/api/v1/system/cost-mode`, `/api/v1/system/autonomy`)
- Tokenomics (`/api/v1/metrics/tokens`), usługi systemowe (`/api/v1/system/services`)
- Historia: ostatnie requesty + detail (`/api/v1/history/requests`)
- Flow: timeline mermaid dla wybranego requestu (kroki z `/history/requests/{id}`)
- Brain: graf wiedzy z Cytoscape (`/api/v1/knowledge/graph`), filtrowanie węzłów, podgląd detali
- Chart.js: trend tokenów (ostatnie próbki z `/metrics/tokens`)
- Lessons & Graph scan: `/api/v1/lessons`, `/api/v1/graph/scan`
- Flow: filtrowanie/kopiowanie kroków timeline, eksport JSON
- Brain: filtry lekcji po tagach, relacje węzłów, analiza plików (`/graph/file`, `/graph/impact`)
- War Room: dane roadmapy z `/api/roadmap` + raport statusu/kampania, renderowanie Markdown wizji/raportów

## Kolejne kroki
- Dynamic import bibliotek (Chart.js, mermaid, Cytoscape) w trybie CSR.
- Testy E2E (Playwright) dla kluczowych ścieżek Cockpitu.

## Testy E2E (Playwright)
1. Uruchom backend FastAPI (port 8000) i frontend Next.js (`npm run dev`). Next nasłuchuje na 3000, ale przy zajętym porcie automatycznie wybierze kolejny (np. 3001 — sprawdź komunikat w terminalu).
2. W innym terminalu:
   ```bash
   cd web-next
   BASE_URL=http://127.0.0.1:3000 npm run test:e2e -- --reporter=list
   ```
   Dopasuj `BASE_URL` do faktycznego portu z pkt 1 (np. `http://localhost:3000` gdy 3000 jest wolny).
3. Raporty i materiały z nieudanych testów znajdują się w `web-next/test-results/`.
