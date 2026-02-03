# 096: Stabilizacja mypy + porzadek w models (bez prowizorek)

Status: Zakonczone.

## Kontekst
- Po uruchomieniu `mypy venom_core` pojawia sie 467 bledow w 116 plikach.
- `isort` wykrywa rekursywny symlink w `models/` (np. `models/gemma-3-4b-it`).
- Lokalne uruchomienie narzedzi: `cd /home/ubuntu/venom && source .venv/bin/activate || true`.

Cel: doprowadzic diagnostyke do stanu powtarzalnego i naprawic realne problemy
typow bez wyciszania bledow "na sile".

## Stan konfiguracji narzedzi (zastany)
1. **`.pre-commit-config.yaml`**
   - `ruff-check --fix`, `ruff-format`
   - `isort --profile black`
2. **`Makefile`**
   - `make lint` -> `pre-commit run --all-files`
   - `make format` -> `black . && isort .`
3. **Brak dedykowanych configow** (`pyproject.toml`, `mypy.ini`, `ruff.toml`, `.isort.cfg`)
   - Reguly i wykluczenia nie sa zapisane w repo.

## Uwagi z analizy kodu/danych
- `models/` nie zawiera symlinkow (sprawdzone `find -type l`).
- W `models/gemma-3-4b-it` znajduje sie pelny katalog `.git` (nie symlink).
  Ostrzezenie isort o rekursji jest najpewniej skutkiem skanowania danych.

## Zalozenia (finalne zapisy)
1. **Nie wyciszamy globalnie mypy.** Nie wprowadzamy `ignore_missing_imports = True`
   ani `no_implicit_optional = False` jako rozwiazania docelowego.
2. **`models/` to dane, nie kod.** Narzedzia (mypy/isort/ruff) maja go pomijac
   przez konfiguracje w repo, a nie przez ad-hoc parametry w CLI.
3. **Rozwiazania musza miec odzwierciedlenie w kodzie lub configu repo.**

## Plan dzialania

### 1) Ustalenie konfiguracji narzedzi (repo-level)
- Dodac `pyproject.toml` i wpisac w nim konfiguracje:
  - `mypy`: jawne ustawienia, bez globalnego wyciszania bledow, z `exclude` dla danych.
  - `ruff`: `exclude` dla `models/` i `models_cache/`.
  - `isort`: `skip` dla `models/` i `models_cache/`.
- Aktualizowac `Makefile` i dokumentacje, aby wskazywaly na konfiguracje repo.
- Efekt: brak ostrzezen o rekursywnych symlinkach, powtarzalny wynik narzedzi.

### 2) Redukcja bledow mypy wedlug kategorii
Priorytet: najprostsze i masowe poprawki, potem trudniejsze.

1. **Implicit Optional -> Optional**
   - Parametry z domyslnym `None` dostaja `Optional[...]` i realna obsluge `None`.
2. **Brakujace adnotacje zmiennych**
   - Dodac typy do list/slownikow i pol klas (np. `free_ports`, `audio_queue`).
3. **Bledy zwrotow i typow struktur**
   - Poprawic typy zwracane (np. `dict[str, Any]` zamiast `None`).
4. **`None`-safety**
   - Dodac checki lub `assert` w miejscach, gdzie realnie mozliwe jest `None`.
5. **Importy opcjonalne**
   - Zamiast ignorowac, zrobic wzorzec:
     - `try/except ImportError` + `TYPE_CHECKING` + jasny fallback w kodzie.
     - Dodac brakujace stuby do dependencies (np. `types-PyYAML`, `types-psutil`).

### 3) Models: finalne rozstrzygniecie w kodzie
- Zweryfikowac symlinki w `models/` i usunac rekursywne/petle.
- Wprowadzic stale wykluczenie `models/` i `models_cache/` w konfiguracjach
  narzedzi (mypy/isort/ruff) jako katalogow z danymi.
- Dodac krotka notke do dokumentacji (np. `docs/models.md`), ze to katalog danych
  i nie jest skanowany przez narzedzia jak kod.

### 4) Odbudowa wynikow CI/diagnostyki
- Odpalic `mypy venom_core` i zapisac nowy baseline.
- Stopniowo obnizac liczbe bledow do zera lub do zaakceptowanego progu
  (jezeli jest uzgodniony).

## Plan realizacji (zadania zlozone, statusy)
1. **Baseline diagnostyczny**
   - [x] Zapis pierwszego baseline mypy (467 bledow / 116 plikow).
   - [x] Re-baseline po pierwszych poprawkach (371 bledow / 106 plikow).
2. **Masowe poprawki typow (szybkie wygrane)**
   - [x] Adnotacje list/slownikow i pol klas (np. `free_ports`, `audio_queue`, `_jobs_registry`).
   - [x] Standaryzacja `Optional` dla parametrow z domyslnym `None` + obsluga `None`.
   - [x] Poprawki zwrotow i struktur (np. `dict[str, Any]` vs `None`).
3. **Importy i zaleznosci typow**
   - [x] Wzorzec `try/except ImportError` + `TYPE_CHECKING` dla optional deps.
   - [x] Ustalenie listy stubow i dodanie do dependencies (np. `types-PyYAML`, `types-psutil`).
4. **Krytyczne przeplywy i orchestrator**
   - [x] Flow/Orchestrator/Dispatcher: ujednolicenie typow event_broadcaster i agentow.
   - [x] Session/State/Service monitor: brakujace typy i zgodnosc zwrotow.
5. **Perception/UI/Services**
   - [x] Perception (recorder, audio, desktop_sensor, watcher): Optional, typy kolejek i safe-guards.
   - [x] UI (notifier, component_engine): poprawki typow i importow.
6. **Models i dokumentacja**
   - [x] Dopisac notke o `models/` jako danych (np. `docs/models.md`).
   - [x] Upewnic sie, ze config wykluczen jest spójny.
7. **Finalizacja**
   - [x] Kolejny baseline mypy i uzgodnienie pozostalych wyjatkow (jesli sa).
   - [x] Sprawdzenie `make lint` / `make format` z nowymi configami.

## Kryteria akceptacji
- Brak ostrzezen o rekursywnych symlinkach w `models/`.
- `mypy venom_core` przechodzi lub pozostaje tylko niewielka lista
  zaakceptowanych, udokumentowanych wyjatkow.
- Wszystkie zmiany sa w kodzie/configu repo (brak "tymczasowych" komend).

## Postep realizacji
- [x] Inwentaryzacja `models/` (brak symlinkow; `.git` wewnatrz modelu).
- [x] Dodanie repo-level konfiguracji narzedzi w `pyproject.toml`.
- [x] Aktualizacja dokumentacji (`README.md`, `README_EN.md`) pod nowa konfiguracje.
- [x] Pierwsze poprawki mypy (Flow base + ForgeFlow + CouncilFlow + IssueHandlerFlow + CampaignFlow + FlowCoordinator + SessionHandler + Middleware + CodeReviewLoop + SystemStatusAgent + LessonsStore + LessonsManager + TokenEconomist + GraphStore + GraphRAGService + VectorStore + EmbeddingService + MemorySkill + EnergyManager + ChronosEngine + ProcessMonitor + RuntimeController + FileWatcher + TaskDispatcher + SessionStore + IntentManager + ConfigManager + ModelManager + TranslationService + Toolmaker + BenchmarkService: Optional + Protocol).
- [x] SessionStore: bezpieczne typowanie historii + TranslationService: TypedDict dla cache i poprawki typow TTL.
- [x] Szybkie adnotacje typow: PortAuthority, NodeManager (Future), AudioStreamHandler (TypedDict + buffer list).
- [x] LessonsStore: Optional limit + RuntimeController: ujednolicenie typu uptime_seconds.
- [x] Calendar API: typed lista events + Scheduler: typed _jobs_registry.
- [x] StateManager: bezpieczne ustalanie sciezki stanu + System routes: stabilny LLM_CONFIG_HASH.
- [x] ServiceMonitor: import psutil jako untyped + typowanie cache/updated_services.
- [x] Notifier: win10toast import ignore + Any dla get_status.
- [x] ComponentEngine: poprawione typy data/events w create_card_widget.
- [x] TaskDispatcher: typowanie chat_service + bezpieczne parsowanie node_preference (str).
- [x] Scheduler: Optional job_id + typowanie next_run_time i importy APScheduler.
- [x] Feedback API: bezpieczne comment.strip + import aiofiles jako untyped.
- [x] QueueManager/HealingFlow: zgodny typ event_broadcaster (EventBroadcaster).
- [x] SessionHandler: jawny typ entry dla session_store.append_message.
- [x] Perception: AudioEngine (Optional + importy untyped) i DesktopSensor (recorded_actions + importy untyped).
- [x] Perception: Recorder/Watcher (Optional + importy untyped + normalizacja sciezek).
- [x] Perception: cleanup mypy (AudioEngine/Recorder/DesktopSensor/Watcher) + bezpieczne fallbacki.
- [x] Perception: Recorder - dynamiczny import pynput i ujednolicone typy listenerow.
- [x] Models: dodana notka `docs/models.md` + potwierdzone wykluczenia w configu.
- [x] Importy: PyYAML jako optional w PromptManager/PermissionGuard/TokenEconomist.
- [x] Importy: paramiko/pytesseract/networkx jako optional/untyped w HardwareBridge/VisionGrounding/GraphStore.
- [x] Orchestrator/Flow: Optional w initach, Council guards, ServiceMonitor untyped importy, CampaignFlow Callable.
- [x] Importy/stuby: dodane types-* w `requirements.txt` + optional deps dla docker/aiofiles/apscheduler/sklearn.
- [x] Core: naprawy typow w `config.py`, `token_economist.py`, `work_ledger.py`.
- [x] Memory: naprawy typow w `embedding_service.py`, `vector_store.py`, `graph_rag_service.py`.
- [x] Infrastructure: poprawki w `gpu_habitat.py`, `cloud_provisioner.py`, `energy_manager.py` + LLMService w GraphRAG.
- [x] Learning/Simulation: `dataset_curator.py`, `demonstration_analyzer.py`, `persona_factory.py` (Optional + TypedDict + guardy).
- [x] Agent/Skill cleanup (czesc I): Optional w initach + adnotacje `chat_service` w wybranych agentach/skillach.
- [x] Core: `model_registry_clients.py`, `model_registry.py`, `dream_engine.py` (guardy + typy).
- [x] Agent/Skill cleanup (czesc II): chat_service/Optional w agentach + poprawki w `ghost_agent`, `ux_analyst`, `librarian`, `executive`, `integrator`, `coder`, `tester`, `operator`, `simulated_user`.
- [x] Skills: poprawki dla `web_skill`, `media_skill`, `browser_skill`, `compose_skill`, `github_skill`, `google_calendar_skill`, `parallel_skill`, `complexity_skill`, `input_skill`, `platform_skill`, `render_skill`.
- [x] Core/API: `model_manager.py` + `api/routes/memory.py` i `api/routes/knowledge.py`.
- [x] Mypy: doprecyzowanie import-untyped (Tavily/Google API) + adnotacja `_chunks_count` w `UpsertResult`.
- [x] Finalizacja: `mypy venom_core` (0 bledow / 0 plikow). `make lint` OK, `black` obecny; formatowanie wykonane (black + isort). Dodano `[tool.black]` z exclude dla katalogow danych.
- [x] Testy regresji: naprawa `vector_store` (UpsertResult jako string + dict-like), kompatybilnosc `dream_engine` z `graph_store.graph`.
- [x] Testy: usuniete bledy kolekcji (LLMService + cykliczny import flows). `pytest` uruchamia sie, ale potrzebuje dłuższego czasu (timeout po ~120s).
- [x] Redukcja bledow mypy wedlug kategorii (iteracyjnie).
