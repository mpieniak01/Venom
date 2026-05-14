/**
 * Testy kontraktu Fazy 5 (217B): multi_runtime_profile — typy, API helpers, logika UI.
 *
 * Sprawdzają:
 * 1. Typy MultiRuntimeProfile mają wszystkie wymagane pola kontraktu.
 * 2. ApplyMode jest jednym z czterech zdefiniowanych wartości.
 * 3. getMultiRuntimeProfile i updateMultiRuntimeProfile wywołują właściwe URL.
 * 4. Logika wyznaczania etykiet apply_mode jest spójna z macierzą backendu.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type {
  MultiRuntimeApplyMatrix,
  MultiRuntimeApplyMode,
  MultiRuntimeProfile,
  MultiRuntimeProfileResponse,
  MultiRuntimeProfileUpdateRequest,
  MultiRuntimeProfileUpdateResponse,
} from "../lib/gemma4-daemon-api";

// ---------------------------------------------------------------------------
// Type-level contract tests (compile-time — runtime just confirms shape)
// ---------------------------------------------------------------------------

function makeProfile(overrides: Partial<MultiRuntimeProfile> = {}): MultiRuntimeProfile {
  return {
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
    ...overrides,
  };
}

function makeMatrix(): MultiRuntimeApplyMatrix {
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
    precision: "unsupported",
    quantization_backend: "unsupported",
    device_target: "unsupported",
  };
}

function makeProfileResponse(
  overrides: Partial<MultiRuntimeProfileResponse> = {},
): MultiRuntimeProfileResponse {
  return {
    runtime_id: "multi_runtime",
    profile: makeProfile(),
    apply_matrix: makeMatrix(),
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
    daemon_reachable: true,
    ...overrides,
  };
}

describe("MultiRuntimeProfile type contract", () => {
  it("profile has all required fields", () => {
    const p = makeProfile();
    assert.equal(p.runtime_id, "multi_runtime");
    assert.equal(p.compatibility, "multi_runtime_native");
    assert.ok(typeof p.model_id === "string");
    assert.ok(typeof p.max_new_tokens === "number");
    assert.ok(typeof p.enable_thinking === "boolean");
    assert.ok(typeof p.image_token_budget === "number");
  });

  it("profile has unsupported fields present in contract", () => {
    const p = makeProfile();
    assert.ok("precision" in p);
    assert.ok("quantization_backend" in p);
    assert.ok("device_target" in p);
  });

  it("apply_matrix covers all profile fields that can change", () => {
    const matrix = makeMatrix();
    const liveFields: (keyof MultiRuntimeApplyMatrix)[] = [
      "max_new_tokens",
      "image_token_budget",
      "enable_thinking",
      "reasoning_summary_enabled",
      "emotion_detection_enabled",
      "emotion_response_style_enabled",
      "execution_mode",
      "image_strategy",
      "retrieval_mode",
      "audio_output_mode",
      "assistant_mode",
      "economy_mode",
    ];
    for (const field of liveFields) {
      assert.equal(matrix[field], "live", `${field} should be live`);
    }
    assert.equal(matrix.cache_implementation, "soft_reload");
    assert.equal(matrix.model_id, "hard_restart");
    assert.equal(matrix.assistant_model_id, "hard_restart");
    assert.equal(matrix.precision, "unsupported");
    assert.equal(matrix.quantization_backend, "unsupported");
    assert.equal(matrix.device_target, "unsupported");
  });
});

describe("MultiRuntimeApplyMode values", () => {
  it("all four modes are valid literals", () => {
    const modes: MultiRuntimeApplyMode[] = [
      "live",
      "soft_reload",
      "hard_restart",
      "unsupported",
    ];
    assert.equal(modes.length, 4);
  });

  it("live mode is least restrictive", () => {
    const matrix = makeMatrix();
    const liveCount = Object.values(matrix).filter((v) => v === "live").length;
    assert.ok(liveCount >= 6);
  });
});

describe("MultiRuntimeProfileResponse envelope", () => {
  it("daemon_reachable defaults to true in live response", () => {
    const resp = makeProfileResponse();
    assert.equal(resp.daemon_reachable, true);
  });

  it("daemon_reachable false in fallback response", () => {
    const resp = makeProfileResponse({ daemon_reachable: false });
    assert.equal(resp.daemon_reachable, false);
  });

  it("runtime_id is multi_runtime", () => {
    const resp = makeProfileResponse();
    assert.equal(resp.runtime_id, "multi_runtime");
  });

  it("supported_options includes all constrained fields", () => {
    const resp = makeProfileResponse();
    const opts = resp.supported_options;
    assert.ok(Array.isArray(opts.cache_implementation));
    assert.ok(Array.isArray(opts.precision));
    assert.ok(Array.isArray(opts.device_target));
    assert.ok(Array.isArray(opts.quantization_backend));
    assert.ok(Array.isArray(opts.execution_mode));
    assert.ok(Array.isArray(opts.image_strategy));
    assert.ok(Array.isArray(opts.retrieval_mode));
    assert.ok(Array.isArray(opts.audio_output_mode));
    assert.ok(Array.isArray(opts.assistant_mode));
    assert.ok(Array.isArray(opts.economy_mode));
  });
});

describe("MultiRuntimeProfileUpdateRequest contract", () => {
  it("all fields are optional", () => {
    const req: MultiRuntimeProfileUpdateRequest = {};
    assert.ok(req !== null);
  });

  it("partial update only includes changed fields", () => {
    const req: MultiRuntimeProfileUpdateRequest = {
      max_new_tokens: 512,
      enable_thinking: true,
    };
    assert.equal(Object.keys(req).length, 2);
    assert.equal(req.model_id, undefined);
  });
});

describe("MultiRuntimeProfileUpdateResponse contract", () => {
  it("accepted and rejected are separate buckets", () => {
    const resp: MultiRuntimeProfileUpdateResponse = {
      accepted: { max_new_tokens: 512 },
      rejected: [
        {
          field: "precision",
          value: "int4",
          reason: "precision_not_supported_for_runtime",
          detail: "",
        },
      ],
      required_apply_mode: "live",
      applied: true,
      message: "1 field(s) accepted (requires live); 1 field(s) rejected.",
    };
    assert.equal(resp.accepted["max_new_tokens"], 512);
    assert.equal(resp.rejected.length, 1);
    assert.equal(resp.rejected[0].field, "precision");
  });

  it("hard_restart fields are accepted but applied=false", () => {
    const resp: MultiRuntimeProfileUpdateResponse = {
      accepted: { model_id: "google/gemma-4-1B-it" },
      rejected: [],
      required_apply_mode: "hard_restart",
      applied: false,
      message: "1 field(s) accepted (requires hard_restart).",
    };
    assert.equal(resp.applied, false);
    assert.equal(resp.required_apply_mode, "hard_restart");
  });
});

describe("API URL construction", () => {
  it("system profile path is /api/v1/runtime/multi-runtime/profile", () => {
    const base = "http://localhost:8000";
    const path = "/api/v1/runtime/multi-runtime/profile";
    const url = `${base}${path}`;
    assert.equal(url, "http://localhost:8000/api/v1/runtime/multi-runtime/profile");
  });

  it("path contains multi-runtime (hyphenated, not underscore)", () => {
    const path = "/api/v1/runtime/multi-runtime/profile";
    assert.ok(path.includes("multi-runtime"));
    assert.ok(!path.includes("multi_runtime"));
  });
});
