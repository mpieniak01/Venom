~/venom                          # Venom project ROOT (repo)
├── .venv/                       # Python virtual environment
├── .env                         # configuration / secrets (outside Git)
├── requirements.txt             # VENOM dependencies
├── README.md                    # project description (can be empty on start)
│
├── docs/                        # vision, diagrams, notes
│   ├── _done/                   # Documentation of completed development tasks
│   ├── _to_do/                  # Documentation of development tasks to do
│   ├── PROCESS_ENGINE_CONCEPT.md # [v2.0] Process Engine (concept)
│   ├── VENOM_DIAGRAM.md
│   └── VENOM_MASTER_VISION_V1.md
│
├── data/                        # runtime data (not code)
│   └── memory/
│       └── lessons_learned.json # memory of errors / conclusions
│
├── web/                         # WEB layer (Venom UI)
│   ├── templates/
│   │   ├── base.html            # common layout
│   │   └── index.html           # dashboard / main view
│   └── static/
│       ├── css/
│       │   └── app.css          # styles
│       └── js/
│           └── app.js           # frontend logic
│
├── web-next/                    # [NEW] Next.js Dashboard (VENOM 1.0)
│   ├── app/                     # App Router
│   ├── components/              # React/Shadcn UI components
│   ├── lib/                     # utils, types, api clients
│   └── public/                  # static assets
│
├── tests/                       # tests (API, core, etc.)
│   ├── __init__.py
│   └── test_healthz.py          # e.g. /healthz endpoint test
│
├── logs/                        # Venom logs
│   └── venom.log                # (created by logger, not manually)
│
├── workspace/                   # working directory for files Venom creates/processes
│
├── scripts/                     # CLI tools / helper scripts
│   └── genesis.py               # script to create structure (GENESIS)
│
└── venom_core/                  # Python package – Venom organism
    ├── __init__.py
    ├── main.py                  # FastAPI, /healthz, / (UI), layer binding
    ├── core/                    # [LAYER 1: META] – BRAIN
    │   ├── __init__.py
    │   ├── orchestrator.py      # task lifecycle
    │   ├── intent_manager.py    # intent classification (code/research/arch)
    │   ├── config.py            # Settings (Pydantic): paths, models, ENV
    │   ├── policy_engine.py     # ethics, autonomy, domain levels
    │   ├── state_manager.py     # organism state, task log
    │   ├── model_registry.py    # model registry (Ollama + HF Hub)
    │   ├── llm_server_controller.py # LLM server management (Ollama/vLLM)
    │   └── dream_engine.py      # [v2.0] Active dreaming system (postponed)
    │
    ├── agents/                  # [LAYER 2: AGENT SERVICES] – SPECIALISTS
    │   ├── __init__.py
    │   ├── architect.py         # architecture planning
    │   ├── librarian.py         # repo / file structure
    │   ├── coder.py             # code generation
    │   ├── strategist.py        # [v2.0] Strategy Supervisor (Roadmap, KPI)
    │   ├── critic.py            # tests / review
    │   ├── writer.py            # documentation, logs, PR descriptions
    │   ├── ghost_agent.py       # visual GUI automation
    │   ├── apprentice.py        # learning by observation
    │   ├── professor.py         # user education system
    │   └── oracle.py            # knowledge graph analysis (GraphRAG)
    │
    ├── execution/               # [LAYER 3: HANDS] – Semantic Kernel / tools
    │   ├── __init__.py
    │   ├── kernel_builder.py    # SK configuration, skill registration
    │   └── skills/
    │       ├── __init__.py
    │       ├── file_skill.py    # file operations (safe I/O)
    │       ├── shell_skill.py   # commands in sandbox
    │       └── git_skill.py     # git handling (status/diff/commit)
    │
    ├── perception/              # [LAYER 3: SENSES] – EYES + ANTENNA
    │   ├── __init__.py
    │   ├── eyes.py              # vision models (Ollama / OpenAI) [Florence-2 v2.0]
    │   ├── audio_engine.py      # audio engine (Whisper STT + Piper TTS)
    │   └── antenna.py           # web search, scraping
    │
    ├── memory/                  # [LAYER 5: HIPPOCAMPUS] – MEMORY
    │   ├── __init__.py
    │   ├── graph_store.py       # GraphRAG integration
    │   ├── vector_store.py      # LanceDB / other vector storage
    │   └── lessons_store.py     # API to data/memory/lessons_learned.json
    │
    ├── infrastructure/          # [LAYER 4: METABOLISM] – ENGINES
    │   ├── __init__.py
    │   ├── docker_habitat.py    # container / sandbox management
    │   ├── message_broker.py    # Redis + ARQ (Hive)
    │   └── hardware_pi.py       # bridge to Rider-Pi (API, heartbeat)
    │
    └── utils/                   # COMMON TOOLS
        ├── __init__.py
        ├── logger.py            # Loguru/Rich configuration
        └── helpers.py           # small helpers (ID, time, conversions, etc.)
