
# VENOM – MASTER VISION v1
## Local meta-intelligence. One runtime. One organism.

> **[Polska Wersja](../VENOM_MASTER_VISION_V1.md)**

## 0. Introduction – Target Vision (Venom v2.0)
> [!NOTE]
> **Status:** The description below presents the target form of the organism (v2.0). The current version (v1.0) serves as the foundation (Foundation Layer) implementing key orchestration and memory functions.
Venom is a project to create an artificial intelligence organism that develops, supervises, and designs other AI systems.
It's a meta-intelligence layer operating above Rider-PC (logic, code, AI) and Rider-Pi (physical world, sensors, movement).
Venom can in the future encompass any other module in your ecosystem.

Venom is an intelligent, adaptive, learning organism that:
- understands user intent,
- builds technical plans and system architectures,
- orchestrates agent networks,
- writes, modifies and tests code,
- has long-term memory,
- expands knowledge through internet and expert models,
- learns from every task,
- operates fully local-first,
- respects policies and user-ethics.

Venom treats:
- Rider-Pi as its body,
- Rider-PC as its internal environment,
- ONNX models + tools as organs,
- agents as specialized tissues.

Venom is a meta-brain, artificial intelligence organism, code architect, agent orchestrator, knowledge manager, policy guardian, and AI that creates AI.

> [!NOTE]
> **Process Evolution:** In v1.0, the organism operates based on *built-in* autonomous processes (Internal Processes). In v2.0, the user will gain tools for *explicit modeling* of these processes (User-Configurable Processes), taking on the role of a flow engineer.

## 1. Technical definition – what is Venom as a system
Venom is a local meta-intelligence layer that takes user intent and transforms it into a working solution through:
- project context analysis,
- execution plan building,
- agent control,
- code generation and refactoring,
- testing and integration,
- local and external knowledge management,
- self-improvement mechanisms.

Venom strives for technological unification based on the **ONNX Runtime** standard.
In practice, the LLM layer currently runs on OpenAI-compatible servers (Ollama/vLLM) and cloud providers (OpenAI/Gemini/Claude), while ONNX for LLM remains a future direction.
Oracle Models (cloud) are optional and work only in selected policies.

## 2. Venom's biological model – artificial intelligence organism
<table>
<tr><th>Organ</th><th>Function</th><th>Role in organism</th><th>Technology</th><th>Version</th></tr>
<tr><td>Nervous system</td><td>Orchestration</td><td>Dialog, decision loops</td><td>AutoGen + Orchestrator (FastAPI)</td><td>v1.0</td></tr>
<tr><td>Frontal lobe</td><td>Fast thinking</td><td>Generates 90% of code</td><td>Phi-3 (ONNX/GGUF), Ollama/vLLM</td><td>v2.0</td></tr>
<tr><td>Oracle</td><td>Deep thinking</td><td>Difficult problems</td><td>OpenAI GPT-4o, Gemini, Claude</td><td>v1.0</td></tr>
<tr><td>Extended intelligence</td><td>External sense</td><td>Internet knowledge</td><td>Researcher Agent + DDG/Tavily</td><td>v2.0</td></tr>
<tr><td>Hippocampus</td><td>Memory</td><td>Knowledge map</td><td>GraphRAG + LanceDB</td><td>v1.0</td></tr>
<tr><td>Hands</td><td>Action</td><td>Files, shell, git</td><td>Semantic Kernel + Skills</td><td>v1.0</td></tr>
<tr><td>Eyes (digital)</td><td>UI perception</td><td>Screenshot analysis (eyes.py)</td><td>Ollama (vision) / OpenAI GPT-4o</td><td>v1.0</td></tr>
<tr><td>Eyes (digital)</td><td>UI perception</td><td>Target local engine</td><td>Florence-2 ONNX</td><td>v2.0</td></tr>
<tr><td>Ears</td><td>Hearing (STT)</td><td>Audio transcription (WhisperSkill)</td><td>faster-whisper (CTranslate2)</td><td>v1.0</td></tr>
<tr><td>Mouth</td><td>Speech (TTS)</td><td>Voice synthesis (VoiceSkill)</td><td>Piper TTS (ONNX)</td><td>v1.0</td></tr>
<tr><td>Eyes (physical)</td><td>World perception</td><td>Objects, obstacles</td><td>YOLO ONNX</td><td>v2.0</td></tr>
<tr><td>Legs</td><td>Movement</td><td>Mobility</td><td>Rider-Pi</td><td>v1.0</td></tr>
<tr><td>Metabolism</td><td>Performance</td><td>Model execution</td><td>ONNX / GGUF</td><td>v1.0</td></tr>
<tr><td>Circulatory system (Hive)</td><td>Queues & distribution</td><td>Task routing and status</td><td>Redis + ARQ</td><td>v1.0</td></tr>
<tr><td>Communication</td><td>Thought exchange</td><td>Inference engine</td><td>Ollama / vLLM<br>FastAPI + WebSocket<br>Next.js</td><td>v1.0</td></tr>
<tr><td>Habitat</td><td>Environment</td><td>Sandbox</td><td>WSL2 + Dev Containers</td><td>v1.0</td></tr>
</table>

## 2A. Model layer – Dual-Engine Strategy
The original vision assumed basing the entire system solely on **ONNX Runtime**.
In practice, Large Language Model (LLM) engineering necessitated a hybrid approach.

### Engine architecture (v1.0 state + v2.0 target):
1.  **Vision & Audio** -> v1.0 state:
    *   Vision: local models via Ollama (e.g., llava) or OpenAI GPT-4o; Florence-2 ONNX planned.
    *   Audio: STT via faster-whisper (CTranslate2), TTS via Piper (ONNX) when a model is available.
2.  **Large Language Models (LLM)** -> v1.0 state:
    *   **Runtime:** OpenAI-compatible (Ollama/vLLM) + cloud (OpenAI/Gemini/Claude).
    *   **ONNX LLM:** future direction for smaller models and edge devices.

> [!NOTE]
> **Architectural Decision: Experimental Dual-Stack (Ollama vs vLLM)**
> Maintaining parallel support for both serving technologies (Ollama and vLLM) is currently a **conscious design choice**.
> It allows for flexible testing of different model families and quantization methods to empirically select the most efficient target solution for specific hardware conditions.


### Model categories:
1. **Worker Models (workers)** – fast local models (ONNX or GGUF depending on runtime).
2. **Architect Models (architects)** – large local models, if hardware allows.
3. **Oracle Models (external)** – when expert knowledge is needed.

## 3. Venom layers (System architecture)

### 3.1. Meta layer (Core Meta Layer)
- Orchestrator
- Intent Manager
- Policy Engine
- Task Log / State

### 3.2. Memory layer (Memory Layer)
GraphRAG + LanceDB – repository structure, dependencies, project knowledge.

### 3.3. Agent layer (Agent Services Layer)
- planner.arch
- planner.repo
- code.autogen
- code.style
- test.pytest
- test.smoke
- git.integrator
- docs.writer

### 3.4. Execution layer (Execution Layer)
Semantic Kernel – files, shell, git, tests.

### 3.5. Perception layer (Vision Layer)
- Florence-2 ONNX – UI vision
- YOLO ONNX – physical vision

### 3.6. Metabolism layer (Performance Layer)
Support for two computational engines:
- **ONNX Runtime** – for Vision, Audio, and lightweight models.
- **Native/GGUF Engine** – for heavy Large Language Models (LLM).
### 3.7. Infrastructure & queues (Infrastructure Layer)
- **FastAPI + WebSocket** – public API and event streaming.
- **Redis + ARQ (Hive Message Broker)** – task queues, broadcast, node control.
- **Nexus/Spore** – optional distributed layer (cluster mode).

## 4. External knowledge layer (External Knowledge Layer)
Three sources:
1. Local knowledge – GraphRAG.
2. Local expert knowledge – large ONNX models.
3. External knowledge – Web-Agent + Oracle (OpenAI/Gemini/Claude), DDG/Tavily.

Principles:
- local-first,
- internet only consciously and logged,
- sources marked and versioned.

## 5. Self-improvement layer (Self-Improvement Layer)
Venom learns through:
- test results,
- PRs,
- logs,
- errors,
- retry loops,
- external knowledge analysis.

Improves:
- heuristics,
- workflows,
- coding styles,
- agent strategies,
- policies.

## 6. Venom pipeline
1. User intent
2. Orchestrator
3. GraphRAG
4. (optionally) Oracle/Web
5. planner.arch
6. planner.repo
7. AutoGen + Local Engine
8. Phi-3 (ONNX/GGUF)
9. Semantic Kernel
10. Tests
11. Git integrator
12. GraphRAG update
13. Self-Improvement update

## 7. Venom policies
- knowledge policy
- repository policy
- autonomy policy
- user ethics
- testing policies
- security

## 8. Integration of Rider-Pi and Google Home (IoT) - Venom 2.0
Rider-Pi – physical body.
Google Home - Internet of Things

Venom coordinates the entire ecosystem.

## 9. Final definition
Venom is:
- meta-brain,
- AI organism,
- systems architect,
- agent orchestrator,
- knowledge manager,
- learning system,
- policy guardian,
- AI creating AI.

The LLM layer follows a **Dual-Engine approach (Ollama/vLLM + cloud)**, while ONNX covers selected perception/audio paths; full ONNX unification is a v2.0 goal.
