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
│   │ planner.arch │   │  coder.onnx    │   │ tester.pytest│   │ git.write  │ │
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
│   │ SEMANTIC KERNEL (Hands)    │  │ FLORENCE-2 ONNX (Eyes UI) │  │ ANTENNA  │ │
│   │ File I/O, Shell, Git, Cmd  │  │ OCR, UI Analysis, Errors  │  │ Web-Agent│ │
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
│   │ [ WSL2 ] ↔ [ Docker Sandbox ] ↔ [ ONNX Runtime (GPU/CPU) ]              │ │
│   │                 (Single Model Engine for ALL local models)              │ │
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
