# Venom v2.0 🐍

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

### Uruchomienie

```bash
# Uruchom serwer
uvicorn venom_core.main:app --reload

# Lub użyj make
make run
```

## 📖 Dokumentacja

- [Kompletna dokumentacja zadania 007](docs/_done/007_THE_HIVE_MIND_COMPLETED.md)
- [Architektura systemu](docs/VENOM_MASTER_VISION_V2.md)
- [System rozpoznawania intencji](docs/INTENT_RECOGNITION.md)
- [Contributing Guide](docs/CONTRIBUTING.md)

## 🧪 Testy

```bash
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
# Ruff (linter + formatter)
ruff check . --fix
ruff format .

# isort (sortowanie importów)
isort . --profile black

# mypy (type checking)
mypy venom_core
```

## 📊 Statystyki projektu

- **Linie kodu:** ~10,000+
- **Liczba agentów:** 6 (Coder, Critic, Librarian, Chat, Researcher, Architect)
- **Liczba skills:** 5 (File, Git, Shell, Memory, WebSearch)
- **Liczba testów:** 100+
- **Pokrycie testami:** ~80%

## 🎯 Roadmap

### ✅ v2.0 (Current - Q4 2024)
- [x] Warstwa Planowania (ArchitectAgent)
- [x] Ekspansja Wiedzy (ResearcherAgent + WebSearchSkill)
- [x] Integracja z Internetem
- [x] Pamięć długoterminowa
- [x] Comprehensive testing
- [x] **NEW: External Integrations (PlatformSkill)** 🤖
  - [x] GitHub Integration (Issues, Pull Requests)
  - [x] Discord/Slack Notifications
  - [x] Issue-to-PR Workflow

### 🚧 v2.1 (Planned)
- [ ] Background polling dla GitHub Issues
- [ ] Dashboard panel dla External Integrations
- [ ] Recursive Summarization dla długich dokumentów
- [ ] Cached Search Results
- [ ] Plan Validation i Optimization
- [ ] Better Error Recovery

### 🔮 v3.0 (Future)
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

## 📝 Licencja

[LICENSE](LICENSE) - Szczegóły w pliku licencji

## 🌐 THE NEXUS: Architektura Rozproszona

**NOWE w v2.1!** Venom może teraz działać jako **Centralny Węzeł (Nexus)** zarządzający rojem zdalnych instancji ("Zarodników" / Spores).

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
