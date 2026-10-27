# Audyt grupy long przed pomiarem

Odczytowy przegląd plików `config/pytest-groups/long.txt` i najważniejszych
wywoływanych helperów. Stan grupy w trakcie zmian: 43 pliki. Nie uruchomiono
fizycznych testów, modeli, kontenerów ani usług w celu tego audytu.

Obserwacja kodu lub obecność `MagicMock` nie jest dowodem, że wszystkie ścieżki
pliku i zależności tranzytywne są bezpieczne. Poniższa kolumna „pozostaje do
sprawdzenia” oznacza `unknown`; nie klasyfikujemy jej jako symulowanej wyłącznie
na podstawie nazwy. Rzeczywisty zestaw do pomiaru zależy od filtrów, markerów,
środowiska i pominiętych przypadków; należy go zapisać razem z czasem grupy.

## Istotne warunki przed pomiarem

- `test_rag_integration.py` tworzy `EmbeddingService(service_type="local")`,
  którego `_ensure_model_loaded` wywołuje prawdziwy `SentenceTransformer`.
  Cały plik jest oznaczony `unsafe_direct_runtime`; import opcjonalnych bibliotek
  został przeniesiony do fixture po kwalifikacji. Żadne opcje live/integration
  nie powinny zdejmować tego bloku.
- Dwa scenariusze generowania Forge zostały przeniesione do `test_forge_live.py`
  i mają `unsafe_direct_runtime`. Pozostały hot-reload jest testem oddzielnym.
- Dwa scenariusze natywnego Gemma audio przeniesiono z ROI do
  `test_audio_stream_live.py`, który nie należy do grupy long. Marker
  `unsafe_direct_runtime` blokuje je również przy opt-in; jako dodatkową ochronę
  w pomiarze ustawić `GEMMA4_LIVE_AUDIO_TESTS=0`.
- `test_lesson_management_api.py` używa `TestClient(app)` z lifespan i wykonuje
  `purge(force=true)`, prune oraz toggle. Jest `integration` i jest pomijany bez
  `--run-integration`; do pełnego audytu izolacji danych nie uruchamiać go.
- `test_compose_integration.py` tworzy rzeczywiste kontenery; `requires_docker_compose`
  i ochrona live powodują pominięcie w zwykłym profilu symulowanym.
- `test_browser_skill.py` zawiera oznaczone integration wizyty w sieci, ale
  także nieoznaczone przypadki mogące wystartować Chromium. `visit_page` inicjuje
  przeglądarkę przed sprawdzeniem URL. Przestrzeń sieciowa ogranicza łączność,
  ale sama nie zapobiega startowi przeglądarki.
- `test_component_runtime.py`, `test_qualification_process.py` i
  `test_onnx_gpu_bridge.py` uruchamiają rzeczywiste własne procesy/wątki lub
  loopback fixtures; nie są to kolejne serwery Venom. Muszą pozostać we własnej
  przestrzeni i czyścić tylko swoje procesy. Przerwanie może zmienić wynik cleanup.
- `test_overmind_integration.py` i `test_planning_integration.py` tworzą
  rzeczywiste obiekty Orchestrator/MemorySkill, a pierwszy dodatkowo scheduler,
  watcher i gardener. Widziane atrapy i ścieżki tymczasowe nie dowodzą pełnej
  izolacji łańcucha inicjalizacji; traktować je jako unknown.

## Przegląd każdego pliku

| Plik | Zaobserwowane scenariusze i helpery | Pozostaje do sprawdzenia / warunek |
|---|---|---|
| `tests/test_compose_integration.py` | ComposeSkill/StackManager, prawdziwe redis/nginx i operacje Docker, workspace temp | Fizyczna infrastruktura; `requires_docker_compose`, bez live opt-in SKIP |
| `tests/integration/test_verify_backend.py` | Tworzy schemat HistoryRequestDetail i dane kontekstowe | Import route/dependencies jest szerszy od samego schematu; unknown |
| `tests/ollama_bench/test_common_and_scoreboard.py` | Parsowanie tekstu i agregacja; common.py zawiera także helper HTTP Ollamy | Widoczne testy nie wywołują helpera HTTP; importy i inne efekty unknown |
| `tests/ollama_bench/test_scheduler.py` | Tworzenie list zadań i podsumowań; scheduler.py importuje discover_models i subprocess | Widoczne przypadki wywołują helpery danych, nie scheduler benchmarku; unknown dla przyszłych zmian |
| `tests/test_agents_release_integration_contracts.py` | Kernel, Git i FileSkill głównie atrapy; część plików w tmp | Duży plik, nie wszystkie gałęzie/wywołania agentów i sprzątanie mkdtemp potwierdzone |
| `tests/test_agents_routes_integration_regression.py` | TestClient(FastAPI), atrapy usług i kernel; `integration` | Domyślnie SKIP bez opcji; pełny łańcuch route unknown |
| `tests/test_architecture_contracts_guard.py` | Uruchamia subprocess Python guard na danych w tmp_path | Realny proces; sprawdzić propagację środowiska i czas |
| `tests/test_audio_smoke_script.py` | AudioEngine, HTTP i transkrypcja zastąpione atrapami; sztuczne WAV/ONNX w tmp | Import scripts.dev.audio_smoke i pozostałe ścieżki unknown |
| `tests/test_audio_stream_handler_roi.py` | Mock websocket/engine i kontrakty audio; live Gemma wydzielono | Pozostałe liczne gałęzie i importy nie są w pełni zakwalifikowane |
| `tests/test_audit_lite_deps.py` | Uruchamia subprocess audytu na tymczasowych wymaganiach i testach | Realny proces; helper import-smoke wymaga osobnej kontroli przy użyciu |
| `tests/test_browser_skill.py` | Chromium, `visit_page` i screenshot; część przypadków z atrapą page | Nieoznaczone przypadki mogą uruchomić browser/sieć; `integration` skip tylko dla oznaczonych |
| `tests/test_component_runtime.py` | Prywatny HTTP child, faux daemon/uvicorn, tymczasowe PID/receipts; część systemctl to atrapa | Rzeczywiste procesy i sygnały do własnych child; kontrola zakończenia oraz sieć poza hostem |
| `tests/test_dependency_profiles.py` | Profile/locki w tmp i liczne atrapy; pojedynczy realny Python child do sprawdzenia env | Duży plik; dokładny zakres subprocessów i wpływ na środowisko unknown |
| `tests/test_external_discovery_integration.py` | GitHub i HfApi patchowane, odpowiedzi MagicMock | Importy i niewymienione ścieżki usług wymagają dalszej analizy |
| `tests/test_file_operations_integration.py` | FileSkill, workspace/state tempfile; patch runtime i dispatcher | Sprawdzić pełne zamykanie zadań Orchestratora i zależności `permission_guard` |
| `tests/test_forge_integration.py` | Pozostał hot-reload przykładowego skilla w TemporaryDirectory | `integration` domyślnie SKIP; dynamiczny import testowego skilla wymaga izolacji plików |
| `tests/test_forge_live.py` | Dwa scenariusze Toolmaker/KernelBuilder wymagają rzeczywistego LLM | `integration` + `unsafe_direct_runtime`; stały SKIP do bezpiecznego host admission |
| `tests/test_generation_params_integration.py` | Scenariusze KernelBuilder/model oraz kilka testów danych/adaptera | Cały plik `unsafe_direct_runtime`; jednostkowe przypadki też SKIP, warto wydzielić |
| `tests/test_ghost_agent_hil.py` | Tkinter i sterowanie desktopem; wymaga display i VENOM_GHOST_HIL | `manual_llm` + live; bez opt-in SKIP, nie wykonywać fizycznej automatyki w pomiarze |
| `tests/test_knowledge_memory_tasks_integration.py` | TestClient i atrapy orchestratora/store; tymczasowe podmiany sys.modules | `integration` SKIP domyślnie; ryzyko izolacji globalnych importów w workerze |
| `tests/test_lesson_management_api.py` | Prawdziwy app lifespan, purge/prune/toggle przez TestClient | `integration` SKIP domyślnie; izolacja danych i procesu nieudowodniona |
| `tests/test_light_release_installers.py` | Kopiuje skrypty do tmp, fake docker/curl/python, uruchamia bash/PTY | Realne subprocessy; `PATH` i env fixture muszą pozostać kontrolowane |
| `tests/test_module_observations.py` | Atrapy providerów, manifesty tmp, TestClient izolowanego FastAPI | Dynamiczne moduły/lifespan; nie wszystkie importy pomocnicze potwierdzone |
| `tests/test_motor_cortex_integration.py` | Atrapy intencji/dispatchera/model runtime, pliki state w tempfile | Tworzy rzeczywisty Orchestrator; domyślne MemorySkill i prace w tle unknown |
| `tests/test_onnx_gpu_bridge.py` | BridgeServer + TokenFixture, realny loopback na porcie 0, wątki i HTTP/SSE | Nie uruchamia OnnxEngine w pokazanej fixture; zakończenie wątków i inne ścieżki wymagają kontroli |
| `tests/test_orchestrator_council_integration.py` | CouncilConfig/CouncilSession, state i broadcaster jako atrapy | Inne importy i stan globalny unknown |
| `tests/test_overmind_integration.py` | Temp workspace; rzeczywisty scheduler/watcher/gardener i Orchestrator | Procesy/wątki tła oraz MemorySkill wymagają audytu pełnego lifecycle |
| `tests/test_planning_integration.py` | Mock kernel/odpowiedzi, StateManager i rzeczywisty Orchestrator | Domyślne MemorySkill, ścieżki stanu i asynchroniczne zadania unknown |
| `tests/test_policy_gate_integration.py` | Atrapy orchestratora/runtime, realny kod policy/audit | Globalny audit stream i skutek współdzielenia między testami unknown |
| `tests/test_profile_targets.py` | Profile i locki w tmp; atrapy subprocessów/bootstrap | Wszystkie warianty helperów i ich opcjonalne zależności do weryfikacji |
| `tests/test_qualification_process.py` | Rzeczywiste dziecko Python sleep; kontrola PID/identity i stop; pozostałe procesy atrapowane | Sprawdzać cleanup i odmowę sygnałów do cudzych procesów |
| `tests/test_rag_boost_integration.py` | Mock settings, orchestrator i LessonsManager; realna polityka retrievalu | Globalne singletony/cache i pozostałe importy unknown |
| `tests/test_rag_integration.py` | LanceDB w tmp; prawdziwy lokalny SentenceTransformer i embedding | `unsafe_direct_runtime`: wszystkie przypadki SKIP, również z live opt-in |
| `tests/test_routing_integration.py` | DummyRouter/governance, runtime metadata w SimpleNamespace | Część używa prawdziwej logiki governance; dalsze efekty unknown |
| `tests/test_security_scan.py` | Wiele skanerów i subprocessów zastępowanych atrapami; dane/tmp | Sprawdzić wszystkie przypadki przed uznaniem braku realnego skanowania sieci |
| `tests/test_sonar_change_scope_resolver.py` | Generuje katalogi testowe w tmp, mockuje selektor i git | Logika wspólna z bramką; dalsze ścieżki CLI unknown |
| `tests/test_source_distributions.py` | Locki/profile w tmp, `bootstrap.run` i kontrola miejsca mockowane | Symulowane instalacje; sprawdzić wszystkie helpery i możliwe importy |
| `tests/test_system_connections.py` | Atrapy managerów i TestClient; Journal zapisywany w tmp | Registry modułów i mechanizm hooków wymagają audytu zależności |
| `tests/test_system_routes_integration_regression.py` | TestClient dla routerów, atrapy zależności; `integration` | Domyślnie SKIP; efekty niezamockowanych gałęzi unknown |
| `tests/test_test_intelligence_report.py` | Subprocess raportu intelligence z JUnit/katalogiem w tmp | Realny proces; weryfikować ścieżkę wyjścia i brak użycia starego raportu |
| `tests/test_test_lane_contracts_guard.py` | Subprocess walidatora, tymczasowy katalog i grupy | Realny proces; kwalifikacja guardów zależy od jego danych wejściowych |
| `tests/test_traffic_control_integration.py` | Kontroler tokenów oraz FastAPI TestClient; brak prawdziwego HTTP w pokazanych scenariuszach | Globalne settings i wszystkie dalsze ścieżki pozostają unknown |
| `tests/test_vast_observation.py` | Atrapy transportu Vast i odpowiedzi httpx; kod limitu odczytu | Potwierdzić wszystkie ścieżki inicjalizacji klienta; nie używać rzeczywistych kluczy |

## Zakres tego audytu i dalsza praca

Przegląd objął każdy plik grupy i wybrane helpery bez ich wykonywania. Nie jest
pełnym dowodem wszystkich zależności tranzytywnych, izolacji subprocessów ani
kategoryzacją wszystkich 517 plików projektu. Inwentarz AST jest tylko pomocą
w szukaniu kandydatów i nie uwzględnia wszystkich dynamicznych wywołań.

Dla kwalifikacji pełnego long należy osobno potwierdzić izolację systemu plików,
procesów i portów, zestaw wykonanych nodeid, powody skipów oraz czasy. Pomiar
odfiltrowanego zestawu należy nazwać czasem tego właśnie zestawu; nie opisuje on
całej grupy, jeżeli przypadki fizyczne lub integracyjne zostały pominięte.
