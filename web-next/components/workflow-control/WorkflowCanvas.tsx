"use client";

import { useMemo, useEffect } from "react";
import ReactFlow, {
  Node,
  Edge,
  Controls,
  Background,
  BackgroundVariant,
  MiniMap,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import type { SystemState } from "@/types/workflow-control";

interface WorkflowCanvasProps {
  systemState: SystemState | null;
}

interface DecisionNodeData {
  strategy?: string;
  intentMode?: string;
}

interface KernelNodeData {
  kernel?: string;
}

interface RuntimeNodeData {
  runtime?: {
    services?: string[];
  };
}

interface ProviderNodeData {
  provider?: {
    active?: string;
  };
}

interface EmbeddingNodeData {
  model?: string;
}

// Node types
const nodeTypes = {
  decision: DecisionNode,
  kernel: KernelNode,
  runtime: RuntimeNode,
  provider: ProviderNode,
  embedding: EmbeddingNode,
};

// Auto-layout using dagre
function getLayoutedElements(nodes: Node[], edges: Edge[]) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: "TB", nodesep: 100, ranksep: 150 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 200, height: 100 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 100,
        y: nodeWithPosition.y - 50,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

export function WorkflowCanvas({ systemState }: WorkflowCanvasProps) {
  // Generate nodes and edges from system state
  const { initialNodes, initialEdges } = useMemo(() => {
    if (!systemState) {
      return { initialNodes: [], initialEdges: [] };
    }

    const nodes: Node[] = [
      {
        id: "decision",
        type: "decision",
        data: {
          strategy: systemState.decision_strategy,
          intentMode: systemState.intent_mode,
        },
        position: { x: 0, y: 0 },
      },
      {
        id: "kernel",
        type: "kernel",
        data: {
          kernel: systemState.kernel,
        },
        position: { x: 0, y: 0 },
      },
      {
        id: "runtime",
        type: "runtime",
        data: {
          runtime: systemState.runtime,
        },
        position: { x: 0, y: 0 },
      },
      {
        id: "provider",
        type: "provider",
        data: {
          provider: systemState.provider,
        },
        position: { x: 0, y: 0 },
      },
      {
        id: "embedding",
        type: "embedding",
        data: {
          model: systemState.embedding_model,
        },
        position: { x: 0, y: 0 },
      },
    ];

    const edges: Edge[] = [
      { id: "e1", source: "decision", target: "kernel", animated: true },
      { id: "e2", source: "kernel", target: "runtime", animated: true },
      { id: "e3", source: "runtime", target: "provider", animated: true },
      { id: "e4", source: "decision", target: "embedding", animated: true },
    ];

    return getLayoutedElements(nodes, edges);
  }, [systemState]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes and edges when systemState changes
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}

// Custom node components
function DecisionNode({ data }: { data: DecisionNodeData }) {
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-blue-50 dark:bg-blue-950 border-2 border-blue-500">
      <div className="font-bold text-sm mb-1">Decision & Intent</div>
      <div className="text-xs">
        <div>Strategy: {data.strategy}</div>
        <div>Mode: {data.intentMode}</div>
      </div>
    </div>
  );
}

function KernelNode({ data }: { data: KernelNodeData }) {
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-green-50 dark:bg-green-950 border-2 border-green-500">
      <div className="font-bold text-sm mb-1">Kernel</div>
      <div className="text-xs">{data.kernel}</div>
    </div>
  );
}

function RuntimeNode({ data }: { data: RuntimeNodeData }) {
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-purple-50 dark:bg-purple-950 border-2 border-purple-500">
      <div className="font-bold text-sm mb-1">Runtime</div>
      <div className="text-xs">
        {data.runtime?.services?.length || 0} services
      </div>
    </div>
  );
}

function ProviderNode({ data }: { data: ProviderNodeData }) {
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-orange-50 dark:bg-orange-950 border-2 border-orange-500">
      <div className="font-bold text-sm mb-1">Provider</div>
      <div className="text-xs">
        {data.provider?.active || "N/A"}
      </div>
    </div>
  );
}

function EmbeddingNode({ data }: { data: EmbeddingNodeData }) {
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-pink-50 dark:bg-pink-950 border-2 border-pink-500">
      <div className="font-bold text-sm mb-1">Embedding</div>
      <div className="text-xs">{data.model}</div>
    </div>
  );
}
