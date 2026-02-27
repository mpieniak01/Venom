import assert from "node:assert/strict";
import { describe, it } from "node:test";

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
      { source: "runtime", target: "provider" },
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
      { source: "runtime", target: "provider" },
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
    assert.equal(pushedMessage, "Connection rejected: Invalid connection");
  });

  it("adds edge for valid connection", () => {
    let updater: ((edges: Array<{ id: string; source: string; target: string }>) => unknown) | null =
      null;

    handleWorkflowConnect(
      { source: "runtime", target: "provider" },
      {
        readOnly: false,
        nodes: NODES,
        t: (path) => path,
        pushToast: () => {
          throw new Error("pushToast should not be called for valid connection");
        },
        setEdges: (nextUpdater) => {
          updater = nextUpdater;
        },
        validateConnectionFn: () => ({ isValid: true }),
      },
    );

    assert.ok(updater, "setEdges updater must be provided");
    const existing = [{ id: "e-1", source: "decision", target: "intent" }];
    const next = updater!(existing) as Array<{ id: string; source: string; target: string }>;
    assert.equal(next.length, existing.length + 1);
    assert.equal(next.at(-1)?.source, "runtime");
    assert.equal(next.at(-1)?.target, "provider");
  });
});
