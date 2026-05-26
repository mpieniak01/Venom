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

  it("renders component snapshot caption when provided", () => {
    render(
      <RuntimeDiagnosticsPanel
        title="Runtime diagnostics"
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
        componentSnapshotCaption="Ostatnia sesja"
        componentSnapshotVersion="deadbeef12345678"
        componentSnapshotTimestampMs={1_746_050_336_000}
        liveComponentSnapshotVersion="deadbeef12345678"
        liveComponentSnapshotTimestampMs={1_746_050_337_000}
      />,
    );

    assert.ok(screen.getByText("Ostatnia sesja"));
    assert.ok(screen.getAllByText(/deadbeef12345678/i).length >= 2);
    assert.ok(screen.getByText(/zgodny z live|matches live|entspricht live/i));
  });

  it("renders annotated audio-only trace semantics", () => {
    render(
      <RuntimeDiagnosticsPanel
        title="Runtime diagnostics"
        trace={["input_router", "image_preprocessor", "ocr_or_vision", "retrieval", "main_generation", "assistant_postprocess", "audio_output"]}
        traceAnnotations={[
          { label: "Input router", status: "active", note: "audio input routed" },
          { label: "Image preprocessor", status: "no-op", note: "audio-only voice session" },
          { label: "OCR / vision", status: "no-op", note: "audio-only voice session" },
          { label: "Retrieval", status: "no-op", note: "audio-only voice session" },
          { label: "Main generation", status: "active", note: "Gemma response" },
          { label: "Assistant postprocess", status: "active", note: "response shaping" },
          { label: "Audio output", status: "active", note: "tts output" },
        ]}
      />,
    );

    assert.ok(screen.getByText(/Image preprocessor · no-op/i));
    assert.ok(screen.getByText(/OCR \/ vision · no-op/i));
    assert.ok(screen.getByText(/Retrieval · no-op/i));
    assert.ok(screen.getByText(/Main generation · active/i));
    assert.ok(screen.getByText(/audio-only voice session/i));
  });
});
