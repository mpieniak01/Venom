import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { Edge } from "@xyflow/react";

import { handleWorkflowConnect } from "../components/workflow-control/canvas/connection-handler";

const NODES = [
  { id: "runtime", type: "runtime", data: {}, position: { x: 0, y: 0 } },
  { id: "provider", type: "provider", data: {}, position: { x: 0, y: 0 } },
];

describe("workflow canvas connection handler", () => {
  it("does nothing in readOnly mode", () => {
    let pushCount = 0;
    let setEdgesCount = 0;

    handleWorkflowConnect(
      { source: "runtime", target: "provider", sourceHandle: null, targetHandle: null },
      {
        readOnly: true,
        nodes: NODES,
        t: (path) => path,
        pushToast: () => {
          pushCount += 1;
        },
        setEdges: () => {
          setEdgesCount += 1;
        },
      },
    );

    assert.equal(pushCount, 0);
    assert.equal(setEdgesCount, 0);
  });

  it("pushes translated error toast for invalid connection", () => {
    let pushedMessage = "";
    let pushedVariant = "";
    let setEdgesCount = 0;

    handleWorkflowConnect(
      { source: "runtime", target: "provider", sourceHandle: null, targetHandle: null },
      {
        readOnly: false,
        nodes: NODES,
        t: (path) => {
          if (path === "workflowControl.messages.connectionRejected") {
            return "Connection rejected";
          }
          if (path === "workflowControl.messages.invalid_connection") {
            return "Invalid connection";
          }
          return path;
        },
        pushToast: (message, variant) => {
          pushedMessage = message;
          pushedVariant = variant || "";
        },
        setEdges: () => {
          setEdgesCount += 1;
        },
        validateConnectionFn: () => ({
          isValid: false,
          reasonCode: "invalid_connection",
          reasonDetail: "runtime cannot connect to provider",
        }),
      },
    );

    assert.equal(setEdgesCount, 0);
    assert.equal(pushedVariant, "error");
    assert.equal(
      pushedMessage,
      "Connection rejected: Invalid connection: runtime cannot connect to provider",
    );
  });

  it("adds edge for valid connection", () => {
    const existing: Edge[] = [
      { id: "e-1", source: "decision", target: "intent", sourceHandle: null, targetHandle: null },
    ];
    const capture: { next: Edge[] } = { next: existing };

    handleWorkflowConnect(
      { source: "runtime", target: "provider", sourceHandle: null, targetHandle: null },
      {
        readOnly: false,
        nodes: NODES,
        t: (path) => path,
        pushToast: () => {
          throw new Error("pushToast should not be called for valid connection");
        },
        setEdges: (nextUpdater) => {
          capture.next = nextUpdater(existing);
        },
        validateConnectionFn: () => ({ isValid: true }),
      },
    );

    const next = capture.next;
    const last = next[next.length - 1];
    assert.equal(next.length, existing.length + 1);
    assert.equal(last?.source, "runtime");
    assert.equal(last?.target, "provider");
  });
});
