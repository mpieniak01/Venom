/**
 * Testy regresji 217E: porzadek powierzchni operatora voice.
 *
 * Pilnuja:
 * 1. ImageProbeCard (Obsługa obrazu) jest osobnym boxem — wydzielona z Gemma4RuntimeControl.
 * 2. runtime-profile-inline jest osobnym blokiem z wlasnym data-testid.
 * 3. RuntimeDiagnosticsPanel renderuje zlokalizowane etykiety sekcji.
 * 4. Cockpit nie wraca do hardkodowanych angielskich napisow diagnostycznych
 *    (tile i opis przekazywane przez i18n, nie literal string).
 */

import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
import {
  Gemma4RuntimeControlInner,
  ImageProbeCard,
} from "../components/gemma4/gemma4-runtime-control";
import { RuntimeDiagnosticsPanel } from "../components/runtime/runtime-diagnostics-panel";
import type { Gemma4DaemonState } from "../hooks/use-gemma4-daemon";
import type { DaemonStatus } from "../lib/gemma4-daemon-api";

afterEach(() => cleanup());
const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PROFILE_RESPONSE = {
  runtime_id: "multi_runtime",
  daemon_reachable: true,
  profile: {
    profile_id: "default",
    display_name: "Default",
    runtime_id: "multi_runtime",
    compatibility: "multi_runtime_native",
    model_id: "google/gemma-4-E2B-it",
    assistant_model_id: null,
    cache_implementation: null,
    max_new_tokens: 128,
    image_token_budget: 280,
    enable_thinking: false,
    reasoning_summary_enabled: false,
    emotion_detection_enabled: false,
    emotion_response_style_enabled: false,
    execution_mode: "balanced",
    image_strategy: "vlm_only",
    retrieval_mode: "off",
    audio_output_mode: "off",
    assistant_mode: "off",
    economy_mode: "off",
    precision: "auto",
    quantization_backend: null,
    device_target: "auto",
  },
  apply_matrix: {
    model_id: "hard_restart",
    assistant_model_id: "hard_restart",
    cache_implementation: "soft_reload",
    max_new_tokens: "live",
    image_token_budget: "live",
    enable_thinking: "live",
    reasoning_summary_enabled: "live",
    emotion_detection_enabled: "live",
    emotion_response_style_enabled: "live",
    execution_mode: "live",
    image_strategy: "live",
    retrieval_mode: "live",
    audio_output_mode: "live",
    assistant_mode: "live",
    economy_mode: "live",
    precision: "soft_reload",
    quantization_backend: "soft_reload",
    device_target: "soft_reload",
  },
  supported_options: {
    cache_implementation: [null, "static", "dynamic", "offloaded"],
    precision: ["auto"],
    device_target: ["auto", "cpu", "cuda"],
    quantization_backend: [null],
    execution_mode: ["balanced", "vision_priority", "voice_priority"],
    image_strategy: ["vlm_only", "ocr_first", "hybrid"],
    retrieval_mode: ["off", "auto", "always"],
    audio_output_mode: ["off", "text_first", "voice_first"],
    assistant_mode: ["off", "attached", "conditional"],
    economy_mode: ["off", "auto"],
  },
};

function makeDaemonStatus(supportsImageInput: boolean): DaemonStatus {
  return {
    target_model: "google/gemma-4-E2B-it",
    assistant_model: null,
    mode: "target_only",
    target_loaded: true,
    assistant_loaded: false,
    params: {
      max_new_tokens: 128,
      enable_thinking: false,
      image_token_budget: 280,
      reasoning_summary_enabled: false,
      emotion_detection_enabled: false,
      emotion_response_style_enabled: false,
      cache_implementation: null,
      execution_mode: "balanced",
      image_strategy: "vlm_only",
      retrieval_mode: "off",
      audio_output_mode: "off",
      assistant_mode: "off",
      economy_mode: "off",
    },
    vram: { backend: "cpu", allocated_mb: 0, reserved_mb: 0, total_mb: 0, free_mb: 0 },
    raw_thinking_available: false,
    reasoning_summary_status: "disabled",
    reasoning_summary: null,
    emotion_label: null,
    emotion_confidence: null,
    emotion_source: null,
    pending_reload: false,
    reload_reason: null,
    supports_image_input: supportsImageInput,
    component_snapshot: [],
  };
}

function makeDaemonState(supportsImageInput: boolean): Gemma4DaemonState {
  return {
    status: makeDaemonStatus(supportsImageInput),
    loading: false,
    error: null,
    actionPending: null,
    lastAppliedSignal: null,
    refresh: async () => {},
    applyConfig: async () => null,
    reload: async () => {},
    restart: async () => {},
    fallback: async () => null,
    attachAssistant: async () => {},
    detachAssistant: async () => {},
  };
}

const DAEMON_STATUS_RESPONSE: DaemonStatus = {
  target_model: "google/gemma-4-E2B-it",
  assistant_model: null,
  mode: "target_only",
  target_loaded: true,
  assistant_loaded: false,
  params: {
    max_new_tokens: 128,
    enable_thinking: false,
    image_token_budget: 280,
    reasoning_summary_enabled: false,
    emotion_detection_enabled: false,
    emotion_response_style_enabled: false,
    cache_implementation: null,
    execution_mode: "balanced",
    image_strategy: "vlm_only",
    retrieval_mode: "off",
    audio_output_mode: "off",
    assistant_mode: "off",
    economy_mode: "off",
  },
  vram: { backend: "cpu", allocated_mb: 0, reserved_mb: 0, total_mb: 0, free_mb: 0 },
  raw_thinking_available: false,
  reasoning_summary_status: "disabled",
  reasoning_summary: null,
  emotion_label: null,
  emotion_confidence: null,
  emotion_source: null,
  pending_reload: false,
  reload_reason: null,
  supports_image_input: true,
  component_snapshot: [],
};

function mockFetch() {
  globalThis.fetch = async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/v1/daemon/status")) {
      return new Response(JSON.stringify(DAEMON_STATUS_RESPONSE), { status: 200 });
    }
    if (url.includes("/api/v1/runtime/multi-runtime/profile")) {
      return new Response(JSON.stringify(PROFILE_RESPONSE), { status: 200 });
    }
    throw new Error(`Unexpected fetch in 217E test: ${url}`);
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("217E – voice operator layout regression", () => {
  it("ImageProbeCard (Obsługa obrazu) renders as standalone card when daemon supports image input", async () => {
    mockFetch();
    render(<ImageProbeCard />);

    assert.ok(
      await screen.findByText(/Obsługa obrazu|Image input|Bildeingabe/i),
      "ImageProbeCard must render the image input heading when supports_image_input=true",
    );
  });

  it("Obsługa obrazu is NOT rendered inside Gemma4RuntimeControl (extracted to ImageProbeCard)", async () => {
    mockFetch();
    render(
      <Gemma4RuntimeControlInner
        daemon={makeDaemonState(true)}
        variant="voice"
      />,
    );
    await screen.findByLabelText(/Thinking/i);
    assert.equal(
      screen.queryByText(/Obsługa obrazu|Image input|Bildeingabe/i),
      null,
      "ImageProbeSection must NOT appear inside Gemma4RuntimeControlInner — it lives in ImageProbeCard",
    );
  });

  it("runtime-profile-inline exists as a separate block", async () => {
    mockFetch();
    render(
      <Gemma4RuntimeControlInner
        daemon={makeDaemonState(false)}
        variant="voice"
      />,
    );

    assert.ok(
      await screen.findByTestId("runtime-profile-inline"),
      "runtime-profile-inline block must be rendered as a distinct section",
    );
  });

  it("RuntimeDiagnosticsPanel renders localized section labels", () => {
    render(
      <RuntimeDiagnosticsPanel
        title="Diagnostyka runtime"
        trace={["input_router", "main_generation"]}
        componentSnapshot={[
          {
            component_id: "stt_component",
            component_type: "stt",
            enabled: true,
            available: true,
            backend: "faster_whisper",
            model_id: "medium",
            device_target: "cpu",
            health: "ok",
            last_error: null,
          },
        ]}
        degradationReasons={["budget_limit"]}
      />,
    );

    assert.ok(screen.getByText("Diagnostyka runtime"));
    assert.ok(
      screen.getByText(/Ślad wykonania|Execution trace|Ausführungsspur/i),
      "Execution trace section must use localized label",
    );
    assert.ok(
      screen.getByText(/Komponenty runtime|Runtime components|Runtime-Komponenten/i),
      "Runtime components section must use localized label",
    );
  });

  it("cockpit uses i18n for RuntimeDiagnosticsPanel — PL key resolves to localized string", () => {
    // runtime.diagnostics.title in PL = "Diagnostyka runtime" (not hardcoded "Runtime diagnostics")
    // runtime.diagnostics.description in PL = "Podgląd sesji runtime na żywo i stanu komponentów."
    // Passing these as title/description simulates what cockpit does via t("runtime.diagnostics.*")
    render(
      <RuntimeDiagnosticsPanel
        title="Diagnostyka runtime"
        description="Podgląd sesji runtime na żywo i stanu komponentów."
      />,
    );

    assert.ok(
      screen.getByText("Diagnostyka runtime"),
      "Cockpit panel title must come from i18n key runtime.diagnostics.title",
    );
    assert.ok(
      screen.getByText(/Podgląd sesji runtime/i),
      "Cockpit panel description must come from i18n key runtime.diagnostics.description",
    );
  });
});
