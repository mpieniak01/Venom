# Venom v1.0 🐍

**Venom Meta-Intelligence System** - Autonomiczny system agentów AI z warstwą planowania strategicznego i ekspansją wiedzy.

## 🌟 Nowe w wersji 2.0: The Hive Mind

Venom został przekształcony z prostego wykonawcy poleceń w **autonomicznego inżyniera**, który potrafi:

### ✨ Kluczowe funkcjonalności
- 🎨 Tworzenie nowych narzędzi i autonaprawa
- 🌐 **Dostęp do Internetu** - Wyszukiwanie aktualnych informacji (ceny, wiadomości, dokumentacja)
- 🧠 **Planowanie strategiczne** - Automatyczna dekompozycja złożonych projektów na kroki
- 📚 **Synteza wiedzy** - Zbieranie i analiza dokumentacji z wielu źródeł
- 🤖 **Zarządzanie agentami** - Koordynacja wielu wyspecjalizowanych agentów
- 💾 **Pamięć długoterminowa** - Zapisywanie i wykorzystywanie zdobytej wiedzy
- 🎓 **Uczenie przez obserwację** - Nagrywanie demonstracji i automatyczne generowanie workflow (NOWOŚĆ!)
- 👍👎 **Pętla jakości** - feedback użytkownika + logi i metryki jakości odpowiedzi
- 🧠 **Hidden prompts** - zatwierdzone odpowiedzi jako skróty kontekstu
- 🧭 **Selekcja runtime LLM** - Ollama/vLLM + aktywny model sterowany z panelu

### 🎯 Przykłady użycia

```python
# 1. Wyszukiwanie aktualnych informacji
"Jaka jest aktualna cena Bitcoina?"
→ System automatycznie wyszukuje w Internecie i zwraca świeże dane

# 2. Złożone projekty z planowaniem
"Stwórz grę Snake używając PyGame"
→ System:
  1. Znajdzie dokumentację PyGame (ResearcherAgent)
  2. Stworzy strukturę gry (CoderAgent)
  3. Dodaj logikę węża (CoderAgent)
  4. Zaimplementuje scoring (CoderAgent)

# 3. Strona webowa z wieloma plikami
"Stwórz stronę HTML z zegarem cyfrowym i stylem CSS"
→ System utworzy osobno: index.html, style.css, script.js

# 4. NOWE: Uczenie przez demonstrację
"Venom, patrz jak wysyłam raport na Slacka"
→ [Użytkownik wykonuje akcje]
→ System nagrywa, analizuje i generuje workflow
→ "Zapisałem jako umiejętność 'wyslij_raport_slack'"
→ Później: "Venom, wyślij raport na Slacka" - wykonuje automatycznie!
```

## 🏗️ Architektura

### Struktura projektu
```
venom_core/
├── api/routes/          # REST API endpoints (agents, tasks, memory, nodes)
├── core/flows/          # Przepływy biznesowe i orkiestracja
├── agents/              # Wyspecjalizowani agenci AI
├── execution/           # Warstwa wykonawcza i model routing
├── perception/          # Sensory (desktop_sensor, audio)
├── memory/              # Pamięć długoterminowa (vector, graph, workflow)
└── infrastructure/      # Infrastruktura (hardware, cloud, message broker)
```

### Główne komponenty

#### 1. **Strategic Layer** (Warstwa Planowania)
- **ArchitectAgent** - Kierownik projektu, rozbija złożone zadania na kroki
- **ExecutionPlan** - Model planu wykonania ze zdefiniowanymi krokami i zależnościami

#### 2. **Knowledge Expansion** (Ekspansja Wiedzy)
- **ResearcherAgent** - Zbiera i syntetyzuje wiedzę z Internetu
- **WebSearchSkill** - Wyszukiwanie (DuckDuckGo) i scraping (trafilatura)
- **MemorySkill** - Pamięć długoterminowa (LanceDB)

#### 3. **Execution Layer** (Warstwa Wykonawcza)
- **CoderAgent** - Generuje kod z wykorzystaniem wiedzy
- **CriticAgent** - Weryfikuje jakość kodu
- **LibrarianAgent** - Zarządza plikami i strukturą projektu
- **ChatAgent** - Rozmowa i asystent
- **GhostAgent** - Automatyzacja GUI (RPA - Robotic Process Automation)
- **ApprenticeAgent** - Uczenie się workflow poprzez obserwację (NOWOŚĆ!)

#### 4. **Hybrid AI Engine** (Silnik Hybrydowy) 🧠
- **HybridModelRouter** (`venom_core/execution/model_router.py`) - Inteligentny routing między Local LLM a Cloud
- **Tryby pracy**: LOCAL (tylko lokalne), HYBRID (mix), CLOUD (głównie chmura)
- **Local First**: Prywatność i $0 kosztów operacyjnych
- **Providerzy**: Ollama/vLLM (local), Google Gemini, OpenAI
- Wrażliwe dane **NIGDY** nie trafiają do chmury

#### 5. **Visual Imitation Learning** (Uczenie przez Demonstrację) 🎓
- **DemonstrationRecorder** - Nagrywanie akcji użytkownika (mysz, klawiatura, zrzuty ekranu)
- **DemonstrationAnalyzer** - Analiza behawioralna i transformacja pikseli → semantyka
- **WorkflowStore** - Magazyn procedur z możliwością edycji
- **Integration z GhostAgent** - Wykonywanie wygenerowanych workflow

#### 6. **Orchestration** (Orkiestracja)
- **Orchestrator** - Główny koordynator systemu
- **IntentManager** - Klasyfikacja intencji (5 typów: CODE_GENERATION, RESEARCH, COMPLEX_PLANNING, KNOWLEDGE_SEARCH, GENERAL_CHAT)
- **TaskDispatcher** - Routing zadań do odpowiednich agentów

### Przepływ danych

```
User Request
    ↓
IntentManager (klasyfikacja intencji)
    ↓
Orchestrator (decyzja o przepływie)
    ↓
┌─────────────────────┬─────────────────────┬──────────────────────┐
│  Prosty kod         │  Złożony projekt    │  Wyszukiwanie        │
│  CODE_GENERATION    │  COMPLEX_PLANNING   │  RESEARCH            │
├─────────────────────┼─────────────────────┼──────────────────────┤
│  CoderAgent         │  ArchitectAgent     │  ResearcherAgent     │
│       ↓             │       ↓             │       ↓              │
│  CriticAgent        │  Create Plan        │  WebSearchSkill      │
│       ↓             │       ↓             │       ↓              │
│  Result             │  Execute Plan       │  MemorySkill         │
│                     │   (Step by step)    │       ↓              │
│                     │       ↓             │  Result              │
│                     │  Result             │                      │
└─────────────────────┴─────────────────────┴──────────────────────┘
```

## 🚀 Szybki start

> 🔎 **Nowy dashboard web-next**
> Szczegółowy opis źródeł danych dla widoków Brain/Strategy oraz checklistę testów znajdziesz w `docs/FRONTEND_NEXT_GUIDE.md`. Dokument definiuje też kryteria wejścia do kolejnego etapu prac nad UI.

## 🖥️ Frontend (Next.js – `web-next`)

Nowa warstwa prezentacji działa na Next.js 15 (App Router, React 19). Interfejs jest złożony z dwóch typów komponentów:
- **SCC (Server/Client Components)** – domyślnie tworzymy komponenty serwerowe (bez dyrektywy `"use client"`), a interaktywne fragmenty oznaczamy jako klientowe. Dzięki temu widoki Brain/Strategy i Cockpit mogą strumieniować dane bez dodatkowych fetchy.
- **Wspólny layout** (`components/layout/*`) – TopBar, Sidebar, dolna belka statusu oraz overlaye dzielą tokeny graficzne i tłumaczenia (`useTranslation`).

### Kluczowe komendy

```bash
# instalacja zależności
npm --prefix web-next install

# środowisko developerskie (http://localhost:3000)
npm --prefix web-next run dev

# build produkcyjny (generuje meta version + standalone)
npm --prefix web-next run build

# smoke E2E (Playwright, tryb prod)
npm --prefix web-next run test:e2e

# walidacja spójności tłumaczeń
npm --prefix web-next run lint:locales
```

Skrypt `predev/prebuild` uruchamia `scripts/generate-meta.mjs`, który zapisuje `public/meta.json` (wersja + commit). Wszystkie hooki HTTP korzystają z `lib/api-client.ts`; w trybie lokalnym możesz wskazać backend przez zmienne:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000/ws/events
API_PROXY_TARGET=http://localhost:8000
```

> Szczegóły (architektura katalogów, guidelines dla SCC, źródła danych widoków) opisuje `docs/FRONTEND_NEXT_GUIDE.md`.

Uwaga: Cockpit ma teraz dwa widoki — `/` (produkcyjny układ z wybranymi boxami) oraz `/chat` (referencyjna, pełna kopia wcześniejszego układu).

### Instalacja

```bash
# Klonowanie repozytorium
git clone https://github.com/mpieniak01/Venom.git
cd Venom

# Instalacja zależności
pip install -r requirements.txt

# Konfiguracja (skopiuj .env.example do .env i uzupełnij)
cp .env.example .env
```

### Wymagane zależności

```
Python 3.10+ (zalecane 3.11)
```

### Kluczowe pakiety:
- `semantic-kernel>=1.9.0` - Orkiestracja agentów
- `duckduckgo-search>=6.0` - Wyszukiwarka
- `trafilatura` - Ekstrakcja tekstu ze stron WWW
- `beautifulsoup4` - Parsowanie HTML
- `lancedb` - Baza wektorowa dla pamięci
- `fastapi` - API serwera
- `zeroconf` - mDNS service discovery dla lokalnej sieci
- `pynput` - Nagrywanie akcji użytkownika (THE_APPRENTICE)
- `google-generativeai` - Google Gemini (opcjonalne)
- `openai` / `anthropic` - Modele LLM (opcjonalne)

Pełna lista w [requirements.txt](requirements.txt)

### Konfiguracja

Stwórz plik `.env` na podstawie `.env.example`:

```bash
cp .env.example .env
```

## ⚙️ Uruchamianie (FastAPI + Next.js)

Pełna lista kroków oraz checklisty wdrożeniowej znajduje się w [`docs/DEPLOYMENT_NEXT.md`](docs/DEPLOYMENT_NEXT.md). Poniżej skrót:

### Tryb developerski
```bash
# backend (uvicorn --reload) + web-next (next dev, turbopack off)
make start        # alias make start-dev

# zatrzymanie procesów i czyszczenie portów 8000/3000
make stop

# status PID-ów
make status
```

### Tryb produkcyjny
```bash
make start-prod   # build next + uvicorn bez reload
make stop
```

- backend działa na `http://localhost:8000` (REST/SSE/WS),
- Next.js serwuje UI na `http://localhost:3000`,
- flaga `SERVE_LEGACY_UI=True` uruchamia stary panel FastAPI na porcie 8000 (rozwiązanie awaryjne / referencyjne).

### 🔧 Profile Uruchomieniowe (Light Mode)

Venom oferuje elastyczne tryby uruchamiania komponentów osobno - idealnie dla środowisk developerskich z ograniczonymi zasobami (PC, laptop).

#### Uruchamianie komponentów osobno

| Komenda | Opis | Zużycie zasobów | Kiedy używać |
|---------|------|-----------------|--------------|
| `make api` | Backend (produkcyjny, **bez** autoreload) | ~50 MB RAM, ~5% CPU | Praca nad frontendem lub gdy nie edytujesz kodu backendu |
| `make api-dev` | Backend (developerski, **z** autoreload) | ~110 MB RAM, ~70% CPU (spike) | Aktywna praca nad kodem backendu |
| `make api-stop` | Zatrzymaj tylko backend | - | Zwalnia port 8000 i pamięć backendu |
| `make web` | Frontend (produkcyjny build + start) | ~500 MB RAM, ~3% CPU | Demo lub gdy nie edytujesz UI |
| `make web-dev` | Frontend (dev server z hot reload) | ~1.3 GB RAM, ~7% CPU | Aktywna praca nad UI |
| `make web-stop` | Zatrzymaj tylko frontend | - | Zwalnia port 3000 i pamięć frontend |
| `make vllm-start` | Uruchom vLLM (lokalny model LLM) | ~1.4 GB RAM, 13% RAM | Tylko gdy pracujesz z lokalnymi modelami |
| `make vllm-stop` | Zatrzymaj vLLM | - | Zwalnia ~1.4 GB RAM |
| `make ollama-start` | Uruchom Ollama | ~400 MB RAM | Alternatywa dla vLLM |
| `make ollama-stop` | Zatrzymaj Ollama | - | Zwalnia pamięć Ollama |

#### Przykładowe scenariusze użycia

**Scenariusz 1: Praca tylko nad API (Light)**
```bash
make api          # Backend bez autoreload (~50 MB)
# Nie uruchamiaj web ani LLM - oszczędzasz ~2.7 GB RAM
```

**Scenariusz 2: Praca nad frontendem**
```bash
make api          # Backend w tle (stabilny, bez reload)
make web-dev      # Frontend z hot reload do pracy nad UI
# Nie uruchamiaj LLM jeśli nie jest potrzebny
```

**Scenariusz 3: Pełny stack development**
```bash
make api-dev      # Backend z autoreload
make web-dev      # Frontend z hot reload
make vllm-start   # LLM tylko jeśli pracujesz z lokalnymi modelami
```

**Scenariusz 4: Demo / prezentacja**
```bash
make start-prod   # Wszystko w trybie produkcyjnym (niższe zużycie CPU)
```

**Scenariusz 5: Tylko testowanie API**
```bash
make api          # Backend bez UI
curl http://localhost:8000/health
```

#### 💡 Wskazówki optymalizacji

- **VS Code Server**: Jeśli pracujesz w CLI, zamknij zdalne VS Code:
  ```bash
  # Z poziomu WSL/Linux
  pkill -f vscode-server
  # Lub jeśli używasz code tunnel
  code tunnel exit
  ```

- **Autoreload**: `--reload` w uvicorn spawnuje dodatkowy proces watchera. Używaj `make api` zamiast `make api-dev` gdy nie edytujesz kodu backendu.

- **Next.js dev**: `next dev` zużywa ~1.3 GB RAM przez hot reload. Używaj `make web` (produkcyjny) gdy tylko testujesz, nie edytujesz UI.

- **LLM runtime**: vLLM/Ollama zużywają 1-2 GB RAM. Uruchamiaj je **tylko** gdy pracujesz z lokalnymi modelami. W trybie `AI_MODE=CLOUD` nie są potrzebne.

> Wszystkie dane i testy są traktowane jako lokalny eksperyment – Venom działa na prywatnej maszynie użytkownika i **nie szyfrujemy artefaktów**. Zamiast tego katalogi z wynikami (`**/test-results/`, `perf-artifacts/`, raporty Playwright/Locust) trafiają na listę `.gitignore`, aby uniknąć przypadkowego commitowania wrażliwych danych. Transparencja ma priorytet nad formalnym „shadow data”.

#### Kluczowe zmienne środowiskowe:

**AI Configuration (Hybrid Engine):**
```bash
# Tryb AI: LOCAL (tylko lokalne), HYBRID (mix), CLOUD (głównie chmura)
AI_MODE=LOCAL

# Local LLM (Ollama/vLLM)
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=llama3

# Cloud Providers (opcjonalne, wymagane dla HYBRID/CLOUD)
GOOGLE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Hybrid Settings
HYBRID_CLOUD_PROVIDER=google        # google lub openai
HYBRID_LOCAL_MODEL=llama3
HYBRID_CLOUD_MODEL=gemini-1.5-pro
SENSITIVE_DATA_LOCAL_ONLY=true     # Wrażliwe dane ZAWSZE local
```

**Network & Discovery (Local First):**
```bash
# mDNS (Zeroconf) dla lokalnej sieci - venom.local
# UWAGA: Cloudflare został usunięty, używamy lokalnego discovery
```

**The Hive (Distributed Processing):**
```bash
ENABLE_HIVE=false
HIVE_URL=https://hive.example.com:8080
HIVE_REGISTRATION_TOKEN=your_token
REDIS_HOST=localhost
```

**The Nexus (Distributed Mesh):**
```bash
ENABLE_NEXUS=false
NEXUS_SHARED_TOKEN=your_secret_token
NEXUS_PORT=8765
```

**External Integrations:**
```bash
GITHUB_TOKEN=ghp_your_token         # Personal Access Token
GITHUB_REPO_NAME=username/repo      # Nazwa repozytorium
DISCORD_WEBHOOK_URL=https://...     # Opcjonalne
ENABLE_ISSUE_POLLING=false          # Włącz auto-polling Issues
```

📖 **Pełna lista zmiennych:** [.env.example](.env.example)
📖 **Dokumentacja integracji zewnętrznych:** [docs/EXTERNAL_INTEGRATIONS.md](docs/EXTERNAL_INTEGRATIONS.md)
📖 **Dokumentacja Hybrid AI:** [docs/HYBRID_AI_ENGINE.md](docs/HYBRID_AI_ENGINE.md)

### Panel Konfiguracji (Configuration UI)

Venom 2.0 wprowadza **graficzny panel konfiguracji** dostępny w interfejsie webowym pod adresem `http://localhost:3000/config`. Panel umożliwia:

#### Zarządzanie Usługami
- **Monitoring statusów** - Backend, UI, LLM (Ollama/vLLM), Hive, Nexus, Background Tasks
- **Kontrola procesów** - Start/Stop/Restart z UI bez konieczności korzystania z terminala
- **Metryki w czasie rzeczywistym** - PID, port, CPU%, RAM, uptime, ostatnie logi
- **Profile szybkie**:
  - `Full Stack` - Wszystkie usługi aktywne
  - `Light` - Tylko Backend i UI (oszczędność zasobów)
  - `LLM OFF` - Wszystko oprócz modeli językowych

#### Edycja Parametrów
Panel umożliwia edycję kluczowych parametrów runtime z poziomu UI, z automatyczną:
- **Walidacją zakresów** - Porty (1-65535), progi pewności (0.0-1.0), wartości boolean
- **Maskowaniem sekretów** - API keys, tokeny, hasła są domyślnie ukryte
- **Backupem konfiguracji** - Automatyczny backup `.env` do `config/env-history/` przed każdą zmianą
- **Informacją o restartach** - System wskazuje które usługi wymagają restartu po zmianie

#### Dostępne sekcje parametrów:
1. **AI Mode** - Tryb AI, endpoint LLM, klucze API, routing modeli
2. **Commands** - Komendy start/stop dla Ollama i vLLM
3. **Hive** - Konfiguracja Redis, kolejki, timeouty
4. **Nexus** - Distributed mesh, port, tokeny, heartbeat
5. **Tasks** - Zadania w tle (dokumentacja, gardening, memory consolidation)
6. **Shadow** - Desktop awareness, progi pewności, privacy filter
7. **Ghost** - Visual GUI automation, verification, safety delays
8. **Avatar** - Audio interface, Whisper, TTS, VAD

#### Bezpieczeństwo
- **Whitelist parametrów** - Tylko zdefiniowane parametry można edytować przez UI
- **Walidacja typów i zakresów** - Sprawdzanie poprawności wartości przed zapisem
- **Sprawdzanie zależności** - System nie pozwoli uruchomić usługi bez spełnienia wymagań (np. Nexus wymaga działającego backendu)
- **Historia zmian** - Każda modyfikacja `.env` jest zapisywana z timestampem (zachowywanych ostatnie 50 backupów)

#### Przywracanie konfiguracji
Panel oferuje funkcję przywracania `.env` z wcześniejszych backupów:
```bash
# Backupy znajdują się w:
config/env-history/.env-YYYYMMDD-HHMMSS
```

> 💡 **Tip**: Profile szybkie są idealne do przełączania między trybami pracy. Użyj `Light` podczas developmentu na laptopie, a `Full Stack` na stacji roboczej z GPU.

### 📊 Monitoring Zasobów

Venom oferuje narzędzia do szybkiej diagnostyki zużycia zasobów systemowych.

#### System Snapshot
```bash
# Generuje raport diagnostyczny (procesy, pamięć, CPU, status usług)
make monitor

# Ręczne uruchomienie
bash scripts/diagnostics/system_snapshot.sh
```

Raport zostanie zapisany w `logs/diag-YYYYMMDD-HHMMSS.txt` i zawiera:
- Uptime i load average
- Zużycie pamięci (free -h, /proc/meminfo)
- Top 15 procesów (CPU i RAM)
- Status procesów Venom (uvicorn, Next.js, vLLM, Ollama)
- Status PID files i otwarte porty (8000, 3000, 8001, 11434)

**Przykład użycia:**
```bash
# Przed rozpoczęciem pracy - sprawdź baseline
make monitor

# Po uruchomieniu usług - porównaj zużycie
make api-dev
make web-dev
make monitor

# Po zakończeniu - upewnij się że wszystko zostało zatrzymane
make stop
make monitor
```

### 💾 Zarządzanie Pamięcią WSL (Windows)

Jeśli uruchamiasz Venom w WSL (Windows Subsystem for Linux), możesz napotkać problem z `vmmem` - procesem Windows, który rezerwuje dużo RAM mimo niewielkiego zużycia po stronie Linuxa.

#### Sprawdzanie zużycia pamięci
```bash
# Pokaż szczegółowe statystyki pamięci WSL
bash scripts/wsl/memory_check.sh
```

Skrypt wyświetli:
- Podsumowanie pamięci (free -h)
- Szczegółowe info z /proc/meminfo
- Top 10 procesów zużywających RAM
- Zużycie pamięci przez poszczególne komponenty Venom

#### Problem: vmmem zajmuje 20+ GB na Windows

**Symptom:** Task Manager w Windows pokazuje proces `vmmem` zajmujący 20-30 GB RAM, mimo że `free -h` w WSL pokazuje tylko 3-4 GB.

**Przyczyna:** WSL nie zwraca pamięci do Windows natychmiast. Cache i bufory są trzymane "na wszelki wypadek".

**Rozwiązanie:**

1. **Doraźne:** Reset pamięci WSL
   ```bash
   # Z poziomu WSL (zatrzyma wszystkie procesy Venom i wykona shutdown)
   bash scripts/wsl/reset_memory.sh

   # LUB z poziomu Windows (PowerShell/CMD)
   wsl --shutdown
   ```

2. **Trwałe:** Limituj zużycie przez `.wslconfig`

   Utwórz plik `%USERPROFILE%\.wslconfig` (np. `C:\Users\TwojaNazwa\.wslconfig`):
   ```ini
   [wsl2]
   # Limit pamięci dla WSL
   memory=12GB

   # Liczba procesorów
   processors=4

   # Limit swap
   swap=8GB
   ```

   Dostępny przykład z komentarzami:
   ```bash
   # Zobacz pełną konfigurację z przykładami
   cat scripts/wsl/wslconfig.example

   # Skopiuj do Windows (z poziomu WSL)
   cp scripts/wsl/wslconfig.example /mnt/c/Users/TwojaNazwa/.wslconfig
   ```

   Po zapisaniu `.wslconfig` wykonaj:
   ```powershell
   # Z poziomu Windows (PowerShell/CMD)
   wsl --shutdown
   ```

   Następnie uruchom ponownie terminal WSL.

#### Przykładowe konfiguracje .wslconfig

**PC z 16 GB RAM (oszczędny):**
```ini
[wsl2]
memory=8GB
processors=4
swap=4GB
```

**PC z 32 GB RAM (zbalansowany):**
```ini
[wsl2]
memory=12GB
processors=6
swap=8GB
```

**Workstation z 64 GB RAM (performance):**
```ini
[wsl2]
memory=32GB
processors=12
swap=16GB
```

#### Monitorowanie vmmem w Windows

1. Otwórz Task Manager (Ctrl+Shift+Esc)
2. Zakładka "Details" lub "Processes"
3. Znajdź proces "vmmem" - to jest pamięć używana przez WSL
4. Porównaj z wynikami `free -h` w WSL

Jeśli różnica jest znaczna (>50%), rozważ:
- Wykonanie `wsl --shutdown` aby zwolnić cache
- Ustawienie limitów w `.wslconfig`
- Używanie profili Light (`make api` zamiast `make start-dev`)

### Uruchomienie

```bash
# Uruchom serwer
uvicorn venom_core.main:app --reload

# Lub użyj make
make run
```

## 📖 Dokumentacja

- [Kompletna dokumentacja zadania 007](docs/_done/007_THE_HIVE_MIND_COMPLETED.md)
- [Architektura systemu](docs/VENOM_MASTER_VISION_V1.md)
- [System rozpoznawania intencji](docs/INTENT_RECOGNITION.md)
- [Strojenie modelu LLM (Cockpit)](docs/_to_do/072_strojenie_modelu_llm_ui.md)
- [Zarządzanie modelami](docs/MODEL_MANAGEMENT.md)
- [Panel konfiguracji](docs/CONFIG_PANEL.md)
- [Contributing Guide](docs/CONTRIBUTING.md)

## 🧪 Testy

```bash
cd /path/to/venom
source .venv/bin/activate || true

# Uruchom wszystkie testy
pytest

## 🔬 Testy i benchmarki

Pełna instrukcja (kroki + oczekiwane wartości) jest w [`docs/TESTING_CHAT_LATENCY.md`](docs/TESTING_CHAT_LATENCY.md). Najważniejsze komendy:

### Backend (FastAPI / agenci)
- `pytest -q` — smoke całego systemu.
- `pytest tests/test_researcher_agent.py` / `tests/test_architect_agent.py` — scenariusze agentów.
- `pytest tests/perf/test_chat_pipeline.py -m performance` — pomiar SSE (task_update → task_finished) + batch równoległy.
- `pytest --cov=venom_core --cov-report=html` — raport pokrycia.

### Frontend Next.js
- `npm --prefix web-next run lint`
- `npm --prefix web-next run build`
- `npm --prefix web-next run test:e2e` — Playwright na buildzie prod.

### Czas reakcji i wydajność chatu
- `npm --prefix web-next run test:perf` — Playwright porównujący Next Cockpit i stary panel (`PERF_NEXT_BASE_URL` / `PERF_LEGACY_BASE_URL`, raport HTML odkłada się do `test-results/perf-report`).
-  Dostępne env-y: `PERF_NEXT_LATENCY_BUDGET`, `PERF_LEGACY_LATENCY_BUDGET` (domyślnie 5000ms/6000ms) oraz `PERF_*_RESPONSE_TIMEOUT` jeśli trzeba rozluźnić limity na wolniejszych maszynach.
- `pytest tests/perf/test_chat_pipeline.py -m performance` — backendowy pipeline (czas do `task_finished` + batch).
- `./scripts/run-locust.sh` — start panelu Locusta (`http://127.0.0.1:8089`) i ręczne obciążenie API.
- `./scripts/archive-perf-results.sh` — zrzut `test-results/`, raportów Playwright/Locust do `perf-artifacts/<timestamp>/`.

> Wyniki testów NIE trafiają do repo (ignorujemy `**/test-results/`, `perf-artifacts/`, `playwright-report/`, itd.) – dzięki temu przechowujesz je lokalnie bez ryzyka ujawnienia danych.

## 🛠️ Narzędzia deweloperskie

### Pre-commit hooks

```bash
# Instalacja
pip install pre-commit
pre-commit install

# Manualne uruchomienie
pre-commit run --all-files
```

### Linting i formatowanie

```bash
cd /home/ubuntu/venom
source .venv/bin/activate || true

# Ruff (linter + formatter)
ruff check . --fix
ruff format .

# isort (sortowanie importów)
isort . --profile black

# mypy (type checking)
mypy venom_core
```

## 📊 Statystyki projektu

- **Linie kodu:** 118,555 (linie niepuste; bez `docs/`, `node_modules/`, `logs/`, `data/`)
- **Liczba agentów:** 33 (moduły `venom_core/agents/*`)
- **Liczba skills:** 19 wykonawczych (`venom_core/execution/skills/*`) + 4 pomocnicze (Memory/Voice/Whisper/Core)
- **Liczba testów:** 518 (pytest `def test_`) + 18 (Playwright `test(`)
- **Pokrycie testami:** 65%

## 🎯 Roadmap

### ✅ v1.0 (Current - Q4 2024)
- [x] Warstwa Planowania (ArchitectAgent)
- [x] Ekspansja Wiedzy (ResearcherAgent + WebSearchSkill)
- [x] Integracja z Internetem
- [x] Pamięć długoterminowa
- [x] Comprehensive testing
- [x] **NEW: External Integrations (PlatformSkill)** 🤖
  - [x] GitHub Integration (Issues, Pull Requests)
  - [x] Discord/Slack Notifications
  - [x] Issue-to-PR Workflow

### 🚧 v1.1 (Planned)
- [ ] Background polling dla GitHub Issues
- [ ] Dashboard panel dla External Integrations
- [ ] Recursive Summarization dla długich dokumentów
- [ ] Cached Search Results
- [ ] Plan Validation i Optimization
- [ ] Better Error Recovery

### 🔮 v1.2 (Future)
- [ ] Webhook support dla GitHub
- [ ] MS Teams Integration
- [ ] Multi-Source Verification
- [ ] Google Search API Integration
- [ ] Parallel Execution kroków planu
- [ ] Plan Caching dla podobnych zadań
- [ ] GraphRAG Integration

## 🤝 Contributing

Zapraszamy do współpracy! Zobacz [CONTRIBUTING.md](docs/CONTRIBUTING.md) aby dowiedzieć się jak zacząć.

### Proces

1. Fork repozytorium
2. Stwórz branch dla feature (`git checkout -b feature/amazing-feature`)
3. Commit zmian (`git commit -m 'feat: add amazing feature'`)
4. Push do brancha (`git push origin feature/amazing-feature`)
5. Otwórz Pull Request

### Konwencje

- **Kod i komentarze:** Polski
- **Commit messages:** Conventional Commits (feat, fix, docs, test, refactor)
- **Style:** Black + Ruff + isort (automatyczne przez pre-commit)
- **Tests:** Wymagane dla nowych funkcjonalności


## 🌐 THE NEXUS: Architektura Rozproszona

**NOWE w v1.1!** Venom może teraz działać jako **Centralny Węzeł (Nexus)** zarządzający rojem zdalnych instancji ("Zarodników" / Spores).

### Cechy distributed mesh:
- 🔗 **Master-Worker Architecture** - Nexus (mózg) + Spores (wykonawcy)
- 📡 **WebSocket Communication** - Szybka, dwukierunkowa komunikacja
- 🔍 **mDNS Service Discovery** - Automatyczne wykrywanie węzłów w sieci lokalnej (venom.local)
- ⚖️ **Load Balancing** - Automatyczny wybór najmniej obciążonego węzła
- 🔄 **Hot-Plug** - Dynamiczne dodawanie/usuwanie węzłów
- 💓 **Healthcheck & Failover** - Automatyczne wykrywanie offline nodes

### Przykład użycia:

```bash
# 1. Uruchom Venom w trybie Nexus
export ENABLE_NEXUS=true
export NEXUS_SHARED_TOKEN=your-secret-token
cd venom_core && python main.py

# 2. Uruchom Venom Spore na zdalnej maszynie
cd venom_spore
export SPORE_NEXUS_HOST=venom.local  # lub 192.168.1.10
export SPORE_SHARED_TOKEN=your-secret-token
python main.py

# 3. Sprawdź połączone węzły
curl http://localhost:8000/api/v1/nodes

# 4. Wykonaj zadanie na zdalnym węźle
curl -X POST http://localhost:8000/api/v1/nodes/{node_id}/execute \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "ShellSkill", "method_name": "run", "parameters": {"command": "ls"}}'
```

### Demo z Docker Compose:
```bash
# Uruchom symulację roju (2 węzły Docker)
docker-compose -f docker-compose.spores.yml up

# Uruchom demo
python examples/nexus_demo.py
```

📖 **Pełna dokumentacja:** [venom_spore/README.md](venom_spore/README.md)
📖 **Architektura Hive:** [docs/THE_HIVE.md](docs/THE_HIVE.md)

## 👥 Zespół

- **Lead Developer:** mpieniak01
- **Architecture:** Venom Core Team
- **Contributors:** [Lista kontrybutorów](https://github.com/mpieniak01/Venom/graphs/contributors)

## 🙏 Podziękowania

- Microsoft Semantic Kernel
- Microsoft AutoGen
- OpenAI / Anthropic / Google AI
- Społeczność Open Source

---

**Venom** - *Autonomiczny system agentów AI dla następnej generacji automatyzacji*

🌟 Jeśli podoba Ci się projekt, zostaw gwiazdkę na GitHub!

## 📝 Licencja

Ten projekt znajduje się obecnie na wczesnym etapie rozwoju.
Repozytorium jest publiczne wyłącznie w celach poglądowych i referencyjnych.

Na tym etapie nie jest udzielana żadna licencja.
Wszelkie prawa są zastrzeżone przez autora do odwołania.

## License

This project is currently in an early development phase.
The repository is public for review and reference purposes only.

No license is granted at this time.
All rights are reserved by the author until further notice.

---
