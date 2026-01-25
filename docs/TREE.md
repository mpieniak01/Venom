~/venom                          # ROOT projektu Venom (repo)
├── .venv/                       # środowisko wirtualne Pythona
├── .env                         # konfiguracja / sekrety (poza Gitem)
├── requirements.txt             # zależności VENOM
├── README.md                    # opis projektu (może być pusty na start)
│
├── docs/                        # wizja, diagramy, notatki
│   ├── _done/                   # Dokumentacja zadan programistycznych zrealizowanych
│   ├── _to_do/                  # Dokumentacja zadan programistycznych do realizacji
│   ├── PROCESS_ENGINE_CONCEPT.md # [v2.0] System procesowy (koncepcja)
│   ├── VENOM_DIAGRAM.md
│   └── VENOM_MASTER_VISION_V1.md
│
├── data/                        # dane runtime (nie kod)
│   └── memory/
│       └── lessons_learned.json # pamięć błędów / wniosków
│
├── web/                         # warstwa WEB (UI Venoma)
│   ├── templates/
│   │   ├── base.html            # wspólny layout
│   │   └── index.html           # dashboard / widok główny
│   └── static/
│       ├── css/
│       │   └── app.css          # style
│       └── js/
│           └── app.js           # logika frontendu
│
├── web-next/                    # [NOWY] Next.js Dashboard (VENOM 1.0)
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
    │   ├── orchestrator.py      # cykl życia zadania
    │   ├── intent_manager.py    # klasyfikacja intencji (code/research/arch)
    │   ├── policy_engine.py     # etyka, autonomia, poziomy domen
    │   ├── state_manager.py     # stan organizmu, log zadań
    │   ├── model_registry.py    # rejestr modeli (Ollama + HF Hub)
    │   ├── llm_server_controller.py # zarządzanie serwerami LLM (Ollama/vLLM)
    │   └── dream_engine.py      # [v2.0] System aktywnego śnienia (przesunięty)
    │
    ├── agents/                  # [WARSTWA 2: AGENT SERVICES] – SPECJALIŚCI
    │   ├── __init__.py
    │   ├── architect.py         # planowanie architektury
    │   ├── librarian.py         # struktura repo / plików
    │   ├── coder.py             # generacja kodu
    │   ├── strategist.py        # [v2.0] Strategy Supervisor (Roadmap, KPI)
    │   ├── critic.py            # testy / review
    │   ├── writer.py            # dokumentacja, logi, opisy PR
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
