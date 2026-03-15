# Venom v1.8 🐍
[![GitGuardian](https://img.shields.io/badge/security-GitGuardian-blue)](https://www.gitguardian.com/)
[![OpenAPI Contract](https://img.shields.io/github/actions/workflow/status/mpieniak01/Venom/ci.yml?branch=main&logo=swagger&logoColor=white&label=OpenAPI%20Contract)](https://github.com/mpieniak01/Venom/actions/workflows/ci.yml)
[![SonarCloud Quality](https://sonarcloud.io/api/project_badges/measure?project=mpieniak01_Venom&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mpieniak01_Venom)
[![Known Vulnerabilities](https://snyk.io/test/github/mpieniak01/Venom/badge.svg)](https://snyk.io/test/github/mpieniak01/Venom)

**Sygnały jakości**
- *GitGuardian:* wykrywanie sekretów i zapobieganie wyciekom w historii repo i pull requestach.
- *OpenAPI Contract:* weryfikuje eksport OpenAPI i synchronizację codegen typów TypeScript.
- *SonarCloud Quality:* aktualny stan kontroli jakości kodu w SonarCloud.
- *Snyk Vulnerabilities:* aktualny status podatności zależności dla tego repozytorium GitHub.

> **| [English Documentation Available](README.md)**

**Venom** to open-source'owy, local-first stack AI do realnej automatyzacji pracy inżynierskiej. Łączy orkiestrację agentów, wykonywanie narzędzi i pamięć długoterminową w jednym środowisku, które możesz uruchomić i rozwijać lokalnie.

Aktualna rekomendacja środowiskowa: używaj `dev` i `preprod`. `prod` jest nadal etapem planowanym i nie jest jeszcze zwalidowane/rekomendowane do działania live.

To nie jest "czarna skrzynka". W praktyce dostajesz jawne sterowanie procesem (Workflow Control Plane), przejrzyste decyzje runtime i pełny ślad audytowy requestów. Do tego 3 stosy modeli do wyboru: `ONNX`, `vLLM`, `Ollama` - zależnie od sprzętu, kosztu i celu.

## Dlaczego Venom
- Local-first z opcją cloud: dane i inferencja mogą zostać lokalnie, a nie w zewnętrznym SaaS.
- Trzy runtime do wyboru (`ONNX` / `vLLM` / `Ollama`): dobierasz stos pod sprzęt i wymagany latency/cost.
- Sterowanie procesem zamiast "magii": Workflow Control Plane pokazuje co działa, co jest aktywne i co się zmienia.
- Transparentność i audyt: request tracing pokazuje decyzje, kroki i wyniki end-to-end.
- Pamięć i lessons learned: wiedza nie znika po jednym czacie, tylko wraca w kolejnych zadaniach.
- Otwarta baza kodu i dokumentacji: łatwiej debugować, rozszerzać i utrzymać własny fork.
- Mierzalne bramki jakości w CI: SonarCloud, Snyk i kontrakt OpenAPI działają jako jawne sygnały jakości.

## Kluczowe możliwości
- 🤖 **Orkiestracja agentów** - planowanie i wykonanie zadań przez wyspecjalizowane role.
- 🧭 **Hybrydowy runtime modeli (3-stack)** - przełączanie Ollama / vLLM / ONNX + cloud z podejściem local-first.
- 💾 **Pamięć i wiedza** - utrwalanie kontekstu, lessons learned i ponowne użycie wiedzy.
- 🎓 **Uczenie workflow** - budowa automatyzacji przez demonstrację działań użytkownika.
- 🛠️ **Operacje i governance** - panel usług, policy gate i kontrola kosztów providerów.
- 🔍 **Transparentność i pełna audytowalność** - śledzenie end-to-end decyzji, działań i wyników dla zaufania operacyjnego, compliance oraz szybszej analizy incydentów.
- 🔌 **Rozszerzalność** - narzędzia lokalne i import MCP z repozytoriów Git.

## Ostatnie wdrożenia (2026-03, v1.8)
- Global Policy Gate działa jako jeden centralny checkpoint runtime w przepływie orchestratora (`global_pre_execution`).
- Ujednolicono kontrakt blokad policy/autonomy (`reason_code`, `user_message`, `technical_context`, `remediation_hint`) oraz zapis audytowy.
- Dodano endpointy operacyjne dla rollout i KPI policy:
  - `GET /api/v1/system/autonomy/rollout-status`
  - `GET /api/v1/system/autonomy/observability`
- Dostarczono skrypt walidacji rollout: `scripts/ops/verify_policy_rollout.py`.
- Uproszczono ścieżkę wykonawczą do governance runtime-only (usunięto legacy submit-level policy block ze ścieżki wykonania).
- Rozszerzono UI `/config` o zakładkę `Uprawnienia` i sterowanie autonomią/audytem na tym samym strumieniu zdarzeń.
- Domknięto E2E ścieżkę direct deploy ONNX w Academy dla Gemma-3 LoRA (`merge_export -> activate -> inference -> deactivate`) z walidacją live i artefaktami.
- Podniesiono rekomendowany profil WSL2 dla Academy ONNX E2E na hostach 32 GB / 12 GB do `memory=30GB`, `swap=16GB` (szczegóły: `docs/PL/RUNTIME_PROFILES.md`).

## Dokumentacja
### Start i operacje
- [Deployment + uruchamianie](docs/PL/DEPLOYMENT_NEXT.md) - Kroki startu środowiska dev/prod oraz wymagania runtime.
- [Macierz wsparcia środowisk](docs/PL/ENVIRONMENTS_SUPPORT.md) - Aktualny status wsparcia `dev`/`preprod`/`prod` oraz wymagany model konfiguracji.
- [Przewodnik Dashboard](docs/PL/DASHBOARD_GUIDE.md) - Uruchamianie panelu web, skrypty i przegląd cockpitu operacyjnego.
- [Przewodnik użycia tooli](docs/PL/TOOLS_USAGE_GUIDE.md) - Routing slash tooli, zachowanie `forced_tool` i wymagania web-search w `.venv`.
- [Panel konfiguracji](docs/PL/CONFIG_PANEL.md) - Zakres ustawień dostępnych w UI i zasady bezpiecznej edycji.
- [Frontend Next.js](docs/PL/FRONTEND_NEXT_GUIDE.md) - Struktura aplikacji `web-next`, widoki i standardy implementacyjne.
- [Kontrola ruchu API](docs/PL/API_TRAFFIC_CONTROL.md) - Globalny model anti-spam/anti-ban dla ruchu inbound i outbound.

### Architektura
- [Wizja systemu](docs/PL/VENOM_MASTER_VISION_V1.md) - Docelowy kierunek rozwoju platformy i główne założenia produktowe.
- [Architektura backendu](docs/PL/BACKEND_ARCHITECTURE.md) - Moduły backendu, odpowiedzialności i przepływy między komponentami.
- [Silnik hybrydowy AI](docs/PL/HYBRID_AI_ENGINE.md) - Zasady routingu LOCAL/HYBRID/CLOUD i polityki local-first.
- [Workflow Control](docs/PL/THE_WORKFLOW_CONTROL.md) - Model sterowania workflow, operacje i reguły kontroli wykonania.

### Agenci i funkcje
- [Katalog agentów systemu](docs/PL/SYSTEM_AGENTS_CATALOG.md) - Opis ról agentów, ich wejść/wyjść i współpracy w runtime.
- [The Academy](docs/PL/THE_ACADEMY.md) - Mechanizmy uczenia, strojenia i operacjonalizacji danych treningowych.
- [Warstwa pamięci](docs/PL/MEMORY_LAYER_GUIDE.md) - Organizacja pamięci wektorowej/grafowej i zasady retrievalu wiedzy.
- [Integracje zewnętrzne](docs/PL/EXTERNAL_INTEGRATIONS.md) - Konfiguracja i użycie integracji typu GitHub, Slack i inne usługi.

### Jakość i współpraca
- [Wytyczne dla coding-agentów](docs/PL/AGENTS.md) - Obowiązkowe zasady pracy agentów i wymagane bramki jakości.
- [Przewodnik modułów opcjonalnych](docs/PL/MODULES_OPTIONAL_REGISTRY.md) - Jak tworzyć, rejestrować i włączać zewnętrzne moduły Venom.
- [Contributing](docs/PL/CONTRIBUTING.md) - Proces współpracy, standard zmian i oczekiwania do PR.
- [Polityka testów](docs/PL/TESTING_POLICY.md) - Zakres testów, komendy walidacyjne i wymagania jakościowe.
- [QA Delivery Guide](docs/PL/QA_DELIVERY_GUIDE.md) - Checklista dostarczenia zmian od walidacji do gotowości release.
- [Baseline benchmarku LLM 3-stack](docs/PL/LLM_RUNTIME_3STACK_BENCHMARK_BASELINE.md) - Zamrożone metryki referencyjne dla `ollama`/`vllm`/`onnx` i porównania E2E.

## Podgląd interfejsu
<table>
  <tr>
    <td align="center" width="50%">
      <img src="./docs/assets/wiedza.jpeg" width="100%" alt="Knowledge Grid" />
      <br />
      <strong>Knowledge Grid</strong><br />
      Widok pamięci i relacji wiedzy.
    </td>
    <td align="center" width="50%">
      <img src="./docs/assets/diagram.jpeg" width="100%" alt="Trace Analysis" />
      <br />
      <strong>Trace Analysis</strong><br />
      Analiza przepływu żądań i orkiestracji.
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="./docs/assets/konfiguracja.jpg" width="100%" alt="Konfiguracja" />
      <br />
      <strong>Konfiguracja</strong><br />
      Zarządzanie runtime i usługami.
    </td>
    <td align="center" width="50%">
      <img src="./docs/assets/chat.jpeg" width="100%" alt="AI Command Center" />
      <br />
      <strong>AI Command Center</strong><br />
      Konsola operacyjna i historia pracy.
    </td>
  </tr>
</table>

## Architektura
### Struktura projektu
```text
venom/
├── venom_core/
│   ├── api/routes/          # Endpointy REST API (agenci, zadania, pamięć, węzły)
│   ├── core/flows/          # Przepływy biznesowe i orkiestracja
│   ├── agents/              # Wyspecjalizowani agenci AI
│   ├── execution/           # Warstwa wykonawcza i routing modeli
│   ├── perception/          # Percepcja (desktop_sensor, audio)
│   ├── memory/              # Pamięć długoterminowa (wektory, graf, workflow)
│   └── infrastructure/      # Infrastruktura (sprzęt, chmura, broker wiadomości)
├── web-next/                # Dashboard frontendowy (Next.js)
└── modules/                 # Workspace modułów opcjonalnych (osobne repo modułów)
```

### Główne komponenty
#### 1) Warstwa strategiczna
- **ArchitectAgent** - rozbija złożone zadania na plan wykonania.
- **ExecutionPlan** - model planu z krokami i zależnościami.

#### 2) Ekspansja wiedzy
- **ResearcherAgent** - zbiera i syntetyzuje wiedzę z Internetu.
- **WebSearchSkill** - wyszukiwanie i ekstrakcja treści.
- **MemorySkill** - pamięć długoterminowa (LanceDB).

#### 3) Warstwa wykonawcza
- **CoderAgent** - generuje kod z wykorzystaniem wiedzy.
- **CriticAgent** - weryfikuje jakość kodu.
- **LibrarianAgent** - zarządza plikami i strukturą projektu.
- **ChatAgent** - asystent konwersacyjny.
- **GhostAgent** - automatyzacja GUI (RPA).
- **ApprenticeAgent** - uczenie przepływów przez obserwację.

#### 4) Silnik hybrydowy AI
- **HybridModelRouter** (`venom_core/execution/model_router.py`) - routing lokalny/chmura.
- **Tryby**: LOCAL, HYBRID, CLOUD.
- **Local-first**: priorytet prywatności i kontroli kosztów.
- **Providerzy**: Ollama/vLLM/ONNX (lokalne), Gemini, OpenAI.
- Wrażliwe dane mogą być blokowane przed wyjściem do chmury.

#### 5) Uczenie przez demonstrację
- **DemonstrationRecorder** - nagrywanie akcji użytkownika (mysz, klawiatura, ekran).
- **DemonstrationAnalyzer** - analiza behawioralna i mapowanie piksel → semantyka.
- **WorkflowStore** - magazyn procedur z możliwością edycji.
- **Integracja z GhostAgent** - wykonanie wygenerowanych workflow.

#### 6) Orkiestracja i kontrola
- **Orchestrator** - główny koordynator systemu.
- **IntentManager** - klasyfikacja intencji i dobór ścieżki.
- **TaskDispatcher** - routing zadań do agentów.
- **Workflow Control Plane** - wizualne sterowanie przepływami.

#### 7) The Academy
- **LessonStore** - baza doświadczeń i korekt.
- **Training Pipeline** - dostrajanie LoRA/QLoRA.
- **Adapter Management** - hot-swapping adapterów modeli.
- **Genealogy** - śledzenie ewolucji modeli i metryk.

#### 8) Usługi runtime
- Backend API (FastAPI/uvicorn) i Next.js UI.
- Serwery LLM: Ollama, vLLM, ONNX (in-process).
- LanceDB (embedded), Redis (opcjonalnie).
- Nexus i Background Tasks jako procesy opcjonalne.


## Szybki start
### Ścieżka A: instalacja ręczna z Git (dev)
```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
pip install -r requirements.txt
cp .env.dev.example .env.dev
make start
```

Domyślny `requirements.txt` instaluje **minimalny profil API/cloud**.
Jeśli chcesz lokalne silniki runtime, doinstaluj jeden z profili:
- `pip install -r requirements.txt` (Ollama: bez dodatkowych paczek Pythona)
- `pip install -r requirements-profile-vllm.txt`
- `pip install -r requirements-profile-onnx.txt`
- `pip install -r requirements-profile-onnx-cpu.txt`
- `pip install -r requirements-extras-onnx.txt` (opcjonalne extras: `faster-whisper` + `piper-tts`; instaluj po profilu ONNX/ONNX-CPU)
- `pip install -r requirements-full.txt` (legacy full stack)

### Gwarancje profili zależności
Traktuj tę tabelę jako źródło prawdy dla rozróżnienia: "to oczekiwane" vs "to błąd profilu".

| Profil | Gwarantowany zakres | Jawnie nie zawiera |
|---|---|---|
| `requirements.txt` (`requirements-profile-api.txt`) | baseline API/cloud (`fastapi`, `uvicorn`, providerzy cloud) | ciężkie lokalne pakiety runtime (`vllm`, `onnxruntime*`, `lancedb`, `sentence-transformers`) |
| `requirements-profile-web.txt` | baseline API + zależności integracji web | te same ciężkie lokalne pakiety runtime co profil API |
| `requirements-profile-vllm.txt` | baseline API + `vllm` | stos ONNX, stos RAG/wektorowy (`lancedb`, `sentence-transformers`) |
| `requirements-profile-onnx.txt` | baseline API + stos runtime ONNX | vLLM, stos RAG/wektorowy (`lancedb`, `sentence-transformers`) |
| `requirements-profile-onnx-cpu.txt` | baseline API + stos runtime ONNX CPU | vLLM, pakiety ONNX CUDA, stos RAG/wektorowy (`lancedb`, `sentence-transformers`) |
| `requirements-full.txt` | legacy profil all-in (zawiera `vllm`, ONNX, `lancedb`, `sentence-transformers`) | n/a |

Zasady triage incydentów:
1. Jeśli pakietu brakuje, bo nie zainstalowano właściwego profilu, to zachowanie oczekiwane.
2. Jeśli pakiet nie jest gwarantowany przez aktywny profil, to zachowanie oczekiwane.
3. Jeśli pakiet jest wpisany w wybranym profilu, ale nadal go brakuje po instalacji, to problem instalacji/środowiska i traktujemy to jako defekt.

### Ścieżka B: instalacja przez skrypt Docker (jedna komenda)
```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
scripts/docker/venom.sh
```

Po uruchomieniu:
- API: `http://localhost:8000`
- UI: `http://localhost:3000`

Polityka protokołów:
- Stos dev/lokalny działa domyślnie po HTTP (`URL_SCHEME_POLICY=force_http` w profilach docker).
- Publiczny production powinien działać po HTTPS na reverse proxy/ingress (TLS na brzegu).

### Najczęstsze komendy
```bash
make start       # backend + frontend (webpack-safe dev)
make start2      # backend + frontend (turbopack dev)
make stop        # zatrzymanie usług
make status      # status procesów
make start-prod  # tryb produkcyjny
```

Ostrzeżenie:
- `make start-prod` istnieje dla zgodności technicznej, ale `prod` nie jest jeszcze zwalidowane/rekomendowane do działania live.
- Rekomendowane środowiska: `dev` i `preprod`.

## Frontend (Next.js - `web-next`)
Warstwa prezentacji działa na Next.js 16 (App Router, React 19).
- Wymagane środowisko: Node.js `>=20.9.0` oraz npm `>=10.0.0` (zob. `web-next/.nvmrc`).
- **SCC (server/client components)** - komponenty serwerowe domyślne, interaktywne oznaczone jako client.
- **Wspólny layout** (`components/layout/*`) - TopBar, Sidebar, status bar i overlaye.

### Komendy frontendu
```bash
npm --prefix web-next install
npm --prefix web-next run dev
npm --prefix web-next run build
npm --prefix web-next run test:e2e
npm --prefix web-next run lint:locales
```

### Zmienne do pracy lokalnej z API
```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000/ws/events
API_PROXY_TARGET=http://localhost:8000
```

### Slash commands w Cockpit
- Wymuszenie narzędzia: `/<tool>` (np. `/git`, `/web`).
- Wymuszenie providerów: `/gpt` (OpenAI) i `/gem` (Gemini).
- UI pokazuje etykietę `Forced` po wykryciu prefiksu.
- Język UI trafia jako `preferred_language` w `/api/v1/tasks`.
- Strategia streszczeń (`SUMMARY_STRATEGY`): `llm_with_fallback` lub `heuristic_only`.

## Instalacja i zależności
### Wymagania
```text
Python 3.12+ (zalecane 3.12)
```

### Kluczowe pakiety
- `semantic-kernel>=1.9.0` - orkiestracja agentów.
- `ddgs>=1.0` - wyszukiwarka.
- `trafilatura` - ekstrakcja tekstu ze stron WWW.
- `beautifulsoup4` - parsowanie HTML.
- `lancedb` - baza wektorowa pamięci.
- `fastapi` - API serwera.
- `zeroconf` - wykrywanie usług mDNS.
- `pynput` - nagrywanie akcji użytkownika.
- `google-genai` - Gemini (opcjonalnie).
- `openai` / `anthropic` - modele LLM (opcjonalnie).

Profile:
- [requirements.txt](requirements.txt) - domyślny minimalny profil API/cloud
- [requirements-profile-web.txt](requirements-profile-web.txt) - profil API + integracja z web-next
- [requirements-profile-vllm.txt](requirements-profile-vllm.txt) - profil API + vLLM
- [requirements-profile-onnx.txt](requirements-profile-onnx.txt) - profil API + ONNX LLM (trzeci silnik)
- [requirements-profile-onnx-cpu.txt](requirements-profile-onnx-cpu.txt) - profil API + ONNX CPU-only
- [requirements-extras-onnx.txt](requirements-extras-onnx.txt) - opcjonalne extras (`faster-whisper`, `piper-tts`), instalowane po profilu ONNX LLM lub ONNX CPU
- [requirements-full.txt](requirements-full.txt) - pełny legacy stack

## Uruchamianie (FastAPI + Next.js)
Pełna checklista: [`docs/PL/DEPLOYMENT_NEXT.md`](docs/PL/DEPLOYMENT_NEXT.md).

### Tryb developerski
```bash
make start
make stop
make status
```

### Tryb produkcyjny
```bash
make start-prod
make stop
```

Ostrzeżenie:
- Na obecnym etapie ten tryb traktujemy jako nierekomendowany (brak pełnej walidacji produkcyjnej).


### Konfiguracje o najniższym zużyciu pamięci
| Konfiguracja | Komendy | Szacunkowy RAM | Zastosowanie |
|-------------|---------|----------------|--------------|
| Minimalna | `make api` | ~50 MB | Testy API / backend-only |
| Lekka z lokalnym LLM | `make api` + `make ollama-start` | ~450 MB | API + lokalny model bez UI |
| Lekka z UI | `make api` + `make web` | ~550 MB | Demo i szybka walidacja UI |
| Zbalansowana | `make api` + `make web` + `make ollama-start` | ~950 MB | Codzienna praca bez dev autoreload |
| Najcięższa (dev) | `make api-dev` + `make web-dev` + `make vllm-start` | ~2.8 GB | Pełny development i testy lokalnych modeli |


## Kluczowe zmienne środowiskowe
Szablon dev: [.env.dev.example](.env.dev.example)
Szablon preprod: [.env.preprod.example](.env.preprod.example)


## Panel konfiguracji (UI)
Panel pod adresem `http://localhost:3000/config` umożliwia:
- monitorowanie statusu backendu, UI, LLM, Hive, Nexus,
- start/stop/restart usług z poziomu UI,
- metryki czasu rzeczywistego (PID, port, CPU, RAM, uptime),
- profile szybkie: `Full Stack`, `Light`, `LLM OFF`.

### Edycja parametrów
- walidacja zakresów i typów,
- maskowanie sekretów,
- backup aktywnego pliku env (`.env.dev` lub `.env.preprod`) do `config/env-history/`,
- informacja o usługach wymagających restartu.

### Bezpieczeństwo panelu
- biała lista edytowalnych parametrów,
- walidacja zależności między usługami,
- historia zmian z timestampem.

## Monitoring i higiena środowiska
### Monitoring zasobów
```bash
make monitor
bash scripts/diagnostics/system_snapshot.sh
```

Raport (`logs/diag-YYYYMMDD-HHMMSS.txt`) zawiera:
- uptime i load average,
- zużycie pamięci,
- top procesy CPU/RAM,
- status procesów Venom,
- otwarte porty (8000, 3000, 8001, 11434).

### Higiena środowiska dev (repo + Docker)
```bash
make env-audit
make env-clean-safe
make env-clean-docker-safe
CONFIRM_DEEP_CLEAN=1 make env-clean-deep
make env-report-diff
```

## Paczka Docker (użytkownik końcowy)
Uruchomienie z gotowych obrazów:
```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
scripts/docker/venom.sh
```

Profile compose:
- `compose/compose.release.yml` - profil użytkownika końcowego (pull gotowych obrazów).
- `compose/compose.minimal.yml` - profil developerski (lokalny build).
- `compose/compose.spores.yml.tmp` - szkic dla Spore, obecnie nieaktywny.

Przydatne komendy:
```bash
scripts/docker/venom.sh
scripts/docker/run-release.sh status
scripts/docker/run-release.sh restart
scripts/docker/run-release.sh stop
scripts/docker/uninstall.sh --stack both --purge-volumes --purge-images
scripts/docker/logs.sh
```

Profil runtime (jedna paczka, wybierany tryb):
```bash
export VENOM_RUNTIME_PROFILE=light   # light|llm_off|full
scripts/docker/run-release.sh start
```
`llm_off` oznacza brak lokalnego runtime LLM (Ollama/vLLM/ONNX), ale backend i UI nadal mogą korzystać z zewnętrznych API LLM (np. OpenAI/Gemini) po konfiguracji kluczy.

Opcjonalny tryb GPU:
```bash
export VENOM_ENABLE_GPU=auto
scripts/docker/run-release.sh restart
```

## Jakość i bezpieczeństwo
- CI: Quick Validate + OpenAPI Contract + SonarCloud.
- Security: GitGuardian + skany zależności Snyk.
- SonarCloud = jakość kodu i pokrycie nowego kodu (maintainability, reliability, coverage).
- Snyk = podatności pakietów/zależności (ryzyko third-party w ekosystemie Python i npm).
- `pre-commit run --all-files` uruchamia: `block-docs-dev-staged`, `end-of-file-fixer`, `trailing-whitespace`, `check-added-large-files`, `check-yaml`, `debug-statements`, `ruff-check --fix`, `ruff-format`, `isort`.
- Dodatkowe hooki poza tą komendą: `block-docs-dev-tracked` (stage `pre-push`) oraz `update-sonar-new-code-group` (stage `manual`).
- `pre-commit` może modyfikować pliki (autofix), wtedy uruchom go ponownie aż wszystkie hooki będą `Passed`.
- `mypy venom_core` traktuj jako pełny audyt typów; backlog typowania może zawierać problemy niezwiązane z Twoją zmianą.
- Lokalnie przed PR:

```bash
test -f .venv/bin/activate || { echo "Brak .venv/bin/activate. Najpierw utwórz .venv."; exit 1; }
source .venv/bin/activate
pre-commit run --all-files
make pr-fast
make check-new-code-coverage
```


## Mapa drogowa
### ✅ v1.5
- [x] Funkcje v1.4 (planowanie, wiedza, pamięć, integracje).
- [x] The Academy (LoRA/QLoRA).
- [x] Workflow Control Plane.
- [x] Provider Governance.
- [x] Academy Hardening.

### ✅ v1.6
- [x] Utwardzenie kontraktu API (Wave-1 + Wave-2 MVP) wraz z synchronizacją OpenAPI/FE.
- [x] Integracja ONNX Runtime jako trzeciego lokalnego silnika LLM (3-stack: Ollama + vLLM + ONNX).
- [x] Aktualizacja strategii profili runtime i instalacji (minimum API-first + opcjonalne stosy lokalne).

### ✅ v1.7
- [x] Dowieziono obsługę modeli zdalnych (`/models` remote tab + status providerów, katalog, mapa spięć, walidacja dla ścieżek GPT/Gemini).
- [x] Utwardzono globalną kontrolę ruchu inbound/outbound (limity, retry/circuit-breaker, bezpieczniejsze zachowanie pod obciążeniem).
- [x] Rozszerzono obserwowalność konfiguracji i audytu (kanoniczny audit stream i lepsza widoczność zmian config/runtime).
- [x] Domknięto falę hardeningu Academy/API (dekompozycja modułów, spójność kontraktów, bezpieczniejsze ścieżki upload/trening/historia).
- [x] Sfinalizowano model pracy pre-prod na wspólnym stacku (separacja danych, podział `.env.dev`/`.env.preprod`, sterowanie Makefile, guard rails, backup/restore/smoke).

### ✅ v1.8 (obecna)
- [x] Zmniejszono ryzyko nieautoryzowanego wykonania zadań i kosztów błędów operacyjnych dzięki jednolitym zasadom decyzji runtime.
- [x] Skrócono czas diagnozy incydentów i blokad dzięki spójnemu feedbackowi, lepszej widoczności powodów decyzji i pełniejszemu audytowi.
- [x] Zwiększono bezpieczeństwo automatyzacji działań na plikach i desktopie, co ogranicza liczbę awarii oraz ręcznych interwencji operatora.
- [x] Podniesiono jakość odpowiedzi i powtarzalność pracy przez spójny model wiedzy oraz stabilniejszą ścieżkę uczenia systemu.
- [x] Zwiększono przewidywalność wydań i wdrożeń dzięki mocniejszym bramkom jakości oraz operacyjnej walidacji gotowości rollout.
- [x] Ułatwiono skalowanie pracy zespołu: mniej wyjątków ad-hoc, bardziej jednolite procesy i szybsze przekazywanie odpowiedzialności między rolami.

### 🚧 v1.9 (planowane detale)
- [ ] Odpytywanie w tle dla GitHub Issues.
- [ ] Panel dashboardu dla integracji zewnętrznych.
- [ ] Rekurencyjne streszczanie długich dokumentów.
- [ ] Cache wyników wyszukiwania.
- [ ] Walidacja i optymalizacja planu (UX).
- [ ] Lepsze odzyskiwanie po błędach end-to-end.

### 🔮 v2.0 (w przyszłości)
- [ ] Obsługa webhooków GitHub.
- [ ] Integracja MS Teams.
- [ ] Weryfikacja wieloźródłowa.
- [ ] Integracja Google Search API.
- [ ] Równoległe wykonanie kroków planu.
- [ ] Cache planów dla podobnych zadań.
- [ ] Integracja GraphRAG.


### Konwencje
- Kod i komentarze: polski lub angielski.
- Wiadomości commitów: Conventional Commits (`feat`, `fix`, `docs`, `test`, `refactor`).
- Styl: Black + Ruff + isort (automatyczne przez pre-commit).
- Testy: wymagane dla nowych funkcjonalności.
- Bramki jakości: SonarCloud musi przejść na PR.

## Zespół
- **Lider rozwoju:** mpieniak01.
- **Architektura:** Venom Core Team.
- **Współautorzy:** [Lista kontrybutorów](https://github.com/mpieniak01/Venom/graphs/contributors).

## Podziękowania
- Microsoft Semantic Kernel, Microsoft AutoGen, OpenAI / Anthropic / Google AI, pytest, społeczność Open Source.

---
**Venom** - *Autonomiczny system agentów AI dla następnej generacji automatyzacji*

## Licencja
Projekt jest udostępniany na licencji MIT. Zobacz plik [`LICENSE`](LICENSE).
Copyright (c) 2025-2026 Maciej Pieniak
