import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  DevDiagnosticsDrawer,
  DevDiagnosticsDrawerContent,
} from "../components/voice/dev-diagnostics-drawer";

afterEach(() => cleanup());

const originalFetch = globalThis.fetch;
let clipboardText = "";

function makeAudioStatus() {
  return {
    enabled: true,
    connected_clients: 4,
    active_recordings: 1,
    vad_threshold: 0.5,
    whisper_model_size: "medium",
    stt_ready: true,
    tts_ready: true,
    tts_fallback: false,
    dependencies: { ffmpeg: true, faster_whisper: true, piper: true },
    message: "Kanał gotowy",
    latest_voice_session: {
      session_id: "session-123",
      duration_sec: 1.25,
      sample_rate: 24000,
      input_format: "wav",
      voice_mode: "standard",
      gain_applied: 1,
      peak_before_normalization: 0.4,
      rms_after_normalization: 0.2,
      timings_ms: { stt: 123, llm: 456, tts: 78 },
      download_url: "/tmp/session.wav",
      transcription: "Co to jest kwadrat?",
      runtime: {
        stt_model: "medium",
        stt_device: "cuda",
        llm_service_id: "gemma4_audio",
        llm_model: "google/gemma-4-E2B-it",
        tts_sample_rate: 24000,
      },
      pipeline_id: "gemma4_audio_piper",
      audio_runtime_provider: "gemma4_audio",
      audio_runtime_model: "google/gemma-4-E2B-it",
      audio_input_status: "verified",
      decoder_source: "gemma4_audio",
      fallback_reason: null,
      native_audio_ms: 1200,
      runtime_log_path: "/var/log/venom/gemma4_audio.log",
    },
    runtime_snapshot: {
      runtime_id: "gemma4_audio@http://localhost:8014/v1",
      provider: "gemma4_audio",
      model_name: "google/gemma-4-E2B-it",
      endpoint: "http://localhost:8014/v1",
      config_hash: "cfg123",
      runtime_capabilities: {
        compatibility_profile: "gemma4_audio_native",
        probe_status: "verified",
        probes: {
          health: { status: "verified" },
        },
      },
      voice_pipeline: {
        profile: "gemma4_audio_native",
        stt: "native_audio",
        reasoning: "native_audio_model",
        tools: "disabled",
        vision: "disabled",
        tts: "piper",
        notes: ["ready"],
      },
    },
  } as const;
}

beforeEach(() => {
  clipboardText = "";
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: async (text: string) => {
        clipboardText = text;
      },
    },
  });
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/v1/daemon/status")) {
      return new Response(JSON.stringify(makeAudioStatus().runtime_snapshot), { status: 200 });
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("DevDiagnosticsDrawer", () => {
  it("renders diagnostics summary and copies runtime JSON", async () => {
    const audioStatus = makeAudioStatus();
    let closed = 0;

    render(
      <DevDiagnosticsDrawerContent
        onClose={() => {
          closed += 1;
        }}
        audioStatus={audioStatus as never}
        lastAudioSignal="ws:open"
        audioChunkCount={2}
        statusMessage="Kanał gotowy"
        renderDiagnosticMode="debug"
      />,
    );

    assert.ok(screen.getByText("WS: online"));
    assert.ok(screen.getByText("signal: ws:open"));
    assert.ok(screen.getByText("chunks: 2"));
    assert.ok(screen.getByText("render: debug"));
    assert.ok(screen.getByText("provider: gemma4_audio"));
    assert.ok(screen.getByText("session: session-123"));
    assert.ok(screen.getAllByText("Kanał gotowy").length >= 2);
    assert.ok(screen.getByText("Kopiuj runtime JSON"));
    assert.ok(screen.getByText("Kopiuj sesję JSON"));

    await act(async () => {
      fireEvent.click(screen.getByText("Kopiuj runtime JSON"));
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Kopiuj sesję JSON"));
    });
    assert.match(clipboardText, /"session_id": "session-123"/);

    fireEvent.click(screen.getByText("Zamknij"));
    assert.equal(closed, 1);
  });

  it("opens the drawer wrapper and renders the diagnostics content", () => {
    const audioStatus = makeAudioStatus();
    render(
      <DevDiagnosticsDrawer
        isOpen
        onClose={() => undefined}
        audioStatus={audioStatus as never}
        lastAudioSignal="ws:open"
        audioChunkCount={2}
        statusMessage="Kanał gotowy"
        renderDiagnosticMode="debug"
      />,
    );

    assert.ok(screen.getByText("⚙ Diagnostics"));
    assert.ok(screen.getByText("Diagnostyka voice runtime i request path."));
    assert.ok(screen.getByText("WS: online"));
    assert.ok(screen.getByText("Kopiuj runtime JSON"));
  });

  it("returns null when closed", () => {
    const { container } = render(
      <DevDiagnosticsDrawer
        isOpen={false}
        onClose={() => {
          throw new Error("should not close");
        }}
        audioStatus={null}
        lastAudioSignal="none"
        audioChunkCount={0}
        statusMessage={null}
      />,
    );

    assert.equal(container.firstChild, null);
  });
});
