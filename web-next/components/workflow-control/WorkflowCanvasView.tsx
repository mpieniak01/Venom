"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  MiniMap,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type Node,
  type NodeChange,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";

import { useToast } from "@/components/ui/toast";
import { useTranslation } from "@/lib/i18n";
import type { SystemState } from "@/types/workflow-control";

import { handleWorkflowConnect } from "./canvas/connection-handler";
import { DEFAULT_EDGE_OPTIONS, FIT_VIEW_OPTIONS, miniMapNodeColor } from "./canvas/config";
import { workflowCanvasEdgeTypes } from "./canvas/edge-components";
import { buildCanvasGraph, graphSignature } from "./canvas/layout";
import { workflowCanvasNodeTypes } from "./canvas/node-components";

type UseNodesStateHook = typeof useNodesState;
type UseEdgesStateHook = typeof useEdgesState;
type ReactFlowComponent = typeof ReactFlow;
type MiniMapComponent = typeof MiniMap;

export interface WorkflowCanvasTestAdapter {
  ReactFlowComponent?: ReactFlowComponent;
  MiniMapComponent?: MiniMapComponent;
  useNodesStateHook?: UseNodesStateHook;
  useEdgesStateHook?: UseEdgesStateHook;
}

interface WorkflowCanvasProps {
  systemState: SystemState | null;
  onNodeClick?: (node: Node) => void;
  onEdgesChange?: (changes: EdgeChange[]) => void;
  onNodesChange?: (changes: NodeChange<Node>[]) => void;
  readOnly?: boolean;
  testAdapter?: WorkflowCanvasTestAdapter;
}

export function WorkflowCanvas({
  systemState,
  onNodeClick,
  onEdgesChange: onEdgesChangeProp,
  onNodesChange: onNodesChangeProp,
  readOnly: _readOnly = true,
  testAdapter,
}: Readonly<WorkflowCanvasProps>) {
  const t = useTranslation();
  const { pushToast } = useToast();
  const [expandedGroupKeys, setExpandedGroupKeys] = useState<Set<string>>(new Set());
  void _readOnly;
  const UseNodesStateHook = testAdapter?.useNodesStateHook ?? useNodesState;
  const UseEdgesStateHook = testAdapter?.useEdgesStateHook ?? useEdgesState;
  const ReactFlowComponent = testAdapter?.ReactFlowComponent ?? ReactFlow;
  const MiniMapView = testAdapter?.MiniMapComponent ?? MiniMap;

  const toggleExpandedGroup = useCallback((groupKey: string) => {
    setExpandedGroupKeys((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) {
        next.delete(groupKey);
      } else {
        next.add(groupKey);
      }
      return next;
    });
  }, []);

  const canvasReadOnly = true;
  const { initialNodes: rawNodes, initialEdges } = useMemo(
    () => buildCanvasGraph(systemState, canvasReadOnly, { expandedGroupKeys }),
    [systemState, canvasReadOnly, expandedGroupKeys]
  );
  const initialNodes = useMemo(
    () =>
      rawNodes.map((node) => {
        if (node.type !== "execution_step") {
          return node;
        }
        return {
          ...node,
          data: {
            ...(node.data ?? {}),
            onToggleGroup: toggleExpandedGroup,
          },
        };
      }),
    [rawNodes, toggleExpandedGroup],
  );

  const [nodes, setNodes, onNodesChange] = UseNodesStateHook(initialNodes);
  const [edges, setEdges, onEdgesChange] = UseEdgesStateHook(initialEdges);
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
      handleWorkflowConnect(params, {
        readOnly: canvasReadOnly,
        nodes,
        t,
        pushToast,
        setEdges,
      });
    },
    [canvasReadOnly, nodes, pushToast, setEdges, t]
  );

  return (
    <div className="h-full w-full bg-[color:var(--ui-surface)]">
      <ReactFlowComponent
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => onNodeClick?.(node)}
        nodeTypes={workflowCanvasNodeTypes}
        edgeTypes={workflowCanvasEdgeTypes}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        proOptions={{ hideAttribution: true }}
      >
        <MiniMapView
          position="top-right"
          nodeColor={miniMapNodeColor}
          className="rounded-lg border border-[color:var(--ui-border)] !bg-[color:var(--bg-panel)] shadow-xl"
          maskColor="rgba(2, 6, 23, 0.7)"
        />
      </ReactFlowComponent>
    </div>
  );
}
