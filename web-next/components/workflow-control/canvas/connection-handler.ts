import { addEdge, type Connection, type Edge, type Node } from "@xyflow/react";

import type { ConnectionValidationReasonCode } from "@/lib/workflow-policy";
import { validateConnection } from "@/lib/workflow-policy";

import { resolveConnectionReasonText, type TranslateFn } from "./value-formatters";

export interface ConnectionValidationResult {
  isValid: boolean;
  reasonCode?: ConnectionValidationReasonCode;
  reasonDetail?: string;
}

export type ValidateConnectionFn = (source: Node, target: Node) => ConnectionValidationResult;

export interface ConnectHandlerDeps {
  readOnly: boolean;
  nodes: Node[];
  t: TranslateFn;
  pushToast: (message: string, tone?: "success" | "error" | "warning" | "info") => void;
  setEdges: (updater: (edges: Edge[]) => Edge[]) => void;
  validateConnectionFn?: ValidateConnectionFn;
}

export function handleWorkflowConnect(
  params: Connection,
  {
    readOnly,
    nodes,
    t,
    pushToast,
    setEdges,
    validateConnectionFn = validateConnection,
  }: ConnectHandlerDeps,
): void {
  if (readOnly) {
    return;
  }

  const sourceNode = nodes.find((node) => node.id === params.source);
  const targetNode = nodes.find((node) => node.id === params.target);

  if (sourceNode && targetNode) {
    const validation = validateConnectionFn(sourceNode, targetNode);
    if (!validation.isValid) {
      const reasonText = resolveConnectionReasonText(
        validation.reasonCode,
        validation.reasonDetail,
        t,
      );
      pushToast(`${t("workflowControl.messages.connectionRejected")}: ${reasonText}`, "error");
      return;
    }
  }

  setEdges((existingEdges: Edge[]) => addEdge(params, existingEdges));
}
