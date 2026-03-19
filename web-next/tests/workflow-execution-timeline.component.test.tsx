import "./component-test-setup";

import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";

import { WorkflowExecutionTimeline } from "../components/workflow-control/WorkflowExecutionTimeline";

afterEach(() => {
  cleanup();
});

describe("WorkflowExecutionTimeline", () => {
  it("renders runtime services and execution steps", () => {
    render(
      <WorkflowExecutionTimeline
        runtimeServices={[
          {
            id: "backend",
            name: "Backend",
            kind: "backend",
            status: "running",
            allowed_actions: ["stop", "restart"],
            dependencies: [],
          },
          {
            id: "ui",
            name: "UI",
            kind: "ui",
            status: "running",
            allowed_actions: ["stop"],
            dependencies: ["backend"],
          },
        ]}
        executionSteps={[
          {
            id: "step-1",
            component: "intent",
            action: "classify",
            status: "running",
            stage: "intent",
            related_service_id: "backend",
            related_config_keys: ["INTENT_MODE"],
          },
          {
            id: "step-2",
            component: "kernel",
            action: "route",
            status: "ok",
            stage: "kernel",
            depends_on_step_id: "step-1",
          },
        ]}
        selection={null}
        onSelectService={mock.fn(() => undefined)}
        onSelectStep={mock.fn(() => undefined)}
      />,
    );

    assert.ok(screen.getByText("Backend"));
    assert.ok(screen.getByText("classify"));
    assert.ok(screen.getAllByText("backend").length >= 1);
    assert.ok(screen.getByText("INTENT_MODE"));
    assert.ok(screen.getAllByText(/Tor runtime/i).length >= 1);
    assert.ok(screen.getAllByText(/Tor wykonania/i).length >= 1);
    assert.ok(screen.getByText(/Poprzednik/i));
  });
});
