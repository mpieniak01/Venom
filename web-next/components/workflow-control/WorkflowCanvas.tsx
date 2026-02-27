"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  MiniMap,
  ReactFlow,
  addEdge,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useToast } from "@/components/ui/toast";
import { useTranslation } from "@/lib/i18n";
import { validateConnection } from "@/lib/workflow-policy";
import type { SystemState } from "@/types/workflow-control";

import { DEFAULT_EDGE_OPTIONS, FIT_VIEW_OPTIONS, miniMapNodeColor } from "./canvas/config";
import { buildCanvasGraph, graphSignature } from "./canvas/layout";
import { workflowCanvasNodeTypes } from "./canvas/node-components";
import { resolveConnectionReasonText } from "./canvas/value-formatters";

interface WorkflowCanvasProps {
  systemState: SystemState | null;
  onNodeClick?: (node: Node) => void;
  onEdgesChange?: (changes: EdgeChange[]) => void;
  onNodesChange?: (changes: NodeChange<Node>[]) => void;
  readOnly?: boolean;
}

export function WorkflowCanvas({
  systemState,
  onNodeClick,
  onEdgesChange: onEdgesChangeProp,
  onNodesChange: onNodesChangeProp,
  readOnly = false,
}: Readonly<WorkflowCanvasProps>) {
  const t = useTranslation();
  const { pushToast } = useToast();

  const { initialNodes, initialEdges } = useMemo(
    () => buildCanvasGraph(systemState, readOnly),
    [systemState, readOnly]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const lastGraphSignatureRef = useRef<string>("");

  useEffect(() => {
    const signature = graphSignature(initialNodes, initialEdges);
    if (lastGraphSignatureRef.current === signature) {
      return;
    }
    lastGraphSignatureRef.current = signature;
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      onNodesChange(changes);
      onNodesChangeProp?.(changes);
    },
    [onNodesChange, onNodesChangeProp]
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(changes);
      onEdgesChangeProp?.(changes);
    },
    [onEdgesChange, onEdgesChangeProp]
  );

  const onConnect = useCallback(
    (params: Connection) => {
      if (readOnly) {
        return;
      }

      const sourceNode = nodes.find((node) => node.id === params.source);
      const targetNode = nodes.find((node) => node.id === params.target);

      if (sourceNode && targetNode) {
        const validation = validateConnection(sourceNode, targetNode);
        if (!validation.isValid) {
          const reasonText = resolveConnectionReasonText(
            validation.reasonCode,
            validation.reasonDetail,
            t
          );
          pushToast(
            `${t("workflowControl.messages.connectionRejected")}: ${reasonText}`,
            "error"
          );
          return;
        }
      }

      setEdges((existingEdges: Edge[]) => addEdge(params, existingEdges));
    },
    [nodes, pushToast, readOnly, setEdges, t]
  );

  return (
    <div className="h-full w-full bg-slate-50 dark:bg-slate-950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => onNodeClick?.(node)}
        nodeTypes={workflowCanvasNodeTypes}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        proOptions={{ hideAttribution: true }}
      >
        <MiniMap
          position="top-right"
          nodeColor={miniMapNodeColor}
          className="!bg-slate-950 rounded-lg border border-slate-800 shadow-xl"
          maskColor="rgba(2, 6, 23, 0.7)"
        />
      </ReactFlow>
    </div>
  );
}
