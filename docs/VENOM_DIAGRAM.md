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
│   │ SEMANTIC KERNEL (Hands)    │  │ FLORENCE-2 ONNX (Eyes UI) │  │ ANTENNA  │ │
│   │ File I/O, Shell, Git, Cmd  │  │ OCR, UI Analysis, Errors  │  │ Web-Agent│ │
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
│   │ [ WSL2 ] ↔ [ Docker Sandbox ] ↔ [ ONNX / GGUF Engines ]                 │ │
│   │                 (Dual-Engine Architecture: ONNX + Native LLM)           │ │
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
