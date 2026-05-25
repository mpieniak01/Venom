import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
import { TimingStrip } from "../components/voice/voice-command-center";
import {
  buildVoiceTimingEntries,
  inferVoiceSessionTimingMode,
} from "../lib/voice-session-timings";

afterEach(() => cleanup());

const nativeSession = {
  voice_pipeline_mode: "native_multi_runtime",
  pipeline_id: "multi_runtime_piper",
  decoder_source: "multi_runtime",
  native_audio_ms: 4167.5,
};

const whisperSession = {
  voice_pipeline_mode: "whisper_llm_piper",
  pipeline_id: "whisper_llm_piper",
  decoder_source: "faster_whisper",
};

describe("voice-session-timings", () => {
  it("infers native audio and whisper timing modes from session metadata", () => {
    assert.equal(inferVoiceSessionTimingMode(nativeSession), "native_audio");
    assert.equal(inferVoiceSessionTimingMode(whisperSession), "whisper_llm_piper");
    assert.equal(inferVoiceSessionTimingMode(null), "unknown");
  });

  it("builds native audio timing entries without STT and LLM slots", () => {
    const entries = buildVoiceTimingEntries(
      {
        decode_ms: 50,
        stt_ms: 1234,
        llm_ms: 5678,
        tts_ms: 420,
        total_backend_ms: 14040,
      },
      nativeSession,
    );

    assert.deepEqual(
      entries.map((entry) => entry.label),
      ["Decode", "Native audio", "TTS", "Total"],
    );
    assert.equal(entries[1]?.value, 4167.5);
    assert.equal(entries[1]?.accent, true);
  });

  it("builds whisper timing entries with explicit STT and LLM slots", () => {
    const entries = buildVoiceTimingEntries(
      {
        decode_ms: 50,
        stt_ms: 1234,
        llm_ms: 5678,
        tts_ms: 420,
        total_backend_ms: 14040,
      },
      whisperSession,
    );

    assert.deepEqual(
      entries.map((entry) => entry.label),
      ["Decode", "STT", "LLM", "TTS", "Total"],
    );
    assert.equal(entries[1]?.value, 1234);
    assert.equal(entries[2]?.value, 5678);
  });

  it("renders native audio timing strip without STT and LLM labels", () => {
    render(
      <TimingStrip
        timings={{
          decode_ms: 50,
          stt_ms: 1234,
          llm_ms: 5678,
          tts_ms: 420,
          total_backend_ms: 14040,
        }}
        session={nativeSession}
      />,
    );

    assert.ok(screen.getByText("Decode"));
    assert.ok(screen.getByText("Native audio"));
    assert.ok(screen.getByText("TTS"));
    assert.ok(screen.getByText("Total"));
    assert.equal(screen.queryByText("STT"), null);
    assert.equal(screen.queryByText("LLM"), null);
    assert.ok(screen.getByText("4.17s"));
  });

  it("renders whisper timing strip with STT and LLM labels", () => {
    render(
      <TimingStrip
        timings={{
          decode_ms: 50,
          stt_ms: 1234,
          llm_ms: 5678,
          tts_ms: 420,
          total_backend_ms: 14040,
        }}
        session={whisperSession}
      />,
    );

    assert.ok(screen.getByText("Decode"));
    assert.ok(screen.getByText("STT"));
    assert.ok(screen.getByText("LLM"));
    assert.ok(screen.getByText("TTS"));
    assert.ok(screen.getByText("Total"));
    assert.ok(screen.getByText("1.23s"));
    assert.ok(screen.getByText("5.68s"));
  });
});
