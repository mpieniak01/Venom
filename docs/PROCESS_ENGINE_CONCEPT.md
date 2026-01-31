# Venom Process Engine Concept [v2.0]

> [!NOTE]
> **Status:** Concept planned for **Venom 2.0**.
> This document describes the vision of the "Process Approach", where the user can manually build, arrange, and manage complex business/logic processes.

## Vision: Venom as a Process Engine

In v1.0, Venom utilizes **internal processes** (e.g., Chat => Planner => Coder => Critic cycle), which are fixed and managed by the system ("Internal/Fixed Processes"). The user assigns tasks, and Venom selects the appropriate built-in process.

In v2.0, we introduce the **Process Approach (User-Configurable Processes)**, where the user gains control over the definition of these workflows. The user moves from being just a requester to becoming an architect of logic, arranging blocks in a graphical editor.

### Key Assumptions

1.  **Visual Process Builder** - Graphical interface (drag & drop) for arranging blocks (Agents, Skills, Logic).
2.  **Determinism vs AI** - Ability to combine rigid rules (If/Else, Loops) with flexible AI nodes (e.g., "Decide if email is important").
3.  **Reusability** - A defined process becomes a new "Skill" available to other agents.
4.  **Human-in-the-Loop** - Nodes requiring human approval or decision before proceeding.

## Architecture (Planned)

```mermaid
graph TD
    User -->|Builds| ProcessBuilder[Visual Process Builder]
    ProcessBuilder -->|Generates| WorkflowDef[Workflow Definition (JSON/YAML)]

    WorkflowDef -->|Loads| ProcessEngine[Process Engine Core]

    ProcessEngine -->|Orchestrates| Flow[Flow Execution]

    subgraph Flow Execution
        Node1[Node: Fetch Data] -->|Result| Node2{AI Decision}
        Node2 -->|Important| Node3[Agent: Send Alert]
        Node2 -->|Spam| Node4[Ignore]
    end
```

### Components

-   **Process Designer**: UI in Next.js based on a graph library (e.g., React Flow).
-   **Execution Engine**: Extension of the current `Orchestrator` to support long-running, stateful processes (State Machines).
-   **Standard**: Consideration of adapting BPMN 2.0 or a simplified JSON standard.

## Example User Processes

1.  **Employee Onboarding**
    *   Step 1: Generate contract (Coder/Writer)
    *   Step 2: Send email (Tool: SMTP)
    *   Step 3: Wait for signature (Human Trigger)
    *   Step 4: Create system accounts (Ghost Agent)

2.  **Media Monitoring**
    *   Step 1: Check RSS every 1h (Researcher)
    *   Step 2: If topic = "Venom AI" -> Analyze sentiment (Analyst)
    *   Step 3: If negative -> Send SMS to Admin

## Relation to The Apprentice

While **The Apprentice** learns by *observation* (recording), the **Process Engine** allows for *conscious design* and *editing* of logic. These systems will collaborate: Apprentice can generate a raw process, which the user then refines in the Process Builder.
