# Venom Dashboard – Instrukcja Uruchomienia

Dokument opisuje dwa frontendy:
- **Nowy Next.js (`web-next`)** – domyślny interfejs z App Routerem i Playwright smoke.
- **Legacy (`web/` + FastAPI templates)** – zachowany dla kompatybilności (ostatnie wdrożenia przed migracją).

Szczegłowe źródła danych, testy i zasady SCC znajdziesz również w `docs/FRONTEND_NEXT_GUIDE.md`.

---

## 1. web-next (Next.js 15)

### 1.1 Wymagania
- Node.js 20+
- Działający backend FastAPI (`uvicorn main:app …`) – standardowo na porcie 8000
- Środowisko `.env` w katalogu głównym (backend) + opcjonalne zmienne frontowe (`NEXT_PUBLIC_*`)

### 1.2 Instalacja i uruchomienie

```bash
npm --prefix web-next install          # jednorazowo
npm --prefix web-next run dev          # http://localhost:3000 (proxy do API)
```

Najważniejsze zmienne środowiskowe frontu:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000          # gdy nie chcemy korzystać z wbudowanego proxy
NEXT_PUBLIC_WS_BASE=ws://localhost:8000/ws/events   # kanał telemetryczny
API_PROXY_TARGET=http://localhost:8000              # cel rewritera Next (dev)
```

### 1.3 Skrypty

| Cel                                 | Komenda                                              |
|-------------------------------------|-------------------------------------------------------|
| Build produkcyjny                   | `npm --prefix web-next run build`                     |
| Serwowanie buildu (`next start`)    | `npm --prefix web-next run start`                     |
| Playwright smoke (15 testów)        | `npm --prefix web-next run test:e2e`                  |
| Lint + typy                         | `npm --prefix web-next run lint`                      |
| Walidacja tłumaczeń                 | `npm --prefix web-next run lint:locales`              |

### 1.4 Struktura
```
web-next/
├── app/ (Cockpit, Brain, Inspector, Strategy – server components)
├── components/ (layout, UI, overlaye)
├── hooks/ (use-api.ts, use-telemetry.ts)
├── lib/ (i18n, formatery, api-client, app-meta)
├── scripts/ (generate-meta.mjs, prepare-standalone.mjs)
└── tests/ (Playwright smoke)
```

### 1.5 Różnice względem legacy
- Interfejs korzysta z `useTranslation` (PL/EN/DE) i SCC – komponenty klientowe posiadają `"use client"`.
- Aktualizacje w czasie rzeczywistym realizuje `usePolling` (fetch + odświeżanie) oraz WebSocket (`useTelemetryFeed`).
- Dolna belka statusu i overlaye TopBaru mają `data-testid`, co umożliwia stabilne testy E2E.
- Build generuje `public/meta.json` (wersja + commit) – wykorzystywany do weryfikacji środowiska w UI.

---

## 2. Legacy dashboard (`web/`)

Venom Cockpit to dashboard do monitorowania i kontrolowania systemu Venom w czasie rzeczywistym.
Dashboard oferuje:
- **Live Feed**: Strumień zdarzeń systemowych w czasie rzeczywistym przez WebSocket
- **Chat Console**: Interfejs do wysyłania zadań bezpośrednio z przeglądarki
- **Task Monitor**: Lista aktywnych zadań z ich statusem
- **Metrics**: Metryki wydajności systemu (liczba zadań, success rate, uptime)

## Wymagania

- Python 3.10+
- Zainstalowane zależności z `requirements.txt`
- Port 8000 dostępny dla serwera

## Uruchomienie

### 2.1 Instalacja zależności

```bash
pip install -r requirements.txt
```

### 2.2 Konfiguracja (opcjonalna)

Utwórz plik `.env` w katalogu głównym projektu:

```env
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=phi3:latest
```

### 2.3 Uruchomienie serwera

```bash
cd venom_core
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.4 Otwarcie dashboardu

Otwórz przeglądarkę i przejdź do:
```
http://localhost:8000
```

## Załącznik – Struktura (legacy)

```
venom_core/
├── api/
│   ├── __init__.py
│   └── stream.py              # WebSocket server i EventBroadcaster
├── core/
│   ├── metrics.py             # System metryk
│   ├── orchestrator.py        # Zmodyfikowany orchestrator z broadcasting
│   └── dispatcher.py          # Dispatcher z event broadcasting
├── agents/
│   └── architect.py           # Agent architekta z event broadcasting
└── main.py                    # FastAPI app z WebSocket i static files

web/
├── templates/
│   └── index.html             # Główny template dashboardu
└── static/
    ├── css/
    │   └── app.css            # Style dashboardu
    └── js/
        └── app.js             # JavaScript: WebSocket client, UI logic
```

## API Endpoints

### REST API

- `GET /` - Dashboard UI
- `GET /healthz` - Health check
- `POST /api/v1/tasks` - Utworzenie nowego zadania
- `GET /api/v1/tasks` - Lista wszystkich zadań
- `GET /api/v1/tasks/{task_id}` - Szczegóły zadania
- `GET /api/v1/metrics` - Metryki systemowe

### WebSocket

- `WS /ws/events` - WebSocket endpoint dla streamingu zdarzeń

## Typy Zdarzeń WebSocket

Dashboard odbiera następujące typy zdarzeń:

- `TASK_CREATED` - Utworzono nowe zadanie
- `TASK_STARTED` - Rozpoczęto przetwarzanie zadania
- `TASK_COMPLETED` - Zadanie ukończone pomyślnie
- `TASK_FAILED` - Zadanie nie powiodło się
- `PLAN_CREATED` - Architekt utworzył plan
- `PLAN_STEP_STARTED` - Rozpoczęto krok planu
- `PLAN_STEP_COMPLETED` - Ukończono krok planu
- `AGENT_ACTION` - Agent wykonuje akcję
- `AGENT_THOUGHT` - "Myśl" agenta
- `SYSTEM_LOG` - Log systemowy

## Testowanie (legacy)

### Test manualny

1. Uruchom serwer zgodnie z instrukcją powyżej
2. Otwórz dashboard w przeglądarce
3. Sprawdź status połączenia (zielona kropka w prawym górnym rogu)
4. Wpisz przykładowe zadanie, np.:
   ```
   Zrób research o Python 3.12
   ```
5. Obserwuj:
   - Live Feed: Logi pojawiające się w czasie rzeczywistym
   - Task Monitor: Nowe zadanie z jego statusem
   - Chat Console: Odpowiedź od agenta
   - Metrics: Aktualizacja liczników

### Test automatyczny

```bash
pytest tests/test_dashboard_api.py -v
```

## Troubleshooting (legacy)

### WebSocket nie łączy się

- Sprawdź czy serwer jest uruchomiony
- Sprawdź czy port 8000 nie jest zablokowany przez firewall
- Sprawdź konsolę przeglądarki (F12) dla błędów

### Dashboard nie ładuje się

- Sprawdź czy katalog `web/` istnieje i zawiera pliki
- Sprawdź logi serwera dla błędów montowania StaticFiles

### Metryki nie aktualizują się

- Sprawdź endpoint `/api/v1/metrics` ręcznie w przeglądarce
- Sprawdź czy zadania są tworzone poprawnie

## Rozwój

### Dodanie nowych typów zdarzeń

1. Dodaj typ zdarzenia do `EventType` w `venom_core/api/stream.py`
2. Wywołaj `event_broadcaster.broadcast_event()` w odpowiednim miejscu
3. Obsłuż zdarzenie w `web/static/js/app.js` w metodzie `handleWebSocketMessage()`

### Modyfikacja UI

- Edytuj `web/templates/index.html` dla struktury HTML
- Edytuj `web/static/css/app.css` dla stylów
- Edytuj `web/static/js/app.js` dla logiki JavaScript

## Licencja

Część projektu Venom Meta-Intelligence
