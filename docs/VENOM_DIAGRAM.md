                                  [ USER INTENT ]
                                          ⬇
┌───────────────────────────────────────────────────────────────────────────────┐
│   LAYER 1: CORE META  —  Brain, Decisions, Logic                             │
│                                                                               │
│   ┌──────────────────────┐   ┌──────────────────┐   ┌──────────────────────┐ │
│   │     ORCHESTRATOR     │←→│  INTENT MANAGER   │←→│    POLICY ENGINE      │ │
│   │ (Central Brain Loop) │   │ (Intent → Plan)  │   │ (Autonomy / Ethics)  │ │
│   └──────────────────────┘   └──────────────────┘   └──────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────┘
                          │ (Neural Signals: JSON Plans)
                          ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│   LAYER 2: AGENT SERVICES  —  Specialized Organs                             │
│                                                                               │
│   ┌──────────────┐   ┌────────────────┐   ┌──────────────┐   ┌────────────┐ │
│   │ planner.arch │   │  coder.llm     │   │ tester.pytest│   │ git.write  │ │
│   │ planner.repo │   │  (AutoGen+Phi) │   │ test.smoke   │   │ docs.writer│ │
│   └──────────────┘   └────────────────┘   └──────────────┘   └────────────┘ │
│            (Coordination between agents via AutoGen GroupChat)               │
└───────────────────────────────────────────────────────────────────────────────┘
                          │ (Execution Requests)
                          ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│   LAYER 3: EXECUTION & PERCEPTION  —  Hands and Senses                        │
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
│   LAYER 4: INFRASTRUCTURE  —  Metabolism and Body                             │
│                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────────┐ │
│   │ RIDER-PC (Host Body)                                                    │ │
│   │ [ WSL2 ] ↔ [ Docker Sandbox ] ↔ [ Ollama / vLLM / ONNX / Cloud ]         │ │
│   │           (LLM Runtime: 3-stack local + Cloud, ONNX also for audio)      │ │
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
│   LAYER 5: MEMORY & KNOWLEDGE  —  HIPPOCAMPUS (GraphRAG + Logs + History)    │
│   - Project knowledge                                                         │
│   - Code map and dependencies                                                  │
│   - Lessons Learned (Self-Improvement)                                          │
│   - Context for planning and agents                                             │
└───────────────────────────────────────────────────────────────────────────────┘

                                ▲
                                │  (Feedback loops)
                                ▼

Legend:
- Florence-2 ONNX — planned v2.0 (local vision engine)
