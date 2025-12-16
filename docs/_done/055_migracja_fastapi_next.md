# ZADANIE 055 (DONE): Migracja FastAPI ↔ Next.js

## Cel
Ustawić FastAPI (API/SSE/WS) i Next.js (`web-next`) jako dwa niezależne procesy, odłączyć stary interfejs Jinja oraz opisać jak uruchamiać nowy stos w trybie dev/prod.

## Zakres prac (17.12.2025)
1. **Flaga `SERVE_LEGACY_UI`** – backend montuje stary dashboard tylko, jeśli jawnie ustawimy `True`. Migracja produkcyjna ustawia `False`, dzięki czemu FastAPI dostarcza wyłącznie `/api`, `/ws`, `/docs`.
2. **Makefile** – nowe cele:
   - `make start` / `make start-dev` – uvicorn z `--reload` + Next dev (z `NEXT_DISABLE_TURBOPACK=1`), PID-y w `.venom.pid` / `.web-next.pid`.
   - `make start-prod` – build Next.js + `next start`, backend bez przeładowania.
   - `make stop/status/clean-ports` obsługują dwa procesy i porty 8000/3000.
3. **Dokumentacja** – `docs/DEPLOYMENT_NEXT.md` opisuje architekturę startu, zmienne środowiskowe, checklistę testową i fallback starego UI.
4. **README** – aktualizacja sekcji „Szybki start / Frontend” + opis nowych testów wydajnościowych.
5. **CI/Tryby lokalne** – opisaliśmy trzy scenariusze startu:
   - Dev (uvicorn reload + next dev),
   - Prod (uvicorn bez reload + next start),
   - Legacy fallback (FastAPI + stary `web/` na porcie 8000).

## Testy
- `make start-dev` + ręczny smoke UI (Next).
- `make start-prod` – weryfikacja, że build i `next start` działają oraz `make stop` czyści procesy.
- `npm --prefix web-next run build && npm --prefix web-next run test:e2e`.
- `pytest tests/test_tasks_stream.py` (SSE) oraz `pytest tests/perf/test_chat_pipeline.py -m performance`.

## Status
✅ Migracja ukończona. Stary panel pozostaje tylko jako opcjonalna referencja (włączany flagą). Wszystkie instrukcje wdrożeniowe znajdują się w `docs/DEPLOYMENT_NEXT.md`.
