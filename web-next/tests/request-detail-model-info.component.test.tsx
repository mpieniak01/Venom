import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";

import { ModelInfoSection } from "../components/cockpit/drawer-sections";
import type { HistoryRequestDetail } from "../lib/types";

const labels: Record<string, string> = {
  "cockpit.requestDetails.modelInfoTitle": "Model info",
  "cockpit.requestDetails.runtimeExecutionModelLabel": "Runtime execution model",
  "cockpit.requestDetails.selectedBaseModelLabel": "Selected base model",
  "cockpit.requestDetails.providerLabel": "Server / Provider",
  "cockpit.requestDetails.endpointLabel": "Endpoint",
  "cockpit.requestDetails.runtimeIdLabel": "Runtime ID",
  "cockpit.requestDetails.adapterAppliedLabel": "Adapter",
  "cockpit.requestDetails.adapterAppliedYes": "yes (request via adapter)",
  "cockpit.requestDetails.adapterAppliedNo": "no (base model)",
  "cockpit.requestDetails.adapterIdLabel": "Adapter ID",
  "cockpit.requestDetails.runtimeFlowOnnxNote":
    "ONNX requests can use a dedicated task flow (OnnxTask), so the diagnostics graph may be shorter than for Ollama.",
};

function t(key: string): string {
  return labels[key] || key;
}

afterEach(() => {
  cleanup();
});

describe("ModelInfoSection", () => {
  it("shows runtime execution model and selected base model separately", () => {
    const detail = {
      llm_model: "venom-adapter-training_20260314_164432",
      routing_decision: {
        model: "gemma-3-4b-it",
      },
      llm_provider: "onnx",
      llm_endpoint: "local",
      llm_runtime_id: "onnx",
      adapter_applied: true,
      adapter_id: "training_20260314_164432",
    } as unknown as HistoryRequestDetail;

    render(<ModelInfoSection historyDetail={detail} t={t} />);

    assert.ok(screen.getByText("Runtime execution model"));
    assert.ok(screen.getByText("venom-adapter-training_20260314_164432"));
    assert.ok(screen.getByText("Selected base model"));
    assert.ok(screen.getByText("gemma-3-4b-it"));
  });

  it("shows full runtime id and ONNX flow note", () => {
    const detail = {
      llm_model: "venom-adapter-training_20260314_164432",
      routing_decision: {
        model: "gemma-3-4b-it",
      },
      llm_runtime_id: "onnx@local-task-flow",
      adapter_applied: true,
    } as unknown as HistoryRequestDetail;

    render(<ModelInfoSection historyDetail={detail} t={t} />);

    assert.ok(screen.getByText("onnx@local-task-flow"));
    assert.ok(
      screen.getByText(
        "ONNX requests can use a dedicated task flow (OnnxTask), so the diagnostics graph may be shorter than for Ollama.",
      ),
    );
  });
});
