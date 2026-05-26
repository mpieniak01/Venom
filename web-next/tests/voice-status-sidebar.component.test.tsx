import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ToastProvider } from "../components/ui/toast";
import { VoiceStatusSidebar } from "../components/voice/voice-status-sidebar";

afterEach(() => cleanup());
const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const voiceStatus = {
  enabled: true,
  connected_clients: 1,
  active_recordings: 0,
  stt_ready: true,
  whisper_model_size: "medium",
  tts_ready: true,
  tts_backend: "piper",
  tts_fallback: false,
  dependencies: { ffmpeg: true, faster_whisper: true, piper: true },
  runtime_snapshot: {
    runtime_id: "ollama@http://localhost:11434/v1",
    provider: "ollama",
    model_name: "gemma2:2b",
    endpoint: "http://localhost:11434/v1",
    config_hash: "cfg123",
    runtime_capabilities: {
      compatibility_profile: "legacy_text_only",
      probe_status: "verified",
    },
    voice_pipeline: {
      profile: "legacy_text_only",
      stt: "faster_whisper",
      reasoning: "prompt_fallback",
      tts: "piper",
    },
  },
} as const;

const gemma4VoiceStatus = {
  ...voiceStatus,
  latest_voice_session: {
    session_id: "session-123",
    pipeline_id: "multi_runtime_piper",
    voice_mode: "standard",
    voice_pipeline_mode: "native_multi_runtime",
    audio_runtime_provider: "multi_runtime",
    audio_runtime_model: "google/gemma-4-E2B-it",
    reasoning_summary_enabled: true,
    reasoning_summary_status: "summary",
    reasoning_summary: "pipeline=multi_runtime_piper | mode=standard",
    raw_thinking_available: true,
    emotion_detection_enabled: true,
    emotion_response_style_enabled: true,
    emotion_source: "transcript",
    emotion_label: "curious",
    emotion_confidence: 0.82,
    transcription: "Co to jest kwadrat?",
    response_text: "Kwadrat ma cztery boki.",
    native_audio_ms: 1200,
    execution_trace_annotations: [
      { label: "Image preprocessor", status: "no-op", note: "audio-only voice session" },
    ],
  },
  runtime_snapshot: {
    ...voiceStatus.runtime_snapshot,
    runtime_id: "multi_runtime://localhost:8014/v1",
    provider: "multi_runtime",
    model_name: "google/gemma-4-E2B-it",
    endpoint: "http://localhost:8014/v1",
    runtime_capabilities: {
      compatibility_profile: "multi_runtime_native",
      probe_status: "verified",
    },
    voice_pipeline: {
      profile: "multi_runtime_native",
      stt: "native_audio",
      reasoning: "native_audio_model",
      reasoning_summary: "summary",
      emotion: "enabled",
      tts: "piper",
    },
  },
} as const;

const gemma4RuntimeProfile = {
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
} as const;

const runtimeSelectionPayloads = {
  models: {
    success: true,
    models: [],
    count: 0,
    providers: {
      multi_runtime: [
        {
          name: "google/gemma-4-E2B-it",
          provider: "multi_runtime",
          source: "local-runtime",
          installed: true,
          active: true,
        },
      ],
    },
    active: {
      provider: "multi_runtime",
      model: "google/gemma-4-E2B-it",
      endpoint: "http://localhost:8014/v1",
      status: "ready",
    },
  },
  runtimeOptions: {
    status: "success",
    active: {
      runtime_id: "multi_runtime",
      active_server: "multi_runtime",
      active_model: "google/gemma-4-E2B-it",
      active_endpoint: "http://localhost:8014/v1",
      config_hash: "cfg123",
      source_type: "local-runtime",
    },
    runtimes: [
      {
        runtime_id: "multi_runtime",
        source_type: "local-runtime",
        configured: true,
        available: true,
        status: "ready",
        active: true,
        models: [
          {
            name: "google/gemma-4-E2B-it",
            provider: "multi_runtime",
            source_type: "local-runtime",
            chat_compatible: true,
          },
        ],
      },
    ],
    selector_flow: ["server", "model"],
  },
  activeServer: {
    status: "success",
    active_server: "multi_runtime",
    active_endpoint: "http://localhost:8014/v1",
    active_model: "google/gemma-4-E2B-it",
    config_hash: "cfg123",
    runtime_id: "multi_runtime",
    source_type: "local-runtime",
  },
  modelOperations: {
    success: true,
    operations: [],
    count: 0,
  },
} as const;

const makeDaemonStatusPayload = (overrides: Record<string, unknown> = {}) => ({
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
  active_runtime_config: {
    precision: "float16",
    quantization_backend: null,
    device_target: "cuda",
  },
  staged_runtime_config: {
    precision: "float16",
    quantization_backend: null,
    device_target: "cuda",
  },
  effective_precision_mode: "explicit_float16",
  effective_config_reason: null,
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
  ...overrides,
});

describe("VoiceStatusSidebar", () => {
  const renderAndFlush = async (ui: Parameters<typeof render>[0]) => {
    await act(async () => {
      render(ui);
      await Promise.resolve();
    });
  };

  it("shows active runtime details and does not surface Gemma 4 controls for ollama", async () => {
    window.history.pushState({}, "", "/voice");
    await renderAndFlush(
      <ToastProvider>
        <VoiceStatusSidebar status={voiceStatus as never} isDevMode={false} />
      </ToastProvider>,
    );

    assert.ok(screen.getAllByText(/ollama \/ gemma2:2b/i).length >= 1);
    assert.ok(screen.getAllByText("Runtime systemowy voice").length >= 1);
    assert.ok(screen.getAllByText("piper").length >= 2);
    assert.ok(screen.getAllByText("faster_whisper").length >= 2);
    assert.equal(screen.queryByText(/Gemma 4 Runtime/i), null);
  });

  it("surfaces Gemma 4 runtime controls for multi_runtime without dev gate", async () => {
    window.history.pushState({}, "", "/voice");
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/daemon/status")) {
        return new Response(JSON.stringify(makeDaemonStatusPayload()), { status: 200 });
      }
      if (url.includes("/api/v1/runtime/multi-runtime/profile")) {
        return new Response(JSON.stringify(gemma4RuntimeProfile), { status: 200 });
      }
      if (url.includes("/api/v1/models/operations")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.modelOperations), {
          status: 200,
        });
      }
      if (url.endsWith("/api/v1/models")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.models), { status: 200 });
      }
      if (url.endsWith("/api/v1/system/llm-runtime/options")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.runtimeOptions), {
          status: 200,
        });
      }
      if (url.endsWith("/api/v1/system/llm-servers/active")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.activeServer), {
          status: 200,
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    };
    await renderAndFlush(
      <ToastProvider>
        <VoiceStatusSidebar status={gemma4VoiceStatus as never} isDevMode={false} />
      </ToastProvider>,
    );

    assert.ok((await screen.findAllByText("Gemma 4 Runtime")).length >= 1);
    assert.ok(await screen.findByText("Runtime odpowiedzi"));
    assert.ok(await screen.findByTestId("runtime-profile-inline"));
    assert.equal(screen.queryByTestId("multi-runtime-profile-panel"), null);
    assert.ok(await screen.findByText(/session-123/i));
    assert.ok(screen.getByText(/curious/i));
    assert.ok(screen.getByText("Tryb toru"));
    assert.ok(screen.getByText("Native audio"));
    assert.ok(screen.getByText("Semantyka śladu"));
    assert.ok(screen.getByText(/Image preprocessor:no-op/i));
  });

  it("shows model-not-loaded transition note in voice sidebar runtime block", async () => {
    window.history.pushState({}, "", "/voice");
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/daemon/status")) {
        return new Response(
          JSON.stringify(
            makeDaemonStatusPayload({
              target_loaded: false,
              effective_precision_mode: "unknown",
              effective_config_reason: "model_not_loaded",
            }),
          ),
          { status: 200 },
        );
      }
      if (url.includes("/api/v1/runtime/multi-runtime/profile")) {
        return new Response(JSON.stringify(gemma4RuntimeProfile), { status: 200 });
      }
      if (url.includes("/api/v1/models/operations")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.modelOperations), {
          status: 200,
        });
      }
      if (url.endsWith("/api/v1/models")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.models), { status: 200 });
      }
      if (url.endsWith("/api/v1/system/llm-runtime/options")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.runtimeOptions), {
          status: 200,
        });
      }
      if (url.endsWith("/api/v1/system/llm-servers/active")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.activeServer), {
          status: 200,
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    };

    await renderAndFlush(
      <ToastProvider>
        <VoiceStatusSidebar status={gemma4VoiceStatus as never} isDevMode={false} />
      </ToastProvider>,
    );

    assert.ok(
      document.body.textContent?.includes("Model niezaładowany")
      || document.body.textContent?.includes("Model not loaded"),
    );
  });

  it("hides model-not-loaded transition note when runtime reports loaded target", async () => {
    window.history.pushState({}, "", "/voice");
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/daemon/status")) {
        return new Response(
          JSON.stringify(
            makeDaemonStatusPayload({
              target_loaded: true,
              effective_precision_mode: "explicit_float16",
              effective_config_reason: null,
            }),
          ),
          { status: 200 },
        );
      }
      if (url.includes("/api/v1/runtime/multi-runtime/profile")) {
        return new Response(JSON.stringify(gemma4RuntimeProfile), { status: 200 });
      }
      if (url.includes("/api/v1/models/operations")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.modelOperations), {
          status: 200,
        });
      }
      if (url.endsWith("/api/v1/models")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.models), { status: 200 });
      }
      if (url.endsWith("/api/v1/system/llm-runtime/options")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.runtimeOptions), {
          status: 200,
        });
      }
      if (url.endsWith("/api/v1/system/llm-servers/active")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.activeServer), {
          status: 200,
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    };

    await renderAndFlush(
      <ToastProvider>
        <VoiceStatusSidebar status={gemma4VoiceStatus as never} isDevMode={false} />
      </ToastProvider>,
    );

    assert.equal(
      Boolean(
        document.body.textContent?.includes("Model niezaładowany")
        || document.body.textContent?.includes("Model not loaded"),
      ),
      false,
    );
  });

  it("normalizes generic backend apology in latest session response", async () => {
    window.history.pushState({}, "", "/voice");
    const statusWithGenericError = {
      ...gemma4VoiceStatus,
      latest_voice_session: {
        ...gemma4VoiceStatus.latest_voice_session,
        response_text: "Przepraszam, wystąpił błąd. Spróbuj ponownie.",
      },
    };
    await renderAndFlush(
      <ToastProvider>
        <VoiceStatusSidebar status={statusWithGenericError as never} isDevMode={false} />
      </ToastProvider>,
    );

    assert.ok(screen.getByText(/Błąd kanału audio|Audio channel error|Fehler im Audiokanal/i));
    assert.equal(screen.queryByText("Przepraszam, wystąpił błąd. Spróbuj ponownie."), null);
  });

  it("keeps runtime panel stable when activation request fails", async () => {
    window.history.pushState({}, "", "/voice");
    const runtimeOptionsOnlyMulti = {
      ...runtimeSelectionPayloads.runtimeOptions,
      runtimes: runtimeSelectionPayloads.runtimeOptions.runtimes.filter(
        (runtime) => runtime.runtime_id === "multi_runtime",
      ),
    };
    const activeServerOllama = {
      ...runtimeSelectionPayloads.activeServer,
      active_server: "ollama",
      active_model: "qwen2.5-coder:3b",
    };
    let postAttempts = 0;
    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/models")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.models), { status: 200 });
      }
      if (url.endsWith("/api/v1/system/llm-runtime/options")) {
        return new Response(JSON.stringify(runtimeOptionsOnlyMulti), {
          status: 200,
        });
      }
      if (url.endsWith("/api/v1/system/llm-servers/active")) {
        if (init?.method === "POST") {
          postAttempts += 1;
          return new Response(
            JSON.stringify({
              detail: "multi_runtime health check failed",
            }),
            { status: 500 },
          );
        }
        return new Response(JSON.stringify(activeServerOllama), {
          status: 200,
        });
      }
      if (url.includes("/api/v1/models/operations")) {
        return new Response(JSON.stringify(runtimeSelectionPayloads.modelOperations), {
          status: 200,
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    };

    await renderAndFlush(
      <ToastProvider>
        <VoiceStatusSidebar status={gemma4VoiceStatus as never} isDevMode={false} />
      </ToastProvider>,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Zastosuj runtime" }));
    });
    assert.ok(await screen.findByText("Runtime systemowy voice"));
    assert.ok(postAttempts <= 1);
  });

  it("keeps the active and response runtime labels distinct", async () => {
    window.history.pushState({}, "", "/voice");
    await renderAndFlush(
      <ToastProvider>
        <VoiceStatusSidebar status={gemma4VoiceStatus as never} isDevMode={false} />
      </ToastProvider>,
    );

    assert.ok(screen.getAllByText("Runtime systemowy voice").length >= 1);
    assert.ok(screen.getByText("Wybrany runtime"));
    assert.ok(screen.getByText("Runtime odpowiedzi"));
  });
});
