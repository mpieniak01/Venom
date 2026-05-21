# chat_operator - Instrukcja operatora czatu

## Cel

`chat_operator` to instrukcja operatorska dla workflow czatu w Venom. Oddziela ona zachowanie czatu, stan, toolsy, konfigurację i zarządzanie cyklem życia od ogólnego podręcznika operatora.

Używaj tego dokumentu, gdy potrzebujesz odpowiedzi operacyjnej na pytania:

- jakie powierzchnie czatu udostępnia Venom,
- jakie toolsy ma obsługiwać czat,
- gdzie leży konfiguracja czatu i sesji,
- jak zarządzać stanem runtime i sesji,
- jakie targety `make` są wspieranym panelem sterowania.

## Szybki start

Użyj tej sekwencji, gdy chcesz rozpocząć workflow Copilot chatu w Venom:

1. Uruchom local-first runtime:
   ```bash
   make local-first-start MODEL=qwen3.5:9b
   ```
2. Potwierdź, że runtime działa:
   ```bash
   make local-first-status
   ```
3. Użyj lokalnego lane Copilot dla zwykłej odpowiedzi:
   ```bash
   make local-first-codex MODEL=qwen3.5:9b PROMPT='Powiedz tylko OK.'
   ```
4. Użyj lane repo-truth, gdy odpowiedź musi odzwierciedlać aktualny stan repo:
   ```bash
   make local-first-repo-truth-agent MODEL=qwen3.5:9b PROMPT='Przeanalizuj stan repo i podaj kolejny krok.'
   ```
5. Jeśli potrzebujesz pełnego kontraktu runtime, przejdź do `CHAT_SESSION.md`.

Zasada praktyczna:

- `local-first-codex` do zwykłej rozmowy,
- `local-first-repo-truth-agent` gdy odpowiedź zależy od `git status` / `git diff`,
- dla Agent-mode w VS Code trzymaj lokalny kontrakt modeli (`chat.model=qwen3.5:9b`, `chat.utilityModel=qwen3:4b`),
- `CHAT_SESSION.md` gdy potrzebujesz routingu, sesji lub szczegółów cyklu życia.

## Troubleshooting Copilot Agent (surowy JSON zamiast wykonania narzedzia)

- Upewnij sie, ze `chat.tools.terminal.autoApprove` dopuszcza bezpieczne komendy read-only git (`git status`, `git diff --shortstat`, `git branch --show-current`, `git rev-parse --short HEAD`).

Objaw:

- odpowiedz czatu pokazuje JSON typu `{\"name\":\"run_command\", ...}` zamiast wyniku narzedzia.

Znaczenie:

- biezaca sesja czatu nie wykonuje realnej petli tool-call dla tego turnu/modelu/trybu.
- karty handoff w UI sa tylko sugestia po odpowiedzi; nie sa dowodem, ze subagent naprawde wystartowal.
- prawdziwa delegacja musi pojawic sie w Agent Debug Log / Chat Debug View jako event `agent` lub `runSubagent`, po ktorym wraca evidence.

Wymagana naprawa operatorska w sesji VS Code:

1. Upewnij sie, ze czat jest w trybie `Agent` (nie tylko Ask).
2. Otworz tools picker i wlacz wymagane narzedzia dla tego requestu.
3. Uzyj lokalnego kontraktu modeli dla Agent mode:
   - `chat.model=qwen3.5:9b`
   - `chat.utilityModel=qwen3:4b`
4. Dla intencji `sprawdz status git` stosuj `single-command policy`:
   - uruchom tylko `git status --short --branch` jeden raz,
   - nie uzywaj `/create-prompt`, `/explain` ani list wielu komend,
   - zwroc najpierw wynik komendy, potem maksymalnie jedna krotka linie nastepnego kroku.
5. Powtorz turn z jawnym poleceniem:
   - `Uzyj teraz handoffu do subagenta. Przekaz repo-truth do Venom Local-First Orchestrator i zwroc tylko evidence subagenta.`
6. Jesli dalej widzisz surowy JSON payload, otworz:
   - Agent Debug Log,
   - Chat Debug View,
   i sprawdz, czy realny tool-call zostal wywolany czy pominiety.

Gdy tool jest pomijany:

- traktuj turn jako `tool_unavailable_or_unsupported_session`;
- nie akceptuj pseudo-JSON komend jako poprawnego wyniku.

## Co obsługuje operator czatu

| Powierzchnia lub intencja | Co robi | Uwagi |
| --- | --- | --- |
| Chat Cockpit | Ogólna rozmowa z asystentem w UI | Domyślna powierzchnia konwersacyjna |
| `GENERAL_CHAT` | Odpowiedzi operacyjne, stan repo, API, docs, skrypty | Idzie do LLM, jeśli nie jest wymagany tool |
| Akcje pamięci | `recall()` i `memorize()` przez `MemorySkill` | Używane dla preferencji i trwałych faktów |
| Akcje kalendarza | `read_agenda()` i `schedule_task()` przez `GoogleCalendarSkill` | Opcjonalne, nie jest to główny temat czatu |
| Cykl życia sesji | Ciągłość, reset i utrwalanie sesji | Wykorzystuje `session_id` i pliki session store |
| Tryby czatu | `Direct`, `Normal`, `Complex` | Szczegóły routingu są w `CHAT_SESSION.md` |
| Higiena sesji | Zasady streszczeń i retencji pamięci | Model pamięci jest opisany w `MEMORY_IN_CHAT.md` |
| Repo analiza | `git status`, `git diff`, zakres kontraktu API | Domyślny przypadek użycia |
| Remodel dokumentacji i skryptów | Zmiana docs i skryptów pod kontrakt czatu | Preferowana forma pracy |

### Czego ten operator nie obsługuje

- generowania kodu i zmian w repo,
- researchu i web browsing,
- routingu slash tooli poza czatem,
- polityki release/deploy.

Domyślny zakres rozmowy to:

1. stan gałęzi git,
2. zakres kontraktu API,
3. analiza i przemodelowanie dokumentacji,
4. analiza i przemodelowanie skryptów,
5. dopiero potem reszta tematów pomocniczych.

Te obszary mają własne toolsy, agentów i dokumenty workflow.

## Kanoniczne odnośniki

- [THE_CHAT.md](THE_CHAT.md)
- [CHAT_SESSION.md](CHAT_SESSION.md)
- [TOOLS_USAGE_GUIDE.md](TOOLS_USAGE_GUIDE.md)
- [CONFIG_PANEL.md](CONFIG_PANEL.md)
- [RUNTIME_PROFILES.md](RUNTIME_PROFILES.md)
- [MEMORY_IN_CHAT.md](MEMORY_IN_CHAT.md)
- [PR240_ARTIFACT_INVENTORY.md](PR240_ARTIFACT_INVENTORY.md)

Te dokumenty zawierają szczegóły techniczne. Ten dokument jest operacyjnym punktem wejścia.

## Gdzie leży konfiguracja

### Stan sesji i UI

- `web-next/lib/session.tsx`
- `web-next/components/cockpit/cockpit-home.tsx`
- klucze `localStorage` przeglądarki:
  - `venom-session-id`
  - `venom-next-build-id`
  - `venom-backend-boot-id`

### Stan sesji i pamięci po stronie backendu

- `venom_core/core/orchestrator/session_handler.py`
- `venom_core/services/session_store.py`
- `data/memory/session_store.json`
- `data/memory/state_dump.json`
- `data/memory/lancedb`

### Toolsy czatu i konfiguracja runtime

- `venom_core/memory/memory_skill.py`
- `venom_core/execution/skills/google_calendar_skill.py`
- `venom_core/services/config_manager.py`
- `venom_core/services/runtime_controller.py`
- `config/chat_operator/venom_operator_tool_profile.json`
- `config/chat_operator/agent_state_registry.json`
- `.env`
- `.env.dev`
- `config/env-history/`

### Istotne klucze środowiskowe

- `AI_MODE`
- `LLM_LOCAL_ENDPOINT`
- `LLM_MODEL_NAME`
- `ENABLE_GOOGLE_CALENDAR`
- `GOOGLE_CALENDAR_CREDENTIALS_PATH`
- `GOOGLE_CALENDAR_TOKEN_PATH`
- `VENOM_CALENDAR_ID`
- `MEMORY_ROOT`

## Jak zarządzać runtime czatu

Środowisko local-first powinno być zarządzane przez jawne i powtarzalne targety `make`, a nie przez jednorazowe komendy shellowe.

### Cykl życia runtime

1. Start lokalnego runtime czatu:
   ```bash
   make local-first-start MODEL=qwen2.5-coder:7b
   ```
2. Sprawdź stan runtime:
   ```bash
   make local-first-status
   ```
3. Uruchom lokalny kanał Codex:
   ```bash
   make local-first-codex MODEL=qwen2.5-coder:7b PROMPT='Powiedz tylko OK.'
   ```
4. Uruchom lane agenta repo-truth-first (wstrzykuje realny preflight `git status`/`git diff` do promptu):
   ```bash
   make local-first-repo-truth-agent MODEL=qwen2.5-coder:7b PROMPT='Przeanalizuj stan repo i podaj kolejny krok.'
   ```
   - intencje repo-truth są teraz kierowane do execution-first lane Git, więc `sprawdz status git` ma zwracać evidence zamiast planu/listy komend.
5. Zwolnij pamięć modelu:
   ```bash
   make local-first-unload MODEL=qwen2.5-coder:7b
   ```
6. Zatrzymaj local-first runtime:
   ```bash
   make local-first-stop
   ```

### Walidacja i probki

1. Probe modeli do pracy z feedbackiem:
   ```bash
   make local-first-feedback-probe
   ```
2. Macierz stabilności tool-call:
   ```bash
   make local-first-tool-flake-probe
   ```
3. Diagnostyka lokalnego chatu:
   ```bash
   make local-first-chat-diagnostics
   ```
   - macierz można nadpisać przez `MODELS`, `CHANNELS`, `PROMPT_VARIANTS`, `IGNORE_RULES`
   - `SHELL_ONLY=1` uruchamia prosty baseline repo bez wywołań modeli
4. Probe higieny outputu Copilot (wykrywanie wycieku surowego JSON tool-call do odpowiedzi asystenta):
   ```bash
   make local-first-copilot-chat-output-probe
   ```
   - domyślne źródło kontraktu: `config/chat_operator/copilot_chat_output_contract.json`
   - domyślny raport wejściowy: `test-results/234/chat_diagnostics.json`
5. Gate higieny outputu Copilot (ponawia diagnostykę i wymusza brak surowego JSON tool-call w odpowiedzi asystenta):
   ```bash
   make local-first-copilot-chat-output-gate
   ```
6. Probe sesji/modelu Copilot Agent (walidacja modelu i ustawień dla stabilnego tool-loop):
   ```bash
   make local-first-copilot-agent-session-probe
   ```
7. Repo-truth preflight probe (twardy preflight prawdziwego `git status` przed odpowiedzia agenta):
   ```bash
   make local-first-repo-truth-preflight-probe MODEL=qwen2.5-coder:7b
   ```
7. Walidacja konfiguracji agentów i promptów:
   ```bash
   make local-first-agent-config-validate
   ```
8. Probe evidencji z VS Code Agent Debug Log (wyeksportuj JSON sesji z panelu Agent Debug Log, potem zwaliduj evidence local tool-loop):
   ```bash
   make local-first-vscode-agent-log-probe LOG_FILE=/absolute/path/to/agent-session.json
   ```
6. Probe kontraktu terminala (`VSCODE_AGENT`):
   ```bash
   make local-first-vscode-agent-probe
   ```
7. Probe ustawień utility modeli (`chat.utilityModel` / `chat.utilitySmallModel`):
   ```bash
   make local-first-utility-models-probe
   ```
   - domyślne źródło kontraktu: `config/chat_operator/vscode_chat_models_contract.json`
   - opcjonalny override lokalny: `make local-first-utility-models-probe SETTINGS_FILE=.vscode/settings.json`
8. Probe workspace context (`AGENTS.md`, nested `AGENTS.md`, `#codebase`, metadata local index):
   ```bash
   make local-first-workspace-context-probe
   ```
   - domyślne źródło kontraktu: `config/chat_operator/vscode_workspace_context_contract.json`
   - opcjonalny override lokalny: `make local-first-workspace-context-probe SETTINGS_FILE=.vscode/settings.json`
9. Decision gate (finalny kontrakt modeli i routingu):
   ```bash
   make local-first-decision-gate
   ```
   - domyślne źródło kontraktu: `config/chat_operator/decision_gate_contract.json`
   - opcjonalny override: `make local-first-decision-gate CONTRACT_FILE=...`
   - tryb strict (FAIL gdy brak exact repo-truth run): `make local-first-decision-gate STRICT_REPO_TRUTH=1`
10. Probe kontraktu pelnego agenta:
   ```bash
   make local-first-full-agent-contract-probe
   ```
   - domyślne źródło kontraktu: `config/chat_operator/venom_full_agent_contract.json`
   - opcjonalny override: `make local-first-full-agent-contract-probe CONTRACT_FILE=...`
11. Probe debug loopu pelnego agenta:
    ```bash
    make local-first-full-agent-debug-probe
    ```
    - domyślne źródło kontraktu: `config/chat_operator/venom_full_agent_debug_contract.json`
    - opcjonalny override: `make local-first-full-agent-debug-probe CONTRACT_FILE=... SETTINGS_FILE=...`
12. Probe implementacyjnego handoffu:
    ```bash
    make local-first-full-agent-handoff-probe
    ```
    - domyślne źródło kontraktu: `config/chat_operator/venom_full_agent_handoff_contract.json`
    - opcjonalny override: `make local-first-full-agent-handoff-probe CONTRACT_FILE=...`
13. Probe użycia tooli pełnego agenta:
    ```bash
    make local-first-full-agent-tool-probe
    ```
    - domyślne źródło kontraktu: `config/chat_operator/venom_full_agent_tool_contract.json`
    - opcjonalny override: `make local-first-full-agent-tool-probe CONTRACT_FILE=...`
14. Finalny gate pełnego agenta:
    ```bash
    make local-first-full-agent-gate
    ```
    - agreguje personę, użycie tooli, debug i handoff pełnego agenta
    - opcjonalny override: `make local-first-full-agent-gate PERSONA_REPORT=... TOOL_REPORT=... DEBUG_REPORT=... HANDOFF_REPORT=...`
15. PR237 probe gotowosci srodowiska i indeksu repo:
    ```bash
    make local-first-env-index-readiness-probe
    ```
    - domyslne zrodlo kontraktu: `config/chat_operator/venom_agent_decision_contract.json`
16. PR237 probe evidence decyzji agenta:
   ```bash
   make local-first-agent-decision-evidence-probe
   ```
   - waliduje schema evidence (`repo_truth`, `tools_used`, `decision`, `next_step`) z lane repo-truth-first
17. PR238G probe rejestru stanu agenta:
   ```bash
   make local-first-agent-state-registry-probe
   ```
   - zbiera kanoniczny rejestr stanu agenta i środowiska oraz live snapshot repo truth
18. PR237 probe policy enforcement:
   ```bash
   make local-first-policy-enforcement-probe
   ```
   - waliduje repo-level hook wiring i skrypt polityki repo-truth
19. PR237 finalny gate decyzji:
   ```bash
   make local-first-agent-decision-gate
   ```
   - agreguje probe gotowosci srodowiska/indeksu, evidence decyzji, policy enforcement i rejestr stanu
20. Audit driftu dokumentacji operatora czatu:
   ```bash
   make chat-operator-docs-drift-audit
   ```
    - sprawdza, czy dokumentacja operatora używa wyłącznie komend obecnych w canonical `make help` i `make local-first-help`

### Zarządzanie profilem shella

Jeśli zmienne local-first mają zostać w shellu na stałe, używaj:

1. `make local-first-profile-status`
2. `make local-first-profile-print`
3. `make local-first-profile-backup`
4. `make local-first-profile-restore`
5. `make local-first-profile-install`
6. `make local-first-profile-remove`

## Skrócony Makefile

- `make local-first-start MODEL=qwen2.5-coder:7b` - start Ollama i preload wybranego modelu
- `make local-first-status` - sprawdzenie, czy local-first działa
- `make local-first-codex MODEL=... PROMPT=...` - wykonanie lokalnego promptu Codex
- `make local-first-repo-truth-agent MODEL=... PROMPT=...` - uruchomienie agenta z obowiązkowym kontekstem preflight prawdy repo z terminala
- `make local-first-unload MODEL=...` - zwolnienie jednego modelu z pamięci
- `make local-first-stop` - zatrzymanie local-first runtime
- `make local-first-feedback-probe` - pomiar zachowania modeli dla pracy feedback/review
- `make local-first-tool-flake-probe` - test stabilności wywołań narzędzi
- `make local-first-chat-diagnostics` - porównanie prawdziwości odpowiedzi i użycia narzędzi
- `make local-first-copilot-chat-output-probe` - wykrywanie wycieku surowego JSON tool-call do odpowiedzi asystenta w lane Copilot
- `make local-first-copilot-agent-session-probe` - walidacja kontraktu modelu i ustawień Agent-mode VS Code (`chat.model`, utility modele, flagi AGENTS.md)
- `make local-first-copilot-chat-output-gate` - ponowienie diagnostyki i FAIL, gdy odpowiedź asystenta zawiera surowy JSON tool-call
- `make local-first-local-agent-tool-loop-probe` - walidacja local-agent-first tool loop (`qwen2.5-coder:7b` + kanal `agent` + exact run repo-truth)
- `make local-first-local-agent-tool-loop-gate` - FAIL, gdy local-agent lane nie ma exact tool-loop run albo wycieka pseudo payload narzedzia
- `make local-first-repo-truth-preflight-probe MODEL=...` - wymuszenie preflightu prawdy repo (`git status`/`git diff`) przed walidacja odpowiedzi agenta
- `make local-first-agent-config-validate` - walidacja agentów, promptów i instrukcji
- `make local-first-vscode-agent-probe` - weryfikacja kontraktu środowiska terminala dla `VSCODE_AGENT`
- `make local-first-utility-models-probe` - walidacja rozdziału utility modeli w ustawieniach czatu (z opcjonalnym `SETTINGS_FILE=...`)
- `make local-first-workspace-context-probe` - walidacja kontraktu workspace context (`AGENTS.md`, nested `AGENTS.md`, `#codebase`, metadata local-index-first)
- `make local-first-decision-gate` - walidacja finalnych decyzji modeli operatora/utility i routingu main window vs Agents window
- `make local-first-decision-gate STRICT_REPO_TRUTH=1` - twardy gate, ktory failuje, gdy model ma zero exact runow repo-truth
- `make local-first-full-agent-contract-probe` - walidacja persony pelnego agenta Venom, tooli, handoffow i debug contract
- `make local-first-full-agent-debug-probe` - walidacja debug loopu pelnego agenta, debug views i ustawienia lokalnego logowania
- `make local-first-full-agent-handoff-probe` - walidacja handoffu implementacyjnego, izolacji worktree i powrotu do review
- `make local-first-full-agent-tool-probe` - walidacja kontraktu tool-loop pełnego agenta dla prawdy repo, search, read, edit, terminal i subagentów
- `make local-first-full-agent-gate` - walidacja finalnego kontraktu PR236 across personę, tools, debug i handoff
- `make local-first-env-index-readiness-probe` - walidacja PR237 gotowosci capability srodowiska i indeksu repo dla workflow decyzyjnego
- `make local-first-agent-decision-evidence-probe` - walidacja PR237 schema evidence decyzji z lane repo-truth-first
- `make local-first-policy-enforcement-probe` - walidacja PR237 hookow policy i skryptu enforcement dla repo-truth
- `make local-first-agent-decision-gate` - agregacja probe PR237 (readiness + evidence + policy) do jednego PASS/FAIL gate

## Pelny agent Venom

`Venom Full Agent` to persona implementacyjna dla PR236.

Uzywaj jej, gdy potrzebujesz jednego agenta, ktory:

1. startuje od prawdy repo,
2. analizuje kod i diffy,
3. edytuje pliki z uzyciem tooli,
4. moze przekazac zadanie do `Venom Release Guard` i `Venom Hard Gate Engineer`,
5. jest debugowany przez Agent Debug Log i Chat Debug View.

Kontrakt tooli:

1. `search/codebase` i `search/usages` sa pierwsza linia dla analizy.
2. `read` jest wymagane przed stwierdzaniem stanu repo.
3. `edit` sluzy do najmniejszego bezpiecznego wycinka zmian, nie do spekulatywnego przepisywania.
4. `terminal` sluzy do prawdziwych komend, testow i prawdy git.
5. `runSubagent` sluzy tylko do dobrze ograniczonych zadan, ktore da sie rozdzielic.
   - Dla intencji repo-truth lokalny orchestrator ma delegowac do `Venom Full Agent`, zamiast odpowiadac planem.
6. Jesli tool jest niedostepny, trzeba to powiedziec wprost i uzyc jawnego fallbacku zamiast wymyslac wynik.
7. zaczynaj od zrodel prawdy i dopiero potem przechodz do zmiany.

Oczekiwania debug loopu:

1. Otwieraj Agent Debug Log dla sesji wieloetapowych.
2. Otwieraj Chat Debug View do sprawdzenia surowych payloadow request/response.
3. Trzymaj `github.copilot.chat.agentDebugLog.fileLogging.enabled` wlaczone w ustawieniach workspace, gdy chcesz trwałych logow debug.
4. Uzywaj komend VS Code `Show Agent Debug Logs` i `Developer: Show Chat Debug View`, gdy chcesz otworzyc te powierzchnie z palety polecen.

Oczekiwania implementacyjnego handoffu:

1. Uzywaj local agent mode do planowania, dopoki zadanie nie jest wystarczajaco konkretne.
2. Handoffuj do Copilot CLI w izolowanym worktree dla dluzszych przebiegow implementacyjnych.
3. Wracaj do main VS Code window do review i przygotowania merge.
4. Trzymaj `Venom Release Guard` i `Venom Hard Gate Engineer` jako sciezki stabilizacji i finalnego gate.
5. Handoff steps: plan in main VS Code window, handoff to Copilot CLI worktree, implement in isolated worktree, review in main VS Code window.

Kontrakt pelnego agenta znajduje sie w:

- `.github/agents/venom-full-agent.agent.md`
- `docs/CHAT_OPERATOR.md`
- `docs/PL/CHAT_OPERATOR.md`
- `config/chat_operator/venom_full_agent_contract.json`
- `scripts/dev/236_full_agent_contract_probe.py`
- `scripts/dev/236_full_agent_gate.py`

## Powiązane dokumenty

- Podręcznik operatora EN: [../OPERATOR_MANUAL.md](../OPERATOR_MANUAL.md)
- Podręcznik operatora PL: [OPERATOR_MANUAL.md](OPERATOR_MANUAL.md)
- Chat internals EN: [../THE_CHAT.md](../THE_CHAT.md), [../CHAT_SESSION.md](../CHAT_SESSION.md)
- Chat internals PL: [THE_CHAT.md](THE_CHAT.md), [CHAT_SESSION.md](CHAT_SESSION.md)
