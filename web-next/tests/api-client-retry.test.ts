import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { ApiError, apiFetch } from "../lib/api-client";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("apiFetch retry policy", () => {
  it("retries GET on transient 500 and succeeds", async () => {
    let calls = 0;
    globalThis.fetch = (async () => {
      calls += 1;
      if (calls < 3) {
        return new Response("Internal Server Error", { status: 500 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as typeof fetch;

    const result = await apiFetch<{ ok: boolean }>("/api/v1/system/llm-servers/active");
    assert.equal(result.ok, true);
    assert.equal(calls, 3);
  });

  it("does not retry POST on 500", async () => {
    let calls = 0;
    globalThis.fetch = (async () => {
      calls += 1;
      return new Response("Internal Server Error", { status: 500 });
    }) as typeof fetch;

    await assert.rejects(
      apiFetch("/api/v1/system/llm-servers/active", { method: "POST" }),
      (error: unknown) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.status, 500);
        return true;
      },
    );
    assert.equal(calls, 1);
  });

  it("retries GET on network TypeError and succeeds", async () => {
    let calls = 0;
    globalThis.fetch = (async () => {
      calls += 1;
      if (calls === 1) {
        throw new TypeError("socket hang up");
      }
      return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
    }) as typeof fetch;

    const result = await apiFetch<{ status: string }>("/api/v1/system/llm-servers/active");
    assert.equal(result.status, "ok");
    assert.equal(calls, 2);
  });

  it("preserves HeadersInit entries for Headers instance input", async () => {
    let capturedHeaders: Headers | null = null;
    globalThis.fetch = (async (_input, init) => {
      capturedHeaders = new Headers(init?.headers as HeadersInit);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as typeof fetch;

    await apiFetch<{ ok: boolean }>("/api/v1/system/llm-servers/active", {
      headers: new Headers([["X-Test-Header", "abc"]]),
    });

    assert.ok(capturedHeaders);
    assert.equal(capturedHeaders?.get("X-Test-Header"), "abc");
    assert.equal(capturedHeaders?.get("Content-Type"), "application/json");
  });
});
