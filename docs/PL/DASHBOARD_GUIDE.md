# Venom Dashboard – Instrukcja Uruchomienia

Dokument opisuje dashboard Next.js (`web-next`).

Szczegółowe źródła danych, testy i zasady SCC znajdziesz również w `docs/PL/FRONTEND_NEXT_GUIDE.md`.

---

## 1. web-next (Next.js 16)

### 1.1 Wymagania
- Node.js 20+
- Działający backend FastAPI (`uvicorn main:app …`) – standardowo na porcie 8000
- Środowisko `.env` w katalogu głównym (backend) + opcjonalne zmienne frontowe (`NEXT_PUBLIC_*`)

### 1.2 Instalacja i uruchomienie

```bash
npm --prefix web-next install          # jednorazowo
npm --prefix web-next run dev          # http://localhost:3000 (proxy do API)
npm --prefix web-next run dev:turbo    # opcjonalny tryb Turbopack
```

Presety stacku (z roota repo):

```bash
make start   # pełny stack dev: backend + web-next (webpack) + aktywny runtime LLM
make start2  # pełny stack dev: backend + web-next (turbopack) + aktywny runtime LLM
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
| Smoke regresyjny Turbopack          | `npm --prefix web-next run test:dev:turbo:smoke:clean` |
| Playwright smoke (15 testów)        | `npm --prefix web-next run test:e2e`                  |
| Lint + typy                         | `npm --prefix web-next run lint`                      |
| Walidacja tłumaczeń                 | `npm --prefix web-next run lint:locales`              |

### 1.4 Tryby uruchamiania stacku (zalecane)
Korzystaj z wrapperów `Makefile` z roota repo (`/home/ubuntu/venom`), żeby spójnie uruchamiać backend/frontend/runtime.

```bash
make start                    # pełny stack (backend + frontend + aktywny runtime LLM)
make start2                   # pełny stack (backend + frontend na turbopack + aktywny runtime LLM)
make stop                     # zatrzymanie pełnego stacku
make status                   # status procesów/runtime
```

Tryby lekkie/celowane:

```bash
make api-dev                  # tylko backend (uvicorn --reload)
make web-dev                  # tylko frontend (webpack, stabilny default)
make web-dev-turbo            # tylko frontend (turbopack, opt-in)
make web-dev-turbo-debug      # turbopack z rozszerzonym logowaniem
make test-web-turbo-smoke-clean # smoke regresyjny dla dev:turbo
```

Zasada operacyjna:
1. Utrzymuj jedną aktywną instancję `next dev`, aby uniknąć konfliktu `.next/dev/lock`.
2. `web-dev` (webpack) traktuj jako tryb domyślny, a `web-dev-turbo` jako walidowany fast-path.

### 1.5 Struktura
```
web-next/
├── app/ (Cockpit, Brain, Inspector, Strategy – server components)
├── components/ (layout, UI, overlaye)
├── hooks/ (use-api.ts, use-telemetry.ts)
├── lib/ (i18n, formatery, api-client, app-meta)
├── scripts/ (generate-meta.mjs, prepare-standalone.mjs)
└── tests/ (Playwright smoke)
```

### 1.6 Uwagi
- Interfejs korzysta z `useTranslation` (PL/EN/DE) i SCC – komponenty klientowe posiadają `"use client"`.
- Aktualizacje w czasie rzeczywistym realizuje `usePolling` (fetch + odświeżanie) oraz WebSocket (`useTelemetryFeed`).
- Dolna belka statusu i overlaye TopBaru mają `data-testid`, co umożliwia stabilne testy E2E.
- Build generuje `public/meta.json` (wersja + commit) – wykorzystywany do weryfikacji środowiska w UI.
- Inspector dostępny jest w `web-next` (`/inspector`) i renderuje przepływy Mermaid z zoom/pan.

### 1.7 Cockpit – panel operacyjny
Najważniejsze bloki w Cockpicie (web-next):
- **Serwery LLM** – wybór runtime (Ollama/vLLM/ONNX), lista modeli dla wybranego runtime, aktywacja modelu.
- **Slash commands** – `/gpt`, `/gem`, `/<tool>` z autouzupełnianiem, wymuszenie routingu i badge „Forced”.
- **Język odpowiedzi** – ustawienie PL/EN/DE w UI jest przekazywane do backendu i służy do tłumaczenia wyniku.
- **Feedback użytkownika** – kciuk w górę/dół przy odpowiedzi, logi feedbacku i metryki jakości (👍/👎).
- **Hidden prompts** – agregacja, filtracja i aktywacja zatwierdzonych odpowiedzi.
- **Logi nauki** – podgląd zapisów LLM-only z `data/learning/requests.jsonl`.

### 1.8 Szybki start tooli
- Zobacz [TOOLS_USAGE_GUIDE.md](TOOLS_USAGE_GUIDE.md), gdzie jest aktualna mapa slash tooli, zasady routingu `forced_tool` i wymagane zależności web-search w `.venv`.

---

## Licencja

Część projektu Venom Meta-Intelligence
