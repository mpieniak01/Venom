import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { LlmRuntimeTargetOption } from "../lib/types";

const GEMMA4_AUDIO_TARGET_MODELS = ["google/gemma-4-E2B-it"];
const GEMMA4_AUDIO_ASSISTANT_MODELS = ["google/gemma-4-E2B-it-assistant"];

function makeGemma4AudioRuntime(
  overrides: Partial<LlmRuntimeTargetOption> = {},
): LlmRuntimeTargetOption {
  return {
    runtime_id: "gemma4_audio",
    source_type: "local-runtime",
    configured: true,
    available: true,
    status: "online",
    active: false,
    models: GEMMA4_AUDIO_TARGET_MODELS.map((id) => ({
      id,
      name: id,
      provider: "gemma4_audio",
      runtime_id: "gemma4_audio",
      source_type: "local-runtime",
      active: false,
      capabilities: ["text", "audio", "voice"],
      chat_compatible: true,
    })),
    supports_text_input: true,
    supports_audio_input: true,
    supports_text_output: true,
    supports_image_input: true,
    supported_models: GEMMA4_AUDIO_TARGET_MODELS,
    assistant_models: GEMMA4_AUDIO_ASSISTANT_MODELS,
    log_path: "logs/gemma4_audio_service.log",
    pid_path: ".venom_runtime/gemma4_audio.pid",
    ...overrides,
  };
}

describe("gemma4_audio runtime type contract", () => {
  it("runtime appears as local-runtime with correct runtime_id", () => {
    const rt = makeGemma4AudioRuntime();
    assert.equal(rt.runtime_id, "gemma4_audio");
    assert.equal(rt.source_type, "local-runtime");
  });

  it("exposes the cached target model list", () => {
    const rt = makeGemma4AudioRuntime();
    assert.equal(rt.models.length, 1);
    const ids = rt.models.map((m) => m.id);
    assert.ok(ids.includes("google/gemma-4-E2B-it"));
  });

  it("model list filters to chat_compatible models only", () => {
    const rt = makeGemma4AudioRuntime();
    const chatModels = rt.models.filter((m) => m.chat_compatible !== false);
    assert.equal(chatModels.length, 1);
  });

  it("each model carries text+audio+voice capability badges", () => {
    const rt = makeGemma4AudioRuntime();
    for (const model of rt.models) {
      const caps = model.capabilities ?? [];
      assert.ok(caps.includes("text"), `text missing for ${model.id}`);
      assert.ok(caps.includes("audio"), `audio missing for ${model.id}`);
      assert.ok(caps.includes("voice"), `voice missing for ${model.id}`);
    }
  });

  it("supports_text_input and supports_audio_input are true", () => {
    const rt = makeGemma4AudioRuntime();
    assert.equal(rt.supports_text_input, true);
    assert.equal(rt.supports_audio_input, true);
    assert.equal(rt.supports_text_output, true);
  });

  it("supports_image_input is true", () => {
    const rt = makeGemma4AudioRuntime();
    assert.equal(rt.supports_image_input, true);
  });

  it("log_path and pid_path are present", () => {
    const rt = makeGemma4AudioRuntime();
    assert.ok(rt.log_path);
    assert.ok(rt.pid_path);
  });

  it("active model flag is correct when E2B-it is active", () => {
    const rt = makeGemma4AudioRuntime({
      active: true,
      models: GEMMA4_AUDIO_TARGET_MODELS.map((id) => ({
        id,
        name: id,
        provider: "gemma4_audio",
        runtime_id: "gemma4_audio",
        source_type: "local-runtime" as const,
        active: id === "google/gemma-4-E2B-it",
        capabilities: ["text", "audio", "voice"],
        chat_compatible: true,
      })),
    });
    const activeModels = rt.models.filter((m) => m.active);
    assert.equal(activeModels.length, 1);
    assert.equal(activeModels[0].id, "google/gemma-4-E2B-it");
  });

  it("runtime status maps to expected states", () => {
    for (const status of ["disabled", "offline", "starting", "ready", "error"]) {
      const rt = makeGemma4AudioRuntime({ status });
      assert.equal(rt.status, status);
    }
  });

  it("supported_models list contains the cached target model and assistant_models exposes drafter presets", () => {
    const rt = makeGemma4AudioRuntime();
    assert.ok(rt.supported_models?.includes("google/gemma-4-E2B-it"));
    assert.equal(rt.supported_models?.length, 1);
    assert.ok(rt.assistant_models?.includes("google/gemma-4-E2B-it-assistant"));
  });
});

describe("gemma4_audio voice diagnostics fields", () => {
  type LatestVoiceSession = {
    session_id: string;
    pipeline_id?: string | null;
    audio_runtime_provider?: string | null;
    audio_runtime_model?: string | null;
    audio_input_status?: string | null;
    decoder_source?: string | null;
    fallback_reason?: string | null;
    native_audio_ms?: number | null;
    runtime_log_path?: string | null;
  };

  it("native pipeline session has gemma4_audio_piper pipeline_id", () => {
    const session: LatestVoiceSession = {
      session_id: "sess-1",
      pipeline_id: "gemma4_audio_piper",
      audio_runtime_provider: "gemma4_audio",
      audio_runtime_model: "google/gemma-4-E2B-it",
      audio_input_status: "verified",
      decoder_source: "gemma4_audio",
      fallback_reason: "",
      native_audio_ms: 1200,
    };
    assert.equal(session.pipeline_id, "gemma4_audio_piper");
    assert.equal(session.audio_runtime_provider, "gemma4_audio");
    assert.equal(session.audio_input_status, "verified");
    assert.equal(session.decoder_source, "gemma4_audio");
  });

  it("fallback session has whisper_llm_piper pipeline_id and fallback_reason", () => {
    const session: LatestVoiceSession = {
      session_id: "sess-2",
      pipeline_id: "whisper_llm_piper",
      audio_runtime_provider: "gemma4_audio",
      audio_input_status: "fallback",
      decoder_source: "faster_whisper",
      fallback_reason: "gemma4_audio health check failed",
    };
    assert.equal(session.pipeline_id, "whisper_llm_piper");
    assert.ok(session.fallback_reason);
    assert.equal(session.audio_input_status, "fallback");
    assert.equal(session.decoder_source, "faster_whisper");
  });

  it("older whisper session has no audio_runtime_provider", () => {
    const session: LatestVoiceSession = {
      session_id: "sess-3",
      pipeline_id: "whisper_llm_piper",
    };
    assert.equal(session.audio_runtime_provider, undefined);
  });
});
