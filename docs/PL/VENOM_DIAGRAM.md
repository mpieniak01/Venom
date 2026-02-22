                                  [ USER INTENT ]
                                          ⬇
┌───────────────────────────────────────────────────────────────────────────────┐
│   WARSTWA 1: CORE META  —  Mózg, Decyzje, Logika                              │
│                                                                               │
│   ┌──────────────────────┐   ┌──────────────────┐   ┌──────────────────────┐ │
│   │     ORCHESTRATOR     │←→│  INTENT MANAGER   │←→│    POLICY ENGINE      │ │
│   │ (Central Brain Loop) │   │ (Intent → Plan)  │   │ (Autonomy / Ethics)  │ │
│   └──────────────────────┘   └──────────────────┘   └──────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────┘
                          │ (Neural Signals: JSON Plans)
                          ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│   WARSTWA 2: AGENT SERVICES  —  Organy specjalistyczne                        │
│                                                                               │
│   ┌──────────────┐   ┌────────────────┐   ┌──────────────┐   ┌────────────┐ │
│   │ planner.arch │   │  coder.llm     │   │ tester.pytest│   │ git.write  │ │
│   │ planner.repo │   │  (AutoGen+Phi) │   │ test.smoke   │   │ docs.writer│ │
│   └──────────────┘   └────────────────┘   └──────────────┘   └────────────┘ │
│            (Koordynacja między agentami poprzez AutoGen GroupChat)           │
└───────────────────────────────────────────────────────────────────────────────┘
                          │ (Execution Requests)
                          ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│   WARSTWA 3: EXECUTION & PERCEPTION  —  Ręce i Zmysły                          │
│                                                                               │
│   ┌─────────────────────────────┐  ┌──────────────────────────┐  ┌──────────┐ │
│   │ SEMANTIC KERNEL (Hands)    │  │ OLLAMA / OPENAI (Eyes UI) │  │ ANTENNA  │ │
│   │ File I/O, Shell, Git, Cmd  │  │ Vision Analysis (v1.0)    │  │ Web-Agent│ │
│   └─────────────────────────────┘  └──────────────────────────┘  └──────────┘ │
│               (System calls / OS access / perception inputs)                  │
└───────────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│   WARSTWA 4: INFRASTRUCTURE  —  Metabolizm i Ciało                            │
│                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────────┐ │
│   │ RIDER-PC (Host Body)                                                    │ │
│   │ [ WSL2 ] ↔ [ Docker Sandbox ] ↔ [ Ollama / vLLM / ONNX / Cloud ]         │ │
│   │      (LLM Runtime: lokalny 3-stack + Cloud, ONNX także dla audio)        │ │
│   └─────────────────────────────────────────────────────────────────────────┘ │
│                                       │ Network / IoT                           │
│                                       ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐ │
│   │ RIDER-PI (Physical Body / Motor System)                                    │ │
│   │ Sensors ↔ Actuators ↔ YOLO ONNX ↔ Movement Logic                            │ │
│   └─────────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────┘

                                ▲          ▲           ▲
                                │          │           │
┌───────────────────────────────────────────────────────────────────────────────┐
│   WARSTWA 5: PAMIĘĆ I WIEDZA  —  HIPOKAMP (GraphRAG + Logs + History)        │
│   - Wiedza o projekcie                                                         │
│   - Mapa kodu i zależności                                                      │
│   - Lessons Learned (Self-Improvement)                                          │
│   - Kontekst dla planowania i agentów                                           │
└───────────────────────────────────────────────────────────────────────────────┘

                                ▲
                                │  (Feedback loops)
                                ▼

Legenda:
- Florence-2 ONNX — planned v2.0 (lokalny vision engine)
