"use client";

import { useMemo, useEffect } from "react";
import {
  ReactFlow,
  Edge,
  Node,
  Controls,
  Background,
  BackgroundVariant,
  MiniMap,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { useTranslation } from "@/lib/i18n";
import type { SystemState } from "@/types/workflow-control";
import { buildWorkflowGraph } from "@/lib/workflow-canvas-helpers";

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

function getLayoutedElements(nodes: Node[], edges: Edge[]): Node[] {
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

  return nodes.map((node) => {
    const pos = dagreGraph.node(node.id);
    return {
      ...node,
      position: { x: pos.x - 100, y: pos.y - 50 },
    };
  });
}

export function WorkflowCanvas({ systemState }: WorkflowCanvasProps) {
  // Generate nodes and edges from system state
  const { initialNodes, initialEdges } = useMemo(() => {
    const { nodes, edges } = buildWorkflowGraph(systemState);
    return { initialNodes: getLayoutedElements(nodes, edges), initialEdges: edges };
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
  const t = useTranslation();
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-blue-50 dark:bg-blue-950 border-2 border-blue-500">
      <div className="font-bold text-sm mb-1">{t("workflowControl.sections.decision")}</div>
      <div className="text-xs">
        <div>{t("workflowControl.labels.currentStrategy")}: {data.strategy || t("workflowControl.common.na")}</div>
        <div>{t("workflowControl.labels.currentIntent")}: {data.intentMode || t("workflowControl.common.na")}</div>
      </div>
    </div>
  );
}

function KernelNode({ data }: { data: KernelNodeData }) {
  const t = useTranslation();
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-green-50 dark:bg-green-950 border-2 border-green-500">
      <div className="font-bold text-sm mb-1">{t("workflowControl.labels.currentKernel")}</div>
      <div className="text-xs">{data.kernel || t("workflowControl.common.na")}</div>
    </div>
  );
}

function RuntimeNode({ data }: { data: RuntimeNodeData }) {
  const t = useTranslation();
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-purple-50 dark:bg-purple-950 border-2 border-purple-500">
      <div className="font-bold text-sm mb-1">{t("workflowControl.labels.runtimeServices")}</div>
      <div className="text-xs">
        {t("workflowControl.canvas.servicesCount", {
          count: data.runtime?.services?.length || 0,
        })}
      </div>
    </div>
  );
}

function ProviderNode({ data }: { data: ProviderNodeData }) {
  const t = useTranslation();
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-orange-50 dark:bg-orange-950 border-2 border-orange-500">
      <div className="font-bold text-sm mb-1">{t("workflowControl.labels.currentProvider")}</div>
      <div className="text-xs">
        {data.provider?.active || t("workflowControl.common.na")}
      </div>
    </div>
  );
}

function EmbeddingNode({ data }: { data: EmbeddingNodeData }) {
  const t = useTranslation();
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-pink-50 dark:bg-pink-950 border-2 border-pink-500">
      <div className="font-bold text-sm mb-1">{t("workflowControl.labels.currentEmbedding")}</div>
      <div className="text-xs">{data.model || t("workflowControl.common.na")}</div>
    </div>
  );
}
