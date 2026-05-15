import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
import { RuntimeDiagnosticsPanel } from "../components/runtime/runtime-diagnostics-panel";

afterEach(() => cleanup());

describe("RuntimeDiagnosticsPanel", () => {
  it("renders summary, components and degradations", () => {
    render(
      <RuntimeDiagnosticsPanel
        title="Runtime diagnostics"
        description="Live snapshot"
        summaryItems={[
          { label: "Policy", value: "balanced|vlm_only", tone: "neutral" },
          { label: "Retrieval", value: "graph", tone: "success" },
        ]}
        trace={["input_router", "retrieval", "main_generation"]}
        componentSnapshot={[
          {
            component_id: "main_model",
            component_type: "model",
            enabled: true,
            available: true,
            backend: "cuda",
            model_id: "google/gemma-4-E2B-it",
            device_target: "cuda",
            health: "ok",
            last_error: null,
          },
        ]}
        degradationReasons={["retrieval fallback"]}
      />,
    );

    assert.ok(screen.getByText("Runtime diagnostics"));
    assert.ok(
      screen.getByText(/Execution trace|Ślad wykonania|Ausführungsspur/i),
    );
    assert.ok(
      screen.getByText(/Runtime components|Komponenty runtime|Runtime-Komponenten/i),
    );
    assert.ok(screen.getByText("balanced|vlm_only"));
    assert.ok(screen.getByText("main_model"));
    assert.ok(screen.getByText("retrieval fallback"));
  });
});
