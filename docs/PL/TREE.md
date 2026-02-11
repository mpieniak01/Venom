~/venom                          # ROOT projektu Venom (repo)
├── .venv/                       # środowisko wirtualne Pythona
├── .env                         # konfiguracja / sekrety (poza Gitem)
├── requirements.txt             # zależności VENOM
├── README.md                    # opis projektu (może być pusty na start)
│
├── docs/                        # dokumentacja (angielska, domyślna)
│   ├── PL/                      # dokumentacja po polsku
│   ├── PROCESS_ENGINE_CONCEPT.md # [v2.0] System procesowy (koncepcja)
│   ├── SECURITY_POLICY.md       # oficjalna polityka bezpieczeństwa runtime i autonomii
│   ├── VENOM_DIAGRAM.md
│   └── VENOM_MASTER_VISION_V1.md
├── docs_dev/                    # dokumentacja deweloperska lokalnie (ignorowana)
│   ├── _backlog/
│   ├── _done/
│   └── _to_do/
│
├── data/                        # dane runtime (nie kod)
│   └── memory/
│       └── lessons_learned.json # pamięć błędów / wniosków
│
├── web-next/                    # Next.js Dashboard (aktywny frontend w v1.0)
│   ├── app/                     # App Router
│   ├── components/              # komponenty React/Shadcn UI
│   ├── lib/                     # utils, types, api clients
│   └── public/                  # static assets
│
├── tests/                       # testy (API, core, itd.)
│   ├── __init__.py
│   └── test_healthz.py          # np. test endpointu /healthz
│
├── logs/                        # logi Venoma
│   └── venom.log                # (tworzone przez logger, nie ręcznie)
│
├── workspace/                   # roboczy katalog na pliki, które Venom tworzy/obrabia
│
├── scripts/                     # narzędzia CLI / pomocnicze skrypty
│   └── genesis.py               # skrypt do tworzenia struktury (GENESIS)
│
└── venom_core/                  # pakiet Pythona – organizm Venoma
    ├── __init__.py
    ├── main.py                  # FastAPI, /healthz, / (UI), spinanie warstw
    ├── config.py                # Settings (Pydantic): ścieżki, modele, ENV
    │
    ├── core/                    # [WARSTWA 1: META] – MÓZG
    │   ├── __init__.py
    │   ├── orchestrator.py      # cykl życia zadania (Orchestrator pipeline)
    │   ├── intent_manager.py    # klasyfikacja intencji (code/research/arch)
    │   ├── policy_engine.py     # etyka, autonomia, poziomy domen
    │   ├── state_manager.py     # stan organizmu, log zadań
    │   ├── model_registry.py    # rejestr modeli (Ollama + HF Hub)
    │   ├── model_manager.py     # lifecycle, wersjonowanie i aktywacja modeli lokalnych
    │   ├── model_router.py      # routing między LLM lokalnym a chmurą
    │   ├── llm_server_controller.py # zarządzanie serwerami LLM (Ollama/vLLM)
    │   ├── prompt_manager.py    # zarządzanie template'ami promptów
    │   ├── service_monitor.py   # monitorowanie usług systemowych (status, CPU/RAM)
    │   ├── tracer.py            # RequestTracer (śledzenie kroków i mermaid)
    │   └── dream_engine.py      # [v2.0] System aktywnego śnienia (przesunięty)
    │
    ├── agents/                  # [WARSTWA 2: AGENT SERVICES] – SPECJALIŚCI
    │   ├── __init__.py
    │   ├── architect.py         # planowanie architektury
    │   ├── librarian.py         # struktura repo / plików
    │   ├── coder.py             # generacja kodu
    │   ├── strategist.py        # [v2.0] Strategy Supervisor (Roadmap, KPI)
    │   ├── critic.py            # testy / review
    │   ├── documenter.py        # generowanie dokumentacji
    │   ├── publisher.py         # release notes i publikacja
    │   ├── ghost_agent.py       # wizualna automatyzacja GUI
    │   ├── apprentice.py        # nauka przez obserwację
    │   ├── professor.py         # system edukacji użytkownika
    │   └── oracle.py            # analiza grafu wiedzy (GraphRAG)
    │
    ├── execution/               # [WARSTWA 3: RĘCE] – Semantic Kernel / tools
    │   ├── __init__.py
    │   ├── kernel_builder.py    # konfiguracja SK, rejestracja skills
    │   └── skills/
    │       ├── __init__.py
    │       ├── file_skill.py    # operacje na plikach (safe I/O)
    │       ├── shell_skill.py   # komendy w sandboxie
    │       └── git_skill.py     # obsługa gita (status/diff/commit)
    │
    ├── skills/                  # [WARSTWA 3: NARZĘDZIA MCP] – import z Git (MCP)
    │   ├── mcp_manager_skill.py # zarządzanie importem MCP
    │   ├── mcp/
    │   │   ├── proxy_generator.py # generator proxy MCP
    │   │   └── _repos/            # klony repozytoriów MCP (runtime)
    │   └── custom/              # generowane wrappery MCP (runtime; może pojawić się po pierwszym imporcie)
    │
    ├── perception/              # [WARSTWA 3: ZMYSŁY] – OCZY + ANTENA
    │   ├── __init__.py
    │   ├── eyes.py              # modele vision (Ollama / OpenAI) [Florence-2 v2.0]
    │   ├── audio_engine.py      # silnik audio (Whisper STT + Piper TTS)
    │   └── antenna.py           # web search, scraping
    │
    ├── memory/                  # [WARSTWA 5: HIPOKAMP] – PAMIĘĆ
    │   ├── __init__.py
    │   ├── graph_store.py       # integracja z GraphRAG
    │   ├── vector_store.py      # LanceDB / inne wektorowe storage
    │   └── lessons_store.py     # API do data/memory/lessons_learned.json
    │
    ├── infrastructure/          # [WARSTWA 4: METABOLIZM] – SILNIKI
    │   ├── __init__.py
    │   ├── docker_habitat.py    # zarządzanie kontenerami / sandboxami
    │   ├── message_broker.py    # Redis + ARQ (Hive)
    │   └── hardware_pi.py       # most do Rider-Pi (API, heartbeat)
    │
    └── utils/                   # NARZĘDZIA WSPÓLNE
        ├── __init__.py
        ├── logger.py            # konfiguracja Loguru/Rich
        └── helpers.py           # drobne helpery (ID, czas, konwersje, itd.)
