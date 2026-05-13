import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";

import type { DaemonStatus } from "../lib/gemma4-daemon-api";
import {
  fetchDaemonStatus,
  postAttachAssistant,
  postDaemonConfig,
  postDaemonFallback,
  postDaemonReload,
  postDaemonRestart,
  postDetachAssistant,
} from "../lib/gemma4-daemon-api";

const BASE = "http://127.0.0.1:8014";

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
      reasoning_summary_enabled: false,
      emotion_detection_enabled: false,
      emotion_response_style_enabled: false,
      cache_implementation: null,
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
    ...overrides,
  };
}

function makeJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  }) as Response;
}

function make204Response(): Response {
  return new Response(null, { status: 204 }) as Response;
}

function makeErrorResponse(status: number, text = "error"): Response {
  return new Response(text, { status }) as Response;
}

let originalFetch: typeof globalThis.fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  mock.restoreAll();
});

describe("fetchDaemonStatus", () => {
  it("returns parsed DaemonStatus on success", async () => {
    const expected = makeStatus();
    globalThis.fetch = async () => makeJsonResponse(expected);
    const result = await fetchDaemonStatus(BASE);
    assert.equal(result.target_model, "google/gemma-4-E2B-it");
    assert.equal(result.mode, "target_only");
    assert.equal(result.pending_reload, false);
  });

  it("requests the correct URL", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (url) => {
      capturedUrl = String(url);
      return makeJsonResponse(makeStatus());
    };
    await fetchDaemonStatus(BASE);
    assert.equal(capturedUrl, `${BASE}/v1/daemon/status`);
  });

  it("throws on non-OK response", async () => {
    globalThis.fetch = async () => makeErrorResponse(503, "Service Unavailable");
    await assert.rejects(
      () => fetchDaemonStatus(BASE),
      (err: Error) => {
        assert.ok(err.message.includes("503"));
        return true;
      },
    );
  });

  it("throws with response body text in error message", async () => {
    globalThis.fetch = async () => makeErrorResponse(400, "bad request body");
    await assert.rejects(
      () => fetchDaemonStatus(BASE),
      (err: Error) => {
        assert.ok(err.message.includes("bad request body"));
        return true;
      },
    );
  });
});

describe("postDaemonConfig", () => {
  it("POSTs to /v1/daemon/config with correct body", async () => {
    let capturedInit: RequestInit | undefined;
    globalThis.fetch = async (_url, init) => {
      capturedInit = init;
      return makeJsonResponse({
        reload_signal: "none",
        applied: {
          max_new_tokens: 256,
          enable_thinking: true,
          reasoning_summary_enabled: false,
          emotion_detection_enabled: false,
          emotion_response_style_enabled: false,
          cache_implementation: null,
        },
        message: "ok",
      });
    };
    const result = await postDaemonConfig(BASE, { max_new_tokens: 256, enable_thinking: true });
    assert.equal(capturedInit?.method, "POST");
    assert.equal(capturedInit?.body, JSON.stringify({ max_new_tokens: 256, enable_thinking: true }));
    assert.equal(result.reload_signal, "none");
    assert.equal(result.applied.max_new_tokens, 256);
  });

  it("returns soft_reload signal when cache_implementation changes", async () => {
    globalThis.fetch = async () =>
      makeJsonResponse({
        reload_signal: "soft_reload",
        applied: {
          max_new_tokens: 128,
          enable_thinking: false,
          reasoning_summary_enabled: false,
          emotion_detection_enabled: false,
          emotion_response_style_enabled: false,
          cache_implementation: "static",
        },
        message: "reload required",
      });
    const result = await postDaemonConfig(BASE, { cache_implementation: "static" });
    assert.equal(result.reload_signal, "soft_reload");
  });

  it("throws on error response", async () => {
    globalThis.fetch = async () => makeErrorResponse(422);
    await assert.rejects(() => postDaemonConfig(BASE, {}));
  });
});

describe("postDaemonReload", () => {
  it("POSTs to /v1/daemon/reload", async () => {
    let capturedUrl = "";
    let capturedMethod = "";
    globalThis.fetch = async (url, init) => {
      capturedUrl = String(url);
      capturedMethod = (init as RequestInit)?.method ?? "";
      return make204Response();
    };
    await postDaemonReload(BASE);
    assert.equal(capturedUrl, `${BASE}/v1/daemon/reload`);
    assert.equal(capturedMethod, "POST");
  });

  it("resolves without error on 204", async () => {
    globalThis.fetch = async () => make204Response();
    await assert.doesNotReject(() => postDaemonReload(BASE));
  });
});

describe("postDaemonRestart", () => {
  it("POSTs to /v1/daemon/restart", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (url) => {
      capturedUrl = String(url);
      return make204Response();
    };
    await postDaemonRestart(BASE);
    assert.equal(capturedUrl, `${BASE}/v1/daemon/restart`);
  });
});

describe("postDaemonFallback", () => {
  it("returns reload_signal from response", async () => {
    globalThis.fetch = async () =>
      makeJsonResponse({ reload_signal: "hard_restart", message: "fallback triggered" });
    const result = await postDaemonFallback(BASE);
    assert.equal(result.reload_signal, "hard_restart");
  });

  it("POSTs to /v1/daemon/fallback", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (url) => {
      capturedUrl = String(url);
      return makeJsonResponse({ reload_signal: "none", message: "" });
    };
    await postDaemonFallback(BASE);
    assert.equal(capturedUrl, `${BASE}/v1/daemon/fallback`);
  });
});

describe("postAttachAssistant", () => {
  it("POSTs model_id to /v1/daemon/assistant/attach", async () => {
    let capturedUrl = "";
    let capturedBody = "";
    globalThis.fetch = async (url, init) => {
      capturedUrl = String(url);
      capturedBody = String((init as RequestInit)?.body ?? "");
      return make204Response();
    };
    await postAttachAssistant(BASE, "google/gemma-4-E2B-it-assistant");
    assert.equal(capturedUrl, `${BASE}/v1/daemon/assistant/attach`);
    assert.deepEqual(JSON.parse(capturedBody), { model_id: "google/gemma-4-E2B-it-assistant" });
  });

  it("throws when fetch fails", async () => {
    globalThis.fetch = async () => makeErrorResponse(500);
    await assert.rejects(() => postAttachAssistant(BASE, "some-model"));
  });
});

describe("postDetachAssistant", () => {
  it("POSTs to /v1/daemon/assistant/detach", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (url) => {
      capturedUrl = String(url);
      return make204Response();
    };
    await postDetachAssistant(BASE);
    assert.equal(capturedUrl, `${BASE}/v1/daemon/assistant/detach`);
  });

  it("resolves on 204 no-content", async () => {
    globalThis.fetch = async () => make204Response();
    await assert.doesNotReject(() => postDetachAssistant(BASE));
  });
});

describe("daemonFetch error handling", () => {
  it("includes path in error message", async () => {
    globalThis.fetch = async () => makeErrorResponse(404);
    await assert.rejects(
      () => fetchDaemonStatus(BASE),
      (err: Error) => {
        assert.ok(err.message.includes("/v1/daemon/status"));
        return true;
      },
    );
  });

  it("includes status code in error message", async () => {
    globalThis.fetch = async () => makeErrorResponse(401);
    await assert.rejects(
      () => fetchDaemonStatus(BASE),
      (err: Error) => {
        assert.ok(err.message.includes("401"));
        return true;
      },
    );
  });
});
