import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Gemma4DaemonState } from "../hooks/use-gemma4-daemon";
import type { DaemonStatus } from "../lib/gemma4-daemon-api";
import { Gemma4RuntimeControlInner } from "../components/gemma4/gemma4-runtime-control";

afterEach(() => cleanup());
const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

beforeEach(() => {
  globalThis.fetch = async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/v1/daemon/status")) {
      return new Response(
        JSON.stringify({
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
          vram: {
            backend: "cpu",
            allocated_mb: 0,
            reserved_mb: 0,
            total_mb: 0,
            free_mb: 0,
          },
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
        }),
        { status: 200 },
      );
    }
    if (url.includes("/api/v1/runtime/multi-runtime/profile")) {
      return new Response(
        JSON.stringify({
          runtime_id: "multi_runtime",
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
            precision: ["auto", "float16", "bfloat16", "float32", "int4", "int8"],
            device_target: ["auto", "cpu", "cuda"],
            quantization_backend: [null, "bitsandbytes"],
            execution_mode: ["balanced", "vision_priority", "voice_priority"],
            image_strategy: ["vlm_only", "ocr_first", "hybrid"],
            retrieval_mode: ["off", "auto", "always"],
            audio_output_mode: ["off", "text_first", "voice_first"],
            assistant_mode: ["off", "attached", "conditional"],
            economy_mode: ["off", "auto"],
          },
          daemon_reachable: true,
        }),
        { status: 200 },
      );
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  };
});

const noop = async () => { };

function makeStatus(overrides: Partial<DaemonStatus> = {}): DaemonStatus {
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
    vram: {
      backend: "cpu",
      allocated_mb: 0,
      reserved_mb: 0,
      total_mb: 0,
      free_mb: 0,
    },
    raw_thinking_available: false,
    reasoning_summary_status: "disabled",
    reasoning_summary: null,
    emotion_label: null,
    emotion_confidence: null,
    emotion_source: null,
    pending_reload: false,
    reload_reason: null,
    supports_image_input: true,
    component_snapshot: [
      {
        component_id: "main_model",
        component_type: "model",
        enabled: true,
        available: true,
        backend: "cpu",
        model_id: "google/gemma-4-E2B-it",
        device_target: "cpu",
        health: "ok",
        last_error: null,
      },
    ],
    ...overrides,
  };
}

function makeState(overrides: Partial<Gemma4DaemonState> = {}): Gemma4DaemonState {
  return {
    status: makeStatus(),
    loading: false,
    error: null,
    actionPending: null,
    lastAppliedSignal: null,
    refresh: noop,
    applyConfig: async () => null,
    reload: noop,
    restart: noop,
    fallback: async () => null,
    attachAssistant: async () => { },
    detachAssistant: async () => { },
    ...overrides,
  };
}

function makeProfileMatrix() {
  return {
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
  };
}

function makeSupportedOptions() {
  return {
    cache_implementation: [null, "static", "dynamic", "offloaded"],
    precision: ["auto", "float16", "bfloat16", "float32", "int4", "int8"],
    device_target: ["auto", "cpu", "cuda"],
    quantization_backend: [null, "bitsandbytes"],
    execution_mode: ["balanced", "vision_priority", "voice_priority"],
    image_strategy: ["vlm_only", "ocr_first", "hybrid"],
    retrieval_mode: ["off", "auto", "always"],
    audio_output_mode: ["off", "text_first", "voice_first"],
    assistant_mode: ["off", "attached", "conditional"],
    economy_mode: ["off", "auto"],
  };
}

function renderControl(
  state: Gemma4DaemonState,
  variant: "cockpit" | "voice" = "voice",
  runtimeSnapshot?: {
    provider?: string | null;
    model_name?: string | null;
    runtime_capabilities?: {
      compatibility_profile?: string | null;
      probe_status?: string | null;
    } | null;
    voice_pipeline?: {
      profile?: string | null;
      tts?: string | null;
    } | null;
  } | null,
  assistantModels: string[] = [],
) {
  return render(
    <Gemma4RuntimeControlInner
      daemon={state}
      variant={variant}
      runtimeSnapshot={runtimeSnapshot ?? null}
      assistantModels={assistantModels}
    />,
  );
}

describe("Gemma4RuntimeControl — loading state", () => {
  it("shows loading message when status is null and loading=true", () => {
    renderControl(makeState({ status: null, loading: true }));
    assert.ok(screen.queryByText(/daemon/i) !== null || screen.queryByText(/łącz/i) !== null);
  });
});

describe("Gemma4RuntimeControl — error state", () => {
  it("shows unavailable message when no status and error present", () => {
    renderControl(makeState({ status: null, loading: false, error: "connection refused" }));
    assert.ok(
      document.body.textContent?.toLowerCase().includes("niedostępny") ||
      document.body.textContent?.toLowerCase().includes("unavailable"),
    );
  });

  it("shows runtime snapshot details when daemon is unavailable", () => {
    renderControl(
      makeState({
        status: null,
        loading: false,
        error: "Failed to fetch",
      }),
      "voice",
      {
        provider: "ollama",
        model_name: "gemma2:2b",
        runtime_capabilities: {
          compatibility_profile: "gemma4_audio_native",
          probe_status: "verified",
        },
        voice_pipeline: {
          profile: "gemma4_audio_native",
          tts: "piper",
        },
      },
    );
    assert.ok(
      document.body.textContent?.toLowerCase().includes("failed to fetch"),
    );
    assert.ok(document.body.textContent?.includes("ollama / gemma2:2b"));
  });
});

describe("Gemma4RuntimeControl — normal state (voice variant)", () => {
  it("renders target model name", () => {
    renderControl(makeState());
    assert.ok(screen.getByText("google/gemma-4-E2B-it"));
  });

  it("renders Gemma 4 Runtime title", () => {
    renderControl(makeState());
    assert.ok(screen.getByText("Gemma 4 Runtime"));
  });

  it("renders Apply button", () => {
    renderControl(makeState());
    assert.ok(screen.getByTestId("apply-button"));
  });

  it("renders Reload and Restart buttons", () => {
    renderControl(makeState());
    assert.ok(screen.getByTestId("reload-button"));
    assert.ok(screen.getByTestId("restart-button"));
  });

  it("renders Fallback button", () => {
    renderControl(makeState());
    assert.ok(screen.getByTestId("fallback-button"));
  });

  it("renders inline runtime profile controls inside the daemon card", async () => {
    renderControl(makeState());
    assert.ok(await screen.findByTestId("runtime-profile-inline"));
    assert.equal(screen.queryByTestId("multi-runtime-profile-panel"), null);
    assert.ok(screen.getByText("Profil runtime"));
    assert.ok(screen.getByText("Polityka wykonania"));
    assert.ok(screen.getByText("Snapshot komponentów"));
    assert.ok(screen.getByText("Główny model"));
    assert.equal(screen.queryByText("component snapshot"), null);
  });

  it("prefers daemon target model over stale multi_runtime snapshot model", () => {
    renderControl(
      makeState({
        status: makeStatus({ target_model: "google/gemma-4-E2B-it" }),
      }),
      "voice",
      {
        runtime_id: "multi_runtime",
        provider: "multi_runtime",
        model_name: "gemma2:2b",
        runtime_capabilities: {
          compatibility_profile: "multi_runtime_native",
          probe_status: "verified",
        },
        voice_pipeline: {
          profile: "multi_runtime_native",
          tts: "piper",
        },
      },
    );
    assert.ok(screen.getByText("multi_runtime / google/gemma-4-E2B-it"));
    assert.equal(screen.queryByText("multi_runtime / gemma2:2b"), null);
  });

  it("image handling block is no longer inside Gemma4RuntimeControl (extracted to ImageProbeCard)", async () => {
    renderControl(makeState());
    // Wait for runtime-profile-inline to confirm the panel is fully rendered
    await screen.findByTestId("runtime-profile-inline");
    // ImageProbeSection has been extracted to ImageProbeCard — must NOT appear inside the panel
    assert.equal(
      screen.queryByText(/Obsługa obrazu|Image input|Bildeingabe/i),
      null,
      "ImageProbeSection must not be rendered inside Gemma4RuntimeControl",
    );
  });

  it("shows CPU / no VRAM when backend=cpu", () => {
    renderControl(makeState());
    assert.ok(document.body.textContent?.includes("CPU"));
  });

  it("shows VRAM bar when backend=cuda", () => {
    renderControl(makeState({
      status: makeStatus({
        vram: {
          backend: "cuda",
          allocated_mb: 4096,
          reserved_mb: 5000,
          total_mb: 8192,
          free_mb: 4096,
        },
      }),
    }));
    const bar = screen.getByTestId("vram-bar");
    assert.ok(bar);
    assert.match(bar.style.width, /\d+%/);
  });
});

describe("Gemma4RuntimeControl — pending reload state", () => {
  it("shows reload banner when pending_reload=true", () => {
    renderControl(makeState({
      status: makeStatus({
        pending_reload: true,
        reload_reason: "cache_implementation changed",
      }),
    }));
    const banner = screen.getByTestId("reload-banner");
    assert.ok(banner);
    assert.ok(banner.textContent?.includes("cache_implementation"));
  });

  it("auto-triggers daemon reload after profile update requiring soft_reload", async () => {
    let reloadCalled = false;
    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/v1/runtime/multi-runtime/profile") && method === "POST") {
        return new Response(
          JSON.stringify({
            accepted: { precision: "int4", quantization_backend: "bitsandbytes", device_target: "cuda" },
            rejected: [],
            required_apply_mode: "soft_reload",
            applied: false,
            message: "staged",
          }),
          { status: 200 },
        );
      }
      if (url.includes("/v1/daemon/reload") && method === "POST") {
        reloadCalled = true;
        return new Response(JSON.stringify({ reason: "manual_reload" }), { status: 200 });
      }
      if (url.includes("/v1/daemon/status")) {
        return new Response(
          JSON.stringify({
            ...makeStatus(),
            pending_reload: false,
            active_runtime_config: {
              ...makeStatus().params,
              precision: "int4",
              quantization_backend: "bitsandbytes",
              device_target: "cuda",
            },
            staged_runtime_config: {
              ...makeStatus().params,
              precision: "int4",
              quantization_backend: "bitsandbytes",
              device_target: "cuda",
            },
          }),
          { status: 200 },
        );
      }
      if (url.includes("/api/v1/runtime/multi-runtime/profile") && method === "GET") {
        return new Response(
          JSON.stringify({
            runtime_id: "multi_runtime",
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
            apply_matrix: makeProfileMatrix(),
            supported_options: makeSupportedOptions(),
            daemon_reachable: true,
          }),
          { status: 200 },
        );
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    };
    renderControl(makeState());
    const applyQuant = await screen.findByRole("button", {
      name: /zastosuj kwantyzację|apply quantization/i,
    });
    await act(async () => {
      fireEvent.click(applyQuant);
    });
    await new Promise((resolve) => setTimeout(resolve, 60));
    assert.equal(reloadCalled, true);
  });
});

describe("Gemma4RuntimeControl — assistant drafter on/off", () => {
  it("shows assistant model name when accordion is expanded", () => {
    renderControl(makeState({
      status: makeStatus({
        assistant_model: "google/gemma-4-E2B-it-assistant",
        mode: "target_with_assistant",
        assistant_loaded: true,
      }),
    }));
    // DrafterBox is behind accordion — expand it first
    fireEvent.click(screen.getByTestId("drafter-accordion-toggle"));
    assert.ok(screen.getByText("google/gemma-4-E2B-it-assistant"));
  });

  it("shows drafter active badge when assistant attached", () => {
    renderControl(makeState({
      status: makeStatus({
        assistant_model: "google/gemma-4-E2B-it-assistant",
        mode: "target_with_assistant",
        assistant_loaded: true,
      }),
    }));
    // accordion toggle label already contains "drafter" text even when collapsed
    assert.ok(
      document.body.textContent?.includes("drafter") ||
      document.body.textContent?.includes("aktywny") ||
      document.body.textContent?.includes("Drafter"),
    );
  });

  it("DrafterBox is collapsed by default — placeholder hidden until expanded", () => {
    renderControl(makeState({ status: makeStatus({ assistant_model: null }) }));
    // "Brak"/"None" is inside DrafterBox — must not be visible before expanding
    const hidden = !(
      document.body.textContent?.includes("Brak") ||
      document.body.textContent?.includes("None")
    );
    assert.ok(hidden, "DrafterBox content should be hidden behind accordion when collapsed");
  });

  it("shows assistant preset selector when accordion is expanded", () => {
    renderControl(
      makeState({ status: makeStatus({ assistant_model: null }) }),
      "voice",
      null,
      ["google/gemma-4-E2B-it-assistant"],
    );
    // Expand accordion first
    fireEvent.click(screen.getByTestId("drafter-accordion-toggle"));
    // Then click "Attach drafter" to reveal the preset select menu
    const attachButton = screen.getByRole("button", { name: /attach|podepnij/i });
    fireEvent.click(attachButton);
    assert.ok(screen.getByText("google/gemma-4-E2B-it-assistant"));
  });
});

describe("Gemma4RuntimeControl — disabled state while action pending", () => {
  it("Apply button has disabled attribute when actionPending=config", () => {
    renderControl(makeState({ actionPending: "config" }));
    const btn = screen.getByTestId("apply-button") as HTMLButtonElement;
    assert.ok(btn.disabled);
  });

  it("Reload button has disabled attribute when actionPending=reload", () => {
    renderControl(makeState({ actionPending: "reload" }));
    const btn = screen.getByTestId("reload-button") as HTMLButtonElement;
    assert.ok(btn.disabled);
  });
});

describe("Gemma4RuntimeControl — cockpit variant", () => {
  it("renders without crashing in cockpit variant", () => {
    const { container } = renderControl(makeState(), "cockpit");
    assert.ok(container.firstChild);
  });

  it("cockpit variant renders target model", () => {
    renderControl(makeState(), "cockpit");
    assert.ok(screen.getByText("google/gemma-4-E2B-it"));
  });
});

describe("Gemma4RuntimeControl — thinking toggle", () => {
  it("reflects enable_thinking=true in switch state", () => {
    renderControl(makeState({
      status: makeStatus({
        params: {
          max_new_tokens: 128,
          enable_thinking: true,
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
      }),
    }));
    const sw = document.querySelector("[role='switch']") as HTMLButtonElement | null;
    assert.ok(sw);
    assert.equal(sw.getAttribute("aria-checked"), "true");
  });
});

describe("Gemma4RuntimeControl — active model detection", () => {
  it("shows target model from status", () => {
    renderControl(makeState({
      status: makeStatus({ target_model: "google/gemma-4-E4B-it" }),
    }));
    assert.ok(screen.getByText("google/gemma-4-E4B-it"));
  });
});
