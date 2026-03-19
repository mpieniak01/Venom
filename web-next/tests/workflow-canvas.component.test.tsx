import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { useState } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";

import { ToastProvider } from "../components/ui/toast";
import {
  WorkflowCanvas,
  type WorkflowCanvasTestAdapter,
} from "../components/workflow-control/WorkflowCanvasView";

afterEach(() => {
  cleanup();
});

const SAMPLE_STATE = {
  decision_strategy: "advanced",
  intent_mode: "expert",
  kernel: "optimized",
  runtime_services: [
    { id: "backend", name: "backend", kind: "backend", status: "running" },
    { id: "ui", name: "ui", kind: "ui", status: "running", dependencies: ["backend"] },
  ],
  provider: { active: "ollama" },
  embedding_model: "sentence-transformers",
  execution_steps: [
    {
      id: "step-1",
      component: "intent",
      action: "classify",
      status: "ok",
      stage: "execution",
      related_service_id: "backend",
      related_config_keys: ["INTENT_MODE"],
    },
    {
      id: "step-2",
      component: "response",
      action: "answer",
      status: "ok",
      stage: "execution",
      depends_on_step_id: "step-1",
      related_service_id: "ui",
      related_config_keys: ["ACTIVE_PROVIDER"],
    },
  ],
};

function createTestAdapter() {
  const captured: {
    props?: {
      onConnect?: (connection: { source?: string | null; target?: string | null }) => void;
      edges?: Array<{ id: string; source: string; target: string }>;
    };
  } = {};

  const ReactFlowComponent = ((props: {
    children?: React.ReactNode;
    onConnect?: (connection: { source?: string | null; target?: string | null }) => void;
    edges?: Array<{ id: string; source: string; target: string }>;
  }) => {
    captured.props = props;
    return <div data-testid="workflow-reactflow">{props.children}</div>;
  }) as unknown as NonNullable<WorkflowCanvasTestAdapter["ReactFlowComponent"]>;

  const MiniMapComponent = (() => <div data-testid="workflow-minimap" />) as unknown as NonNullable<
    WorkflowCanvasTestAdapter["MiniMapComponent"]
  >;

  const useNodesStateHook = ((initialNodes: unknown[]) => {
    const [nodes, setNodes] = useState(initialNodes);
    const onNodesChange = () => {};
    return [nodes, setNodes, onNodesChange];
  }) as unknown as NonNullable<WorkflowCanvasTestAdapter["useNodesStateHook"]>;

  const useEdgesStateHook = ((initialEdges: unknown[]) => {
    const [edges, setEdges] = useState(initialEdges);
    const onEdgesChange = () => {};
    return [edges, setEdges, onEdgesChange];
  }) as unknown as NonNullable<WorkflowCanvasTestAdapter["useEdgesStateHook"]>;

  return {
    captured,
    adapter: {
      ReactFlowComponent,
      MiniMapComponent,
      useNodesStateHook,
      useEdgesStateHook,
    } satisfies WorkflowCanvasTestAdapter,
  };
}

describe("WorkflowCanvas component", () => {
  it("renders with injected ReactFlow adapter", () => {
    const { adapter } = createTestAdapter();

    render(
      <ToastProvider>
        <WorkflowCanvas systemState={SAMPLE_STATE} testAdapter={adapter} />
      </ToastProvider>,
    );

    assert.ok(screen.getByTestId("workflow-reactflow"));
    assert.ok(screen.getByTestId("workflow-minimap"));
  });

  it("keeps auxiliary canvas read-only for invalid connection attempts", async () => {
    const { adapter, captured } = createTestAdapter();

    render(
      <ToastProvider>
        <WorkflowCanvas systemState={SAMPLE_STATE} testAdapter={adapter} />
      </ToastProvider>,
    );

    const initialEdgesCount = captured.props?.edges?.length ?? 0;
    assert.equal(initialEdgesCount, 5);

    await act(async () => {
      captured.props?.onConnect?.({
        source: "runtime-service:backend",
        target: "execution-step:step-1",
      });
    });

    await act(async () => {
      await Promise.resolve();
    });
    assert.equal(captured.props?.edges?.length, initialEdgesCount);
  });

  it("does not add edge when readOnly=true", async () => {
    const { adapter, captured } = createTestAdapter();

    render(
      <ToastProvider>
        <WorkflowCanvas systemState={SAMPLE_STATE} readOnly testAdapter={adapter} />
      </ToastProvider>,
    );

    const initialEdgesCount = captured.props?.edges?.length ?? 0;
    assert.equal(initialEdgesCount, 5);

    await act(async () => {
      captured.props?.onConnect?.({
        source: "runtime-service:backend",
        target: "execution-step:step-1",
      });
    });

    assert.equal(captured.props?.edges?.length, initialEdgesCount);
  });

  it("does not add edge even for valid connection because helper canvas is read-only", async () => {
    const { adapter, captured } = createTestAdapter();

    render(
      <ToastProvider>
        <WorkflowCanvas systemState={SAMPLE_STATE} testAdapter={adapter} />
      </ToastProvider>,
    );

    const initialEdgesCount = captured.props?.edges?.length ?? 0;
    assert.equal(initialEdgesCount, 5);

    await act(async () => {
      captured.props?.onConnect?.({
        source: "runtime-service:backend",
        target: "execution-step:step-1",
      });
    });

    assert.equal(captured.props?.edges?.length, initialEdgesCount);
  });
});
