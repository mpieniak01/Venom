"use client";

import { useMemo, useEffect } from "react";
import {
  ReactFlow,
  Node,
  NodeProps,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  NodeChange,
  EdgeChange,
  MarkerType,
  Handle,
  Position,
  NodeToolbar,
} from "@xyflow/react";
import { useCallback } from "react";
import { useToast } from "@/components/ui/toast";
import "@xyflow/react/dist/style.css";
import { useTranslation } from "@/lib/i18n";
import type { SystemState } from "@/types/workflow-control";
import { buildWorkflowGraph } from "@/lib/workflow-canvas-helpers";
import {
  validateConnection
} from "@/lib/workflow-policy";
import { Button } from "@/components/ui/button";
import { Settings, Info } from "lucide-react";

interface WorkflowCanvasProps {
  systemState: SystemState | null;
}

// Node types
const nodeTypes = {
  decision: DecisionNode,
  intent: IntentNode,
  kernel: KernelNode,
  runtime: RuntimeNode,
  provider: ProviderNode,
  embedding: EmbeddingNode,
  swimlane: SwimlaneNode,
};

const SWIMLANE_HEIGHT = 130;
const SWIMLANE_WIDTH = 1400;

export function WorkflowCanvas({
  systemState,
  onNodeClick,
  onEdgesChange: onEdgesChangeProp,
  onNodesChange: onNodesChangeProp,
  readOnly = false
}: WorkflowCanvasProps & {
  onNodeClick?: (node: Node) => void;
  onEdgesChange?: (changes: unknown) => void;
  onNodesChange?: (changes: unknown) => void;
  readOnly?: boolean;
}) {
  const t = useTranslation();

  // Generate nodes and edges from system state
  // Memozied to avoid regeneration on every render if state doesn't change
  const { initialNodes, initialEdges } = useMemo(() => {
    const { nodes, edges } = buildWorkflowGraph(systemState);

    // Define specific order for Swimlanes to match visual requirements
    const SWIMLANE_ORDER = ['decision', 'intent', 'kernel', 'runtime', 'embedding', 'provider'];

    // Generate visual swimlane nodes (Horizontal Rows)
    const backgroundSwimlanes = SWIMLANE_ORDER.map((cat, i) => ({
      id: `swimlane-${cat}`,
      type: 'swimlane',
      data: { label: cat, index: i }, // Pass simple category key for styling
      position: { x: 0, y: i * SWIMLANE_HEIGHT },
      style: { width: SWIMLANE_WIDTH, height: SWIMLANE_HEIGHT },
      selectable: false,
      draggable: false,
      zIndex: 0, // Base layer
    }));

    // Apply Swimlane Layout Logic
    // Force Strict Diagonal Layout based on user screenshot
    // Order: Decision -> Intent -> Kernel -> Runtime -> Embedding -> Provider
    // Each occupies a row and steps to the right.
    const strictLayout: Record<string, { x: number; y: number }> = {
      decision: { x: 0, y: 0 },
      intent: { x: 1, y: 1 },
      kernel: { x: 2, y: 2 },
      runtime: { x: 3, y: 3 },
      embedding: { x: 4, y: 4 },
      provider: { x: 5, y: 5 },
    };

    const X_START = 60;
    const X_OFFSET = 210; // Matches width to eliminate horizontal overlap while maintaining tight flow

    const positionedNodes: Node[] = nodes.map(node => {
      const position = strictLayout[node.type || ""];
      if (position) {
        return {
          ...node,
          // Parent-Child relationship for swimlane constraint
          parentId: `swimlane-${node.type}`,
          extent: 'parent',
          position: {
            x: X_START + (position.x * X_OFFSET),
            y: 25 // Centered (25 top + 80 node + 25 bottom = 130)
          },
          draggable: !readOnly,
          selectable: !readOnly,
          zIndex: 20, // Above swimlanes
        };
      }
      return {
        ...node,
        draggable: !readOnly,
        selectable: !readOnly,
        zIndex: 20, // Above swimlanes
      };
    });

    return { initialNodes: [...backgroundSwimlanes, ...positionedNodes], initialEdges: edges };
  }, [systemState, readOnly]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync with prop changes if provided (controlled mode)
  useEffect(() => {
    if (initialNodes.length > 0) {
      setNodes(initialNodes);
      setEdges(initialEdges);
    }
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  // Handle external change handlers
  const handleNodesChange = (changes: NodeChange<Node>[]) => {
    onNodesChange(changes);
    if (onNodesChangeProp) onNodesChangeProp(changes);
  };

  const handleEdgesChange = (changes: EdgeChange[]) => {
    onEdgesChange(changes);
    if (onEdgesChangeProp) onEdgesChangeProp(changes);
  };

  const { pushToast } = useToast();

  const onConnect = useCallback(
    (params: Connection) => {
      if (readOnly) return;

      const sourceNode = nodes.find((n) => n.id === params.source);
      const targetNode = nodes.find((n) => n.id === params.target);

      if (sourceNode && targetNode) {
        const validation = validateConnection(sourceNode, targetNode);
        if (!validation.isValid) {
          pushToast(
            `${t("workflowControl.messages.connectionRejected")}: ${t(`workflowControl.messages.${validation.reason}`) || validation.reason}`,
            "error"
          );
          return;
        }
      }

      setEdges((eds) => addEdge(params, eds));
    },
    [nodes, readOnly, setEdges, pushToast, t]
  );

  return (
    <div className="w-full h-full bg-slate-50 dark:bg-slate-950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => onNodeClick?.(node)}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={{
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
          animated: true,
          style: { strokeWidth: 3, stroke: '#e2e8f0' }, // Brighter and thicker for visibility
        }}
        fitView
        fitViewOptions={{ padding: 0.05, minZoom: 0.8, maxZoom: 1.5 }}
        proOptions={{ hideAttribution: true }}
      >


        <MiniMap
          position="top-right"
          nodeColor={(n) => {
            // Match node colors to swimlane colors roughly
            switch (n.type) {
              case 'decision': return '#3b82f6';
              case 'kernel': return '#22c55e';
              case 'runtime': return '#a855f7';
              case 'provider': return '#f97316';
              case 'intent': return '#eab308';
              case 'embedding': return '#ec4899';
              default: return '#334155';
            }
          }}
          className="!bg-slate-950 border border-slate-800 rounded-lg shadow-xl" // Dark background to fix white artifact
          maskColor="rgba(2, 6, 23, 0.7)" // Dark mask
        />
      </ReactFlow>
    </div>
  );
}

// Custom node components
function NodeActions() {
  const t = useTranslation();
  return (
    <NodeToolbar position={Position.Top} className="flex gap-1 bg-slate-900/90 p-1 rounded-md border border-white/10 backdrop-blur-md shadow-xl">
      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 hover:bg-white/10" title={t("workflowControl.actions.edit")}>
        <Settings className="w-3 h-3 text-slate-200" />
      </Button>
      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 hover:bg-white/10" title={t("workflowControl.actions.details")}>
        <Info className="w-3 h-3 text-blue-400" />
      </Button>
    </NodeToolbar>
  );
}

function SelectedNodePulse({
  selected,
  glowClass,
}: {
  selected: boolean;
  glowClass: string;
}) {
  if (!selected) return null;
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 rounded-xl border-2 ${glowClass} opacity-70 motion-safe:animate-pulse motion-reduce:animate-none`}
    />
  );
}

// Swimlane Styling Map - Increased Contrast
const SWIMLANE_STYLES: Record<string, { bg: string; border: string; text: string; bgContent: string }> = {
  decision: { bg: 'bg-blue-900/40', border: 'border-slate-700', text: 'text-blue-400', bgContent: 'bg-blue-900/5' },
  intent: { bg: 'bg-yellow-900/40', border: 'border-slate-700', text: 'text-yellow-400', bgContent: 'bg-yellow-900/5' },
  kernel: { bg: 'bg-green-900/40', border: 'border-slate-700', text: 'text-green-400', bgContent: 'bg-green-900/5' },
  runtime: { bg: 'bg-purple-900/40', border: 'border-slate-700', text: 'text-purple-400', bgContent: 'bg-purple-900/5' },
  provider: { bg: 'bg-orange-900/40', border: 'border-slate-700', text: 'text-orange-400', bgContent: 'bg-orange-900/5' },
  embedding: { bg: 'bg-pink-900/40', border: 'border-slate-700', text: 'text-pink-400', bgContent: 'bg-pink-900/5' },
};

function SwimlaneNode({ data }: { data: { label: string, index: number } }) {
  const t = useTranslation();
  const style = SWIMLANE_STYLES[data.label] || { bg: 'bg-slate-900/20', border: 'border-slate-800', text: 'text-slate-500', bgContent: 'transparent' };

  return (
    <div className={`w-full h-full flex flex-row border-b ${style.border}`}>
      {/* Header (Left Sidebar) */}
      <div className={`w-[40px] h-full flex items-center justify-center ${style.bg} border-r ${style.border}`}>
        <div className="transform -rotate-90 text-[10px] font-extrabold uppercase tracking-widest opacity-90 w-[200px] text-center" style={{ color: 'inherit' }}>
          <span className={style.text}>{t(`workflowControl.sections.${data.label}`)}</span>
        </div>
      </div>
      {/* Content Area */}
      <div className={`flex-1 h-full ${style.bgContent} bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]`} />
    </div>
  );
}

function DecisionNode({ selected = false }: NodeProps) {
  const t = useTranslation();
  return (
    <div className="group px-8 py-6 h-[80px] flex flex-col justify-center shadow-[0_0_15px_rgba(59,130,246,0.3)] hover:shadow-[0_0_25px_rgba(59,130,246,0.5)] transition-shadow duration-300 rounded-xl bg-slate-900 border-2 border-blue-500 text-blue-100 min-w-[210px] relative">
      <SelectedNodePulse selected={selected} glowClass="border-blue-300/90 shadow-[0_0_24px_rgba(96,165,250,0.45)]" />
      <Handle type="source" position={Position.Bottom} className="!bg-blue-500 !w-3 !h-3" />
      <NodeActions />
      <div className="font-bold text-xl text-blue-400 truncate text-center">{t("workflowControl.sections.decision")}</div>
    </div>
  );
}

function KernelNode({ selected = false }: NodeProps) {
  const t = useTranslation();
  return (
    <div className="group px-8 py-6 h-[80px] flex flex-col justify-center shadow-[0_0_15px_rgba(34,197,94,0.3)] hover:shadow-[0_0_25px_rgba(34,197,94,0.5)] transition-shadow duration-300 rounded-xl bg-slate-900 border-2 border-green-500 text-green-100 min-w-[210px] relative">
      <SelectedNodePulse selected={selected} glowClass="border-green-300/90 shadow-[0_0_24px_rgba(74,222,128,0.45)]" />
      <Handle type="target" position={Position.Left} className="!bg-green-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Bottom} className="!bg-green-500 !w-3 !h-3" />
      <NodeActions />
      <div className="font-bold text-xl text-green-400 truncate text-center">{t("workflowControl.labels.currentKernel")}</div>
    </div>
  );
}

function RuntimeNode({ selected = false }: NodeProps) {
  const t = useTranslation();
  return (
    <div className="group px-8 py-6 h-[80px] flex flex-col justify-center shadow-[0_0_15px_rgba(168,85,247,0.3)] hover:shadow-[0_0_25px_rgba(168,85,247,0.5)] transition-shadow duration-300 rounded-xl bg-slate-900 border-2 border-purple-500 text-purple-100 min-w-[210px] relative">
      <SelectedNodePulse selected={selected} glowClass="border-purple-300/90 shadow-[0_0_24px_rgba(196,181,253,0.45)]" />
      <Handle type="target" position={Position.Left} className="!bg-purple-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Bottom} className="!bg-purple-500 !w-3 !h-3" />
      <NodeActions />
      <div className="font-bold text-xl text-purple-400 truncate text-center">{t("workflowControl.labels.runtimeServices")}</div>
    </div>
  );
}

function ProviderNode({ selected = false }: NodeProps) {
  const t = useTranslation();
  return (
    <div className="group px-8 py-6 h-[80px] flex flex-col justify-center shadow-[0_0_15px_rgba(249,115,22,0.3)] hover:shadow-[0_0_25px_rgba(249,115,22,0.5)] transition-shadow duration-300 rounded-xl bg-slate-900 border-2 border-orange-500 text-orange-100 min-w-[210px] relative">
      <SelectedNodePulse selected={selected} glowClass="border-orange-300/90 shadow-[0_0_24px_rgba(253,186,116,0.45)]" />
      <Handle type="target" position={Position.Left} className="!bg-orange-500 !w-3 !h-3" />
      <NodeActions />
      <div className="font-bold text-xl text-orange-400 truncate text-center">{t("workflowControl.labels.currentProvider")}</div>
    </div>
  );
}

function EmbeddingNode({ selected = false }: NodeProps) {
  const t = useTranslation();
  return (
    <div className="group px-8 py-6 h-[80px] flex flex-col justify-center shadow-[0_0_15px_rgba(236,72,153,0.3)] hover:shadow-[0_0_25px_rgba(236,72,153,0.5)] transition-shadow duration-300 rounded-xl bg-slate-900 border-2 border-pink-500 text-pink-100 min-w-[210px] relative">
      <SelectedNodePulse selected={selected} glowClass="border-pink-300/90 shadow-[0_0_24px_rgba(249,168,212,0.45)]" />
      <Handle type="target" position={Position.Left} className="!bg-pink-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Bottom} className="!bg-pink-500 !w-3 !h-3" />
      <NodeActions />
      <div className="font-bold text-xl text-pink-400 truncate text-center">{t("workflowControl.labels.currentEmbedding")}</div>
    </div>
  );
}

function IntentNode({ selected = false }: NodeProps) {
  const t = useTranslation();
  return (
    <div className="group px-8 py-6 h-[80px] flex flex-col justify-center shadow-[0_0_15px_rgba(234,179,8,0.3)] hover:shadow-[0_0_25px_rgba(234,179,8,0.5)] transition-shadow duration-300 rounded-xl bg-slate-900 border-2 border-yellow-500 text-yellow-100 min-w-[210px] relative">
      <SelectedNodePulse selected={selected} glowClass="border-yellow-300/90 shadow-[0_0_24px_rgba(253,224,71,0.45)]" />
      <Handle type="target" position={Position.Left} className="!bg-yellow-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Bottom} className="!bg-yellow-500 !w-3 !h-3" />
      <NodeActions />
      <div className="font-bold text-xl text-yellow-400 truncate text-center">{t("workflowControl.sections.intent")}</div>
    </div>
  );
}
