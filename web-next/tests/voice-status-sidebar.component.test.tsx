import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
import { VoiceStatusSidebar } from "../components/voice/voice-status-sidebar";

afterEach(() => cleanup());

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

describe("VoiceStatusSidebar", () => {
  it("shows active runtime details and does not surface Gemma 4 controls for ollama", () => {
    render(<VoiceStatusSidebar status={voiceStatus as never} />);

    assert.ok(screen.getByText(/ollama \/ gemma2:2b/i));
    assert.ok(screen.getAllByText("piper").length >= 2);
    assert.ok(screen.getAllByText("faster_whisper").length >= 2);
    assert.equal(screen.queryByText(/Gemma 4 Runtime/i), null);
  });
});
