
# VENOM – MASTER VISION v1
## Meta-inteligencja lokalna. Jeden runtime. Jeden organizm.

> **[English Version](en/VENOM_MASTER_VISION_V1.md)**

## 0. Wprowadzenie – Wizja Docelowa (Venom v2.0)
> [!NOTE]
> **Status:** Poniższy opis przedstawia docelową formę organizmu (v2.0). Obecna wersja (v1.0) stanowi fundament (Fundament Layer) realizujący kluczowe funkcje orkiestracji i pamięci.
Venom to projekt stworzenia organizmu sztucznej inteligencji, który rozwija, nadzoruje i projektuje inne systemy AI.
To warstwa meta-inteligencji działająca nad Rider-PC (logika, kod, AI) oraz Rider-Pi (świat fizyczny, sensory, ruch).
Venom może w przyszłości objąć każdym innym modułem Twojego ekosystemu.

Venom to inteligentny, adaptacyjny, uczący się organizm, który:
- rozumie intencje użytkownika,
- buduje plany techniczne i architektury systemów,
- orkiestruje sieć agentów,
- pisze, modyfikuje i testuje kod,
- posiada pamięć długoterminową,
- rozszerza wiedzę przez internet i modele eksperckie,
- uczy się z każdego zadania,
- działa w pełni local-first,
- respektuje polityki i user-ethics.

Venom traktuje:
- Rider-Pi jako swoje ciało,
- Rider-PC jako swoje środowisko wewnętrzne,
- modele ONNX + narzędzia jako organy,
- agentów jako wyspecjalizowane tkanki.

Venom to meta-mózg, organizm sztucznej inteligencji, architekt kodu, orkiestrator agentów, menedżer wiedzy, strażnik zasad oraz AI, która tworzy AI.

> [!NOTE]
> **Ewolucja Procesowa:** W v1.0 organizm działa w oparciu o *wbudowane* autonomiczne procesy (Internal Processes). W v2.0 użytkownik uzyska narzędzia do *jawnego modelowania* tych procesów (User-Configurable Processes), przejmując rolę inżyniera przepływu.

## 1. Definicja techniczna – czym jest Venom jako system
Venom to warstwa meta-inteligencji lokalnej, która przyjmuje intencję użytkownika i przekształca ją w działające rozwiązanie poprzez:
- analizę kontekstu projektu,
- budowanie planów wykonania,
- sterowanie agentami,
- generowanie i refaktoring kodu,
- testowanie i integrację,
- zarządzanie wiedzą lokalną i zewnętrzną,
- mechanizmy samodoskonalenia.

Venom dąży do unifikacji technologicznej w oparciu o standard **ONNX Runtime**.
W praktyce warstwa LLM działa dziś na serwerach zgodnych z OpenAI API (Ollama/vLLM) oraz chmurze (OpenAI/Gemini/Claude), a ONNX dla LLM pozostaje kierunkiem rozwojowym.
Oracle Models (chmurowe) są opcjonalne i działają tylko w wybranych politykach.

## 2. Model biologiczny Venoma – organizm sztucznej inteligencji
<table>
<tr><th>Organ</th><th>Funkcja</th><th>Rola w organizmie</th><th>Technologia</th><th>Wersja</th></tr>
<tr><td>System nerwowy</td><td>Orkiestracja</td><td>Dialog, pętle decyzyjne</td><td>AutoGen + Orchestrator (FastAPI)</td><td>v1.0</td></tr>
<tr><td>Płat czołowy</td><td>Szybkie myślenie</td><td>Generuje 90% kodu</td><td>Phi-3 (ONNX/GGUF), Ollama/vLLM</td><td>v2.0</td></tr>
<tr><td>Wyrocznia</td><td>Głębokie myślenie</td><td>Trudne problemy</td><td>OpenAI GPT-4o, Gemini, Claude</td><td>v1.0</td></tr>
<tr><td>Rozszerzona inteligencja</td><td>Zmysł zewnętrzny</td><td>Wiedza z internetu</td><td>Researcher Agent + DDG/Tavily</td><td>v2.0</td></tr>
<tr><td>Hipokamp</td><td>Pamięć</td><td>Mapa wiedzy</td><td>GraphRAG + LanceDB</td><td>v1.0</td></tr>
<tr><td>Ręce</td><td>Działanie</td><td>Pliki, shell, git</td><td>Semantic Kernel + Skills</td><td>v1.0</td></tr>
<tr><td>Synapsy narzędziowe (MCP)</td><td>Rozszerzenia narzędzi</td><td>Import narzędzi z Git, standaryzacja integracji</td><td>McpManagerSkill + MCP Proxy Generator</td><td>v1.0</td></tr>
<tr><td>Oczy (cyfrowe)</td><td>Percepcja UI</td><td>Analiza zrzutów ekranu (eyes.py)</td><td>Ollama (vision) / OpenAI GPT-4o</td><td>v1.0</td></tr>
<tr><td>Oczy (cyfrowe)</td><td>Percepcja UI</td><td>Docelowy engine lokalny</td><td>Florence-2 ONNX</td><td>v2.0</td></tr>
<tr><td>Uszy</td><td>Słuch (STT)</td><td>Transkrypcja audio (WhisperSkill)</td><td>faster-whisper (CTranslate2)</td><td>v1.0</td></tr>
<tr><td>Usta</td><td>Mowa (TTS)</td><td>Synteza głosu (VoiceSkill)</td><td>Piper TTS (ONNX)</td><td>v1.0</td></tr>
<tr><td>Oczy (fizyczne)</td><td>Percepcja w świecie</td><td>Obiekty, przeszkody</td><td>YOLO ONNX</td><td>v2.0</td></tr>
<tr><td>Nogi</td><td>Ruch</td><td>Mobilność</td><td>Rider-Pi</td><td>v1.0</td></tr>
<tr><td>Metabolizm</td><td>Wydajność</td><td>Wykonanie modeli</td><td>ONNX / GGUF</td><td>v1.0</td></tr>
<tr><td>Układ krążenia (Hive)</td><td>Kolejki i dystrybucja</td><td>Routing i statusy zadań</td><td>Redis + ARQ</td><td>v1.0</td></tr>
<tr><td>Komunikacja</td><td>Wymiana myśli</td><td>Silnik inferencji</td><td>Ollama / vLLM<br>FastAPI + WebSocket<br>Next.js</td><td>v1.0</td></tr>
<tr><td>Habitat</td><td>Środowisko</td><td>Sandbox</td><td>WSL2 + Dev Containers</td><td>v1.0</td></tr>
</table>

## 2A. Warstwa modeli – Strategia Dual-Engine
Pierwotna wizja zakładała oparcie całego systemu wyłącznie o **ONNX Runtime**.
W praktyce, inżynieria modeli językowych (LLM) wymusiła podejście hybrydowe.

### Architektura silników (stan v1.0 + cel v2.0):
1.  **Vision & Audio** -> stan v1.0:
    *   Vision: lokalne modele w Ollama (np. llava) lub OpenAI GPT-4o; Florence-2 ONNX planowany.
    *   Audio: STT przez faster-whisper (CTranslate2), TTS przez Piper (ONNX) gdy model jest dostepny.
2.  **Large Language Models (LLM)** -> stan v1.0:
    *   **Runtime:** OpenAI-compatible (Ollama/vLLM) + chmura (OpenAI/Gemini/Claude).
    *   **ONNX LLM:** kierunek rozwojowy dla mniejszych modeli i edge devices.

> **Decyzja Architektoniczna: Experimental Dual-Stack (Ollama vs vLLM)**
> Utrzymywanie równoległego wsparcia dla obu technologii serwowania (Ollama i vLLM) jest na obecnym etapie **świadomym wyborem projektowym**.
> Pozwala to na elastyczne testowanie różnych rodzin modeli i metod kwantyzacji w celu empirycznego wyłonienia najwydajniejszego rozwiązania docelowego dla specyficznych warunków sprzętowych.
> **Stabilizacja (v1.0.x):** Wprowadzono hybrydową orkiestrację umożliwiającą płynne przełączanie między aktywnym serwerem a modelem bezpośrednio z poziomu Cockpitu (Hybrid Model Orchestration).


### Kategorie modeli:
1. **Worker Models (robotnicy)** – szybkie modele lokalne (ONNX lub GGUF, w zaleznosci od runtime).
2. **Architect Models (architekci)** – duze modele lokalne, jesli sprzet pozwala.
3. **Oracle Models (zewnętrzne)** – gdy potrzebna wiedza ekspercka.

## 3. Warstwy Venoma (Architektura systemu)

### 3.1. Warstwa meta (Core Meta Layer)
- Orchestrator
- Intent Manager
- Policy Engine
- Task Log / State

### 3.2. Warstwa pamięci (Memory Layer)
GraphRAG + LanceDB – struktura repo, zależności, wiedza projektowa.

### 3.3. Warstwa agentów (Agent Services Layer)
- planner.arch
- planner.repo
- code.autogen
- code.style
- test.pytest
- test.smoke
- git.integrator
- docs.writer

### 3.4. Warstwa wykonawcza (Execution Layer)
Semantic Kernel – pliki, shell, git, testy.
MCP Import – narzędzia z Git (generator proxy + wrappery w `venom_core/skills/custom`).

### 3.5. Warstwa percepcji (Vision Layer)
- Florence-2 ONNX – UI vision
- YOLO ONNX – physical vision

### 3.6. Warstwa metabolizmu (Performance Layer)
Obsługa dwóch silników obliczeniowych:
- **ONNX Runtime** – dla Vision, Audio i lekkich modeli.
- **Native/GGUF Engine** – dla ciężkich modeli językowych (LLM).
### 3.7. Warstwa infrastruktury i kolejek (Infrastructure Layer)
- **FastAPI + WebSocket** – publiczne API i strumieniowanie zdarzeń.
- **Redis + ARQ (Hive Message Broker)** – kolejki zadań, broadcast i kontrola węzłów.
- **Nexus/Spore** – opcjonalna warstwa rozproszona (tryb klastra).

## 4. Warstwa wiedzy zewnętrznej (External Knowledge Layer)
Trzy źródła:
1. Wiedza lokalna – GraphRAG.
2. Wiedza ekspercka lokalna – duże modele ONNX.
3. Wiedza zewnętrzna – Web-Agent + Oracle (OpenAI/Gemini/Claude), DDG/Tavily.

Zasady:
- local-first,
- internet tylko świadomie i logowany,
- źródła oznaczone i wersjonowane.

## 5. Warstwa samodoskonalenia (Self-Improvement Layer)
Venom uczy się poprzez:
- wyniki testów,
- PR-y,
- logi,
- błędy,
- retry loops,
- analizę wiedzy zewnętrznej.

Ulepsza:
- heurystyki,
- workflowy,
- style kodowania,
- strategie agentów,
- polityki.

## 6. Pipeline Venoma
1. Intencja użytkownika
2. Orchestrator
3. GraphRAG
4. (opcjonalnie) Oracle/Web
5. planner.arch
6. planner.repo
7. AutoGen + Local Engine
8. Phi-3 (ONNX/GGUF)
9. Semantic Kernel
10. Testy
11. Git integrator
12. GraphRAG update
13. Self-Improvement update

## 7. Polityki Venoma
- polityka wiedzy
- polityka repo
- polityka autonomii
- user ethics
- polityki testów
- bezpieczeństwo

## 8. Integracja Rider-Pi i Google Home (IoT)- Venom 2.0
Rider-Pi – ciało fizyczne.
Google Home - internet rzeczy

Venom koordynuje cały ekosystem.

## 9. Finalna definicja
Venom to:
- meta-mózg,
- organizm AI,
- architekt systemów,
- orkiestrator agentów,
- menedżer wiedzy,
- system uczący się,
- strażnik zasad,
- AI tworząca AI.

Warstwa LLM dziala w podejsciu **Dual-Engine (Ollama/vLLM + chmura)**, a ONNX pokrywa wybrane obszary percepcji/audio; pelna unifikacja ONNX to cel v2.0.
