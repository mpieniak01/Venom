import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { TtsRuntimeEngineOption, TtsRuntimeState, TtsVoiceOption } from "../lib/types";

function makePiperRuntimeState(
  overrides: Partial<TtsRuntimeState> = {},
): TtsRuntimeState {
  return {
    tts_engine: "piper_local",
    available_engines: [
      { engine_id: "piper_local", label: "Piper Local", status: "ready", available: true },
      { engine_id: "fish_speech", label: "Fish Speech", status: "disabled", available: false },
    ],
    engine_status: { piper_local: "ready", fish_speech: "disabled" },
    current_option_id: "/data/models/piper/pl_voice.onnx",
    options: [
      { id: "pl_voice.onnx", label: "pl_voice", path: "/data/models/piper/pl_voice.onnx" },
    ],
    fallback_enabled: true,
    fallback_target: "piper_local",
    ...overrides,
  };
}

function makeFishSpeechRuntimeState(
  overrides: Partial<TtsRuntimeState> = {},
): TtsRuntimeState {
  return {
    tts_engine: "fish_speech",
    available_engines: [
      { engine_id: "piper_local", label: "Piper Local", status: "ready", available: true },
      { engine_id: "fish_speech", label: "Fish Speech", status: "ready", available: true },
    ],
    engine_status: { piper_local: "ready", fish_speech: "ready" },
    current_option_id: "fishaudio/fish-speech-1.5",
    options: [
      {
        id: "fishaudio/fish-speech-1.5",
        label: "fish-speech-1.5",
        path: "fishaudio/fish-speech-1.5",
      },
    ],
    fallback_enabled: true,
    fallback_target: "piper_local",
    ...overrides,
  };
}

describe("TtsRuntimeState type contract", () => {
  it("piper_local runtime has correct engine_id", () => {
    const state = makePiperRuntimeState();
    assert.equal(state.tts_engine, "piper_local");
  });

  it("fish_speech runtime has correct engine_id", () => {
    const state = makeFishSpeechRuntimeState();
    assert.equal(state.tts_engine, "fish_speech");
  });

  it("available_engines always contains both piper_local and fish_speech", () => {
    for (const state of [makePiperRuntimeState(), makeFishSpeechRuntimeState()]) {
      const ids = state.available_engines.map((e: TtsRuntimeEngineOption) => e.engine_id);
      assert.ok(ids.includes("piper_local"), "piper_local missing");
      assert.ok(ids.includes("fish_speech"), "fish_speech missing");
    }
  });

  it("engine_status keys match available_engines engine_ids", () => {
    const state = makePiperRuntimeState();
    for (const eng of state.available_engines) {
      assert.ok(
        eng.engine_id in state.engine_status,
        `engine_status missing key ${eng.engine_id}`,
      );
    }
  });

  it("piper_local options contain path field", () => {
    const state = makePiperRuntimeState();
    assert.equal(state.tts_engine, "piper_local");
    for (const opt of state.options as TtsVoiceOption[]) {
      assert.ok(opt.path, "option.path is empty");
      assert.ok(opt.label, "option.label is empty");
    }
  });

  it("fish_speech when disabled has available=false in engines list", () => {
    const state = makePiperRuntimeState();
    const fishEng = state.available_engines.find(
      (e: TtsRuntimeEngineOption) => e.engine_id === "fish_speech",
    );
    assert.ok(fishEng);
    assert.equal(fishEng.status, "disabled");
    assert.equal(fishEng.available, false);
  });

  it("fallback_enabled is true and fallback_target is piper_local", () => {
    for (const state of [makePiperRuntimeState(), makeFishSpeechRuntimeState()]) {
      assert.equal(state.fallback_enabled, true);
      assert.equal(state.fallback_target, "piper_local");
    }
  });
});

describe("TtsRuntimeState engine switching contract", () => {
  it("switching engine changes tts_engine field", () => {
    const before = makePiperRuntimeState();
    const after = makeFishSpeechRuntimeState();
    assert.notEqual(before.tts_engine, after.tts_engine);
    assert.equal(after.tts_engine, "fish_speech");
  });

  it("fish_speech runtime options use model_id as path", () => {
    const state = makeFishSpeechRuntimeState();
    assert.equal(state.tts_engine, "fish_speech");
    const opt = state.options[0];
    assert.ok(opt.path.includes("fish-speech"), "path should reference fish-speech model");
  });

  it("current_option_id matches active option path for piper", () => {
    const state = makePiperRuntimeState();
    const found = state.options.find(
      (o: TtsVoiceOption) => o.path === state.current_option_id,
    );
    assert.ok(found, "current_option_id not found in options");
  });

  it("fish_speech offline state has available=false", () => {
    const state = makePiperRuntimeState({
      available_engines: [
        { engine_id: "piper_local", label: "Piper Local", status: "ready", available: true },
        { engine_id: "fish_speech", label: "Fish Speech", status: "offline", available: false },
      ],
      engine_status: { piper_local: "ready", fish_speech: "offline" },
    });
    const fishEng = state.available_engines.find(
      (e: TtsRuntimeEngineOption) => e.engine_id === "fish_speech",
    );
    assert.ok(fishEng);
    assert.equal(fishEng.available, false);
    assert.equal(fishEng.status, "offline");
  });
});

describe("TtsRuntimeState AudioStatus integration contract", () => {
  type AudioStatusTtsFields = {
    tts_engine?: string | null;
    tts_backend?: string | null;
    tts_ready?: boolean;
    tts_fallback?: boolean | null;
  };

  it("piper_local active state has correct tts fields", () => {
    const status: AudioStatusTtsFields = {
      tts_engine: "piper_local",
      tts_backend: "piper",
      tts_ready: true,
      tts_fallback: false,
    };
    assert.equal(status.tts_engine, "piper_local");
    assert.equal(status.tts_backend, "piper");
    assert.equal(status.tts_ready, true);
  });

  it("fish_speech active state has correct tts fields", () => {
    const status: AudioStatusTtsFields = {
      tts_engine: "fish_speech",
      tts_backend: "fish_speech",
      tts_ready: true,
      tts_fallback: false,
    };
    assert.equal(status.tts_engine, "fish_speech");
    assert.equal(status.tts_backend, "fish_speech");
  });

  it("fish_speech fallback state shows tts_fallback=true", () => {
    const status: AudioStatusTtsFields = {
      tts_engine: "fish_speech",
      tts_backend: "piper",
      tts_ready: true,
      tts_fallback: true,
    };
    assert.equal(status.tts_fallback, true);
    assert.equal(status.tts_backend, "piper");
  });
});
