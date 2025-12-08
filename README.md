# Venom v2.0 🐍

**Venom Meta-Intelligence System** - Autonomiczny system agentów AI z warstwą planowania strategicznego i ekspansją wiedzy.

## 🌟 Nowe w wersji 2.0: The Hive Mind

Venom został przekształcony z prostego wykonawcy poleceń w **autonomicznego inżyniera**, który potrafi:

### ✨ Kluczowe funkcjonalności

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

#### 4. **Visual Imitation Learning** (Uczenie przez Demonstrację) 🎓
- **DemonstrationRecorder** - Nagrywanie akcji użytkownika (mysz, klawiatura, zrzuty ekranu)
- **DemonstrationAnalyzer** - Analiza behawioralna i transformacja pikseli → semantyka
- **WorkflowStore** - Magazyn procedur z możliwością edycji
- **Integration z GhostAgent** - Wykonywanie wygenerowanych workflow

#### 5. **Orchestration** (Orkiestracja)
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
- `openai` / `anthropic` / `google-generativeai` - Modele LLM (opcjonalne)

Pełna lista w [requirements.txt](requirements.txt)

### Konfiguracja

Stwórz plik `.env`:

```bash
# LLM Configuration
LLM_SERVICE_TYPE=local              # Opcje: local, openai, azure
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1  # Ollama/vLLM
LLM_MODEL_NAME=phi3:latest

# Opcjonalne (dla chmurowych modeli)
OPENAI_API_KEY=your_key_here

# External Integrations (NEW v2.0)
GITHUB_TOKEN=ghp_your_token         # Personal Access Token
GITHUB_REPO_NAME=username/repo      # Nazwa repozytorium
DISCORD_WEBHOOK_URL=https://...     # Opcjonalne
ENABLE_ISSUE_POLLING=false          # Włącz auto-polling Issues
```

📖 **Dokumentacja integracji zewnętrznych:** [docs/EXTERNAL_INTEGRATIONS.md](docs/EXTERNAL_INTEGRATIONS.md)

### Uruchomienie

```bash
# Uruchom serwer
uvicorn venom_core.main:app --reload

# Lub użyj make
make run
```

## 📖 Dokumentacja

- [Kompletna dokumentacja zadania 007](docs/_done/007_THE_HIVE_MIND_COMPLETED.md)
- [Architektura systemu](docs/VENOM_MASTER_VISION_v2.md)
- [System rozpoznawania intencji](docs/INTENT_RECOGNITION.md)
- [Contributing Guide](docs/CONTRIBUTING.md)

## 🧪 Testy

```bash
# Uruchom wszystkie testy
pytest

# Testy specyficzne
pytest tests/test_web_skill.py
pytest tests/test_researcher_agent.py
pytest tests/test_architect_agent.py
pytest tests/test_planning_integration.py

# Z pokryciem
pytest --cov=venom_core --cov-report=html
```

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
export SPORE_NEXUS_HOST=192.168.1.10
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
