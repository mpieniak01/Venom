# ZADANIE 055: Rozdzielenie backendu FastAPI i frontu Next.js

## Cel
Zapewnić, że FastAPI (backend) i Next.js (frontend) działają jako dwa niezależne procesy/artefakty. FastAPI odpowiada wyłącznie za API/SSE/WS, a Next.js serwuje UI (SSR/CSR).

## Zakres
1. **Architektura uruchomieniowa**
   - FastAPI startuje przez `uvicorn` pomijając stare Jinja + statyczne pliki.
   - Next.js budowany w trybie `standalone` i uruchamiany `next start` (prod) lub `next dev` (dev).
   - Reverse proxy (np. nginx/docker-compose) przekierowuje `/api` i `/ws` do FastAPI, a resztę do Next.js.
2. **Makefile / skrypty**
   - Dodać cele `make start-dev` (dev: uvicorn + next dev) oraz `make start-prod` (uvicorn + next start).
   - `make stop` oraz `make status` obsługują oba procesy (oddzielne PID-y).
3. **Konfiguracja FastAPI**
   - Wprowadzić flagę konfiguracyjną `SERVE_LEGACY_UI`. Domyślnie `False` – brak montowania `templates/static`.
   - Zapewnić kompatybilność całego API (CORS, SSE, WebSocket) przy pracy za reverse proxy.
4. **Konfiguracja Next.js**
   - Utrzymać rewrites `/api/:path*` -> `API_PROXY_TARGET`.
   - Dodać opis środowisk (`NEXT_PUBLIC_API_BASE`) w `docs/DEPLOYMENT_NEXT.md`.
5. **Testy / CI**
   - Backend: `pytest`. Frontend: `npm run lint`, `npm run build`, `npx playwright test`.
   - Scenariusz Playwrighta odpala gotowy build (`next start`).

## Kroki do wykonania
1. [x] Odłączyć FastAPI od legacy UI (flagą konfiguracyjną + docelowo usunięciem szablonów). _(17.12: `SERVE_LEGACY_UI` w `venom_core.config` kontroluje montowanie starego cockpit/strategy. Domyślnie `True` (fallback), w trybie produkcyjnym ustaw `False`, aby FastAPI służyło tylko API.)_
2. [ ] Przygotować Makefile z targetami dev/prod + obsługa PID.
3. [ ] Opisać w dokumentacji (deployment) jak uruchomić oba procesy, wymagane zmienne środowiskowe i porty.
4. [ ] Dostosować CI/CD do budowy i uruchamiania Next.js w trybie standalone.
5. [ ] Zweryfikować logi / monitoring – osobne health-checki dla backendu i frontu.
