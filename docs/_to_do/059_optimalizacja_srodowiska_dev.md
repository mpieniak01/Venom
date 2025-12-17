# ZADANIE 059: Optymalizacja środowiska developerskiego (PC single user)

## Kontekst
- Środowisko uruchamiane na pojedynczym PC (bez GPU klasy serwerowej, brak wielu operatorów).
- Obecne procesy:
  - `uvicorn --reload` (~70% CPU w piku, ~110 MB RSS; dodatkowy worker spawn).
  - `next dev` (`next-server` + `npm run dev`) ~6-7% CPU, ~1.3 GB RAM.
  - `vllm serve gemma-2b-it` ~13% RAM (1.3-1.4 GB) + proces `VLLM::EngineCore`.
  - VS Code Server + rozszerzenia (extension host, file watcher) ~0.6-2.5% CPU, ~700 MB RAM.
  - Inne drobne procesy CLI (htop, shell, helpery).
- RAM: 15 GiB total, 5.7 GiB used, 8.8 GiB cache (9.8 GiB available). Load avg ~1.
- Scenariusz: tylko jeden użytkownik → chcemy minimalny footprint, brak równoległych sesji.

## Cele
1. Zmniejszyć stale uruchomione procesy do niezbędnych komponentów.
2. Ograniczyć tryby „dev” z autoreload, jeśli nie są potrzebne.
3. Kontrolować start/stop ciężkich usług (vLLM, Next.js) na żądanie.

## Proponowane działania

### 1. Backend FastAPI
- **Zadanie:** dodać tryb `make api` / `scripts/run_api.sh` bez `--reload` (worker single-process).
- **Uzasadnienie:** `uvicorn --reload` spawnuje watcher i dodatkowy proces (multiprocessing). Na PC operator ma VS Code i CLI – autoreload można zostawić jako opcję.
- **Implementacja:**
  - W `Makefile` oraz README dopisać `make api-dev` (reload) i `make api` (bez reload).
  - W dokumentacji opis, kiedy używać którego trybu.

### 2. Frontend Next.js
- **Zadanie:** umożliwić łatwe wyłączenie dev servera. Dodać alias `npm run web` (prod build + `next start`) oraz instrukcję, że `next dev` uruchamiamy tylko podczas pracy nad UI.
- **Wsparcie:** dodać kontrolkę w README/Task doc, by developer nie trzymał `next dev` non-stop.
- **Opcjonalnie:** dodać `scripts/run_web.sh` (uruchamia `next start` po `next build`).

### 3. vLLM Runtime
- **Zadanie:** ustandaryzować start/stop przez `make vllm-start` / `make vllm-stop` (wykorzystując istniejące `scripts/llm/vllm_service.sh`).
- **Automation:** w panelu LLM UI dodać tooltip: „Startuj vLLM tylko jeśli pracujesz z lokalnym modelem”.
- **Doc:** dodać w README sekcję „Lekki profil pracy” – startuj vLLM tylko przy zadaniach LLM.

### 4. VS Code Server / narzędzia
- **Uwaga:** w repo brak integracji, ale w dokumentacji można wskazać, aby zamykać zdalne VS Code gdy pracujemy w CLI.
- **Dodatki:** skrót w README: `kill -9 $(pgrep -f vscode-server)` / `code tunnel exit`.

### 5. Monitor zasobów
- **Zadanie:** przygotować prosty skrypt `scripts/monitor/resources.sh` (wyświetla top procesów, użycie RAM/Swap).
- **Cel:** szybka diagnostyka w przyszłości.

## Plan PR
1. **Dokumentacja** (README, docs/TREE): opis trybu lekkiego, tableka dostępnych komend (`make api`, `make web`, `make vllm-start`). Dodać sekcję „Profil Light (PC)”.
2. **Makefile / scripts**:
   - `make api` → `uvicorn ...` bez `--reload`.
   - `make api-dev` pozostaje (reload).
   - `make web` → `npm --prefix web-next run build && npm --prefix web-next run start`.
   - `make web-dev` → `npm --prefix web-next run dev` (dotychczasowe zachowanie).
   - `make vllm-start/stop/restart` → wrappery na `scripts/llm/vllm_service.sh`.
3. **UI hint** (opcjonalny commit, jeśli w tym PR): w panelu „Serwery LLM” dopisać tooltip, że start OLLAMA/vLLM tylko gdy potrzebne.
4. **Resource monitor script**: `scripts/diagnostics/system_snapshot.sh` (zbiera `ps`, `free`, `uptime` i loguje do `logs/diag-*.txt`).
5. **README check-list**: w sekcji „Uruchomienie lokalne” dodać tabelę z combos (Full stack vs Light vs Only API).

## Kryteria akceptacji
- Developer może uruchomić jedynie API bez autoreload (komenda w README).
- W README jest opisany profil minimalny i informacja, które procesy można wyłączyć.
- Panel LLM informuje o kosztach uruchomienia runtime.
- Skrypt monitoringu dostępny i opisany.

## Dalsze kroki (po PR)
- Rozważyć automatyczny watchdog, który zatrzyma vLLM po X minutach bez requestów.
- Dodać w UI przełącznik „Profil oszczędny” aktywujący/wyłączający serwisy.
