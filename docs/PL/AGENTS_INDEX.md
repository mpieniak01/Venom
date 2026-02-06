# Indeks Agentów Venom - Pełna Lista

## Przegląd

> **[English Version](../AGENTS_INDEX.md)**

System Venom składa się z 34 wyspecjalizowanych agentów, każdy odpowiedzialny za konkretny obszar funkcjonalności. Poniżej znajdziesz pełną listę z opisami i linkami do szczegółowej dokumentacji.

## Standardy jakości dla kodu agentów

- Zmiany w agentach powinny przechodzić CI Lite na PR (szybki lint + wybrane testy unit).
- SonarCloud działa jako obowiązkowa bramka jakości dla PR.
- Snyk jest uruchamiany okresowo do monitorowania ryzyk w zależnościach i kontenerach.
- Rozszerzając agentów, utrzymuj czytelną logikę i typowanie (`mypy venom_core` powinno być zielone).
- Unikaj martwych gałęzi/placeholderów; ścieżki błędów mają być jawne i testowalne.

## Kategorie Agentów

### 🏗️ Planowanie i Architektura

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Architect** | `architect.py` | [THE_ARCHITECT.md](THE_ARCHITECT.md) | Planowanie strategiczne, dekompozycja złożonych zadań |
| **Strategist** | `strategist.py` | [THE_STRATEGIST.md](THE_STRATEGIST.md) | [v2.0] Ocena złożoności, zarządzanie budżetem API |
| **Executive** | `executive.py` | [THE_EXECUTIVE.md](THE_EXECUTIVE.md) | Orkiestracja na wysokim poziomie, decision-making |

### 💻 Implementacja i Kod

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Coder** | `coder.py` | [THE_CODER.md](THE_CODER.md) | Generowanie kodu, Docker Compose, samonaprawa |
| **Critic** | `critic.py` | [THE_CRITIC.md](THE_CRITIC.md) | Weryfikacja jakości i bezpieczeństwa kodu |
| **Toolmaker** | `toolmaker.py` | [THE_FORGE.md](THE_FORGE.md) | Tworzenie nowych Skills/narzędzi |

### 📚 Wiedza i Badania

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Researcher** | `researcher.py` | [THE_RESEARCHER.md](THE_RESEARCHER.md) | Wyszukiwanie w Internecie, synteza wiedzy |
| **Librarian** | `librarian.py` | [THE_LIBRARIAN.md](THE_LIBRARIAN.md) | Zarządzanie plikami, nawigacja po projekcie |
| **Oracle** | `oracle.py` | [ORACLE_GRAPHRAG_GUIDE.md](ORACLE_GRAPHRAG_GUIDE.md) | GraphRAG, analiza wiedzy projektowej |
| **Historian** | `historian.py` | - | Historia projektu, tracking zmian |

### 🤖 Interakcja z Użytkownikiem

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Chat** | `chat.py` | [THE_CHAT.md](THE_CHAT.md) | Asystent konwersacyjny, pytania ogólne |
| **Apprentice** | `apprentice.py` | [THE_APPRENTICE.md](THE_APPRENTICE.md) | Uczenie przez obserwację, nagrywanie workflows |
| **Professor** | `professor.py` | [THE_ACADEMY.md](THE_ACADEMY.md) | Edukacja użytkownika, wyjaśnienia koncepcji |

### 🎨 Kreatywność i Design

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Creative Director** | `creative_director.py` | - | Branding, marketing, prompty do AI art |
| **Designer** | `designer.py` | - | Design UI/UX, prototypy |
| **UX Analyst** | `ux_analyst.py` | - | Analiza doświadczenia użytkownika |

### 🔧 DevOps i Infrastruktura

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Integrator** | `integrator.py` | [THE_INTEGRATOR.md](THE_INTEGRATOR.md) | Git, GitHub Issues, Pull Requesty |
| **DevOps** | `devops.py` | - | CI/CD, deployment, monitoring |
| **System Engineer** | `system_engineer.py` | - | Konfiguracja systemowa, infrastruktura |
| **Operator** | `operator.py` | - | Operacje runtime, maintenance |
| **Release Manager** | `release_manager.py` | [THE_LAUNCHPAD.md](THE_LAUNCHPAD.md) | Zarządzanie wydaniami, CHANGELOG |

### 🧪 Testowanie i Jakość

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Tester** | `tester.py` | - | Generowanie testów jednostkowych i integracyjnych |
| **Guardian** | `guardian.py` | [GUARDIAN_GUIDE.md](GUARDIAN_GUIDE.md) | Bezpieczeństwo, weryfikacja w sandbox |
| **Analyst** | `analyst.py` | - | Analiza wydajności, metryki, koszty |

### 📝 Dokumentacja i Porządkowanie

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Documenter** | `documenter.py` | - | Generowanie dokumentacji, docstringi |
| **Gardener** | `gardener.py` | - | Refaktoryzacja, clean-up kodu |
| **Foreman** | `foreman.py` | - | Zarządzanie zadaniami budowlanymi projektu |
| **Publisher** | `publisher.py` | - | Publikacja artefaktów, release notes |
| **Writer** | - | - | *[Wycofany/Zintegrowany z CreativeDirector]* |

### 🤝 Integracje Zewnętrzne

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Integrator** | `integrator.py` | [EXTERNAL_INTEGRATIONS.md](EXTERNAL_INTEGRATIONS.md) | Integracje zewnętrzne (GitHub, Discord/Slack, Tavily, HF, Calendar) |
| **Simulated User** | `simulated_user.py` | - | Symulacja użytkownika dla testów E2E |
| **Ghost Agent** | `ghost_agent.py` | [GHOST_AGENT.md](GHOST_AGENT.md) | Automatyzacja GUI (RPA) |
| **Shadow** | `shadow.py` | [THE_SHADOW.md](THE_SHADOW.md) | Desktop awareness, proaktywna pomoc |

### ⏰ Czas i Monitoring

| Agent | Plik | Dokumentacja | Opis |
|-------|------|--------------|------|
| **Time Assistant** | `time_assistant.py` | [THE_CHRONOMANCER.md](THE_CHRONOMANCER.md) | Zarządzanie czasem, harmonogramy |
| **System Status** | `system_status.py` | [THE_OVERMIND.md](THE_OVERMIND.md) | Monitoring stanu systemu, health checks |

### 🌐 Architektura Rozproszona

| Koncepcja | Dokumentacja | Opis |
|-----------|--------------|------|
| **The Hive** | [THE_HIVE.md](THE_HIVE.md) | Architektura rozproszona z Redis |
| **The Nexus** | - | Master-worker mesh, distributed execution |
| **The Council** | [THE_COUNCIL.md](THE_COUNCIL.md) | Zarządzanie kolektywne, consensus |

## Agenci bez Dedykowanej Dokumentacji

Poniżsi agenci istnieją w kodzie ale nie mają jeszcze dedykowanych plików dokumentacji (15 z 33):

- **Analyst** (`analyst.py`) - Analiza wydajności i kosztów
- **Creative Director** (`creative_director.py`) - Branding i marketing
- **Designer** (`designer.py`) - Design UI/UX
- **DevOps** (`devops.py`) - CI/CD i deployment
- **Documenter** (`documenter.py`) - Generowanie dokumentacji
- **Foreman** (`foreman.py`) - Zarządzanie zadaniami budowlanymi
- **Gardener** (`gardener.py`) - Refaktoryzacja i clean-up
- **Historian** (`historian.py`) - Historia projektu
- **Integrator** (`integrator.py`) - Integracje zewnętrzne (GitHub/Discord/Slack/Tavily/HF/Calendar)
- **Operator** (`operator.py`) - Operacje runtime
- **Publisher** (`publisher.py`) - Publikacja artefaktów
- **Simulated User** (`simulated_user.py`) - Symulacja użytkownika
- **System Engineer** (`system_engineer.py`) - Konfiguracja systemowa
- **Tester** (`tester.py`) - Generowanie testów
- **UX Analyst** (`ux_analyst.py`) - Analiza UX

## Jak Wybrać Odpowiedniego Agenta?

### Chcę...

**Napisać kod** → **Coder** + **Critic** (review)
**Znaleźć informacje** → **Researcher** (Internet) lub **Librarian** (pliki lokalne)
**Zaplanować projekt** → **Architect** (plan) + **Strategist** (ocena złożoności)
**Stworzyć nowe narzędzie** → **Toolmaker** (THE_FORGE)
**Zarządzać repozytorium** → **Integrator** (Git, PR, Issues)
**Porozmawiać** → **Chat** (pytania ogólne)
**Automatyzować GUI** → **Ghost Agent** (RPA)
**Testować** → **Tester** (generowanie) + **Guardian** (sandbox)
**Dokumentować** → **Documenter** (docstringi) + **Publisher** (release notes)
**Nauczyć system** → **Apprentice** (nagrywanie workflows)

## Przepływy Pracy (Workflows)

### 1. Złożony Projekt (E2E)
```
User Request → IntentManager (COMPLEX_PLANNING)
            → Architect (plan: 5 steps)
            → Strategist (estimate: COMPLEX, 3h)
            → Researcher (find docs)
            → Coder (implement)
            → Critic (review)
            → Tester (generate tests)
            → Guardian (sandbox verify)
            → Integrator (commit, PR)
```

### 2. Proste Pytanie
```
User: "Jaka jest stolica Francji?"
→ IntentManager (GENERAL_CHAT)
→ Chat Agent
→ Odpowiedź: "Paryż"
```

### 3. Nowe Narzędzie
```
User: "Dodaj możliwość sprawdzania pogody"
→ Architect detects missing tool
→ Toolmaker creates WeatherSkill
→ Critic reviews code
→ SkillManager loads skill
→ System: "Skill załadowany. Możesz używać get_weather()"
```

## Metryki Systemu Agentów

**Ogólne statystyki:**
- Liczba agentów: **34**
- Z dokumentacją `THE_*.md` lub dedykowanymi plikami: **21** (62%)
- Bez dokumentacji: **13** (38%)
- Kategorie: **10**

**Najbardziej używane:**
1. **Coder** - Generowanie kodu
2. **Chat** - Rozmowy z użytkownikiem
3. **Researcher** - Wyszukiwanie informacji
4. **Architect** - Planowanie projektów
5. **Integrator** - Git i GitHub

## Zobacz też

- [VENOM_MASTER_VISION_V1.md](VENOM_MASTER_VISION_V1.md) - Wizja systemu
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Architektura backendu
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - Klasyfikacja intencji
- [THE_HIVE.md](THE_HIVE.md) - Architektura rozproszona
