import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";

import { ApiError, apiFetch } from "../lib/api-client";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  mock.restoreAll();
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
    const capture: { headers?: Headers } = {};
    globalThis.fetch = (async (_input, init) => {
      capture.headers = new Headers(init?.headers as HeadersInit);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as typeof fetch;

    await apiFetch<{ ok: boolean }>("/api/v1/system/llm-servers/active", {
      headers: new Headers([["X-Test-Header", "abc"]]),
    });

    assert.ok(capture.headers);
    assert.equal(capture.headers.get("X-Test-Header"), "abc");
    assert.equal(capture.headers.get("Content-Type"), "application/json");
  });
  it("awaits response parsing inside the retry error boundary", async () => {
    let calls = 0;
    const interrupted = Response.json({ ok: false });
    Object.defineProperty(interrupted, "json", {
      value: () => Promise.reject(new TypeError("response body interrupted")),
    });
    globalThis.fetch = async () => ++calls === 1 ? interrupted : Response.json({ ok: true });
    const result = await apiFetch<{ ok: boolean }>("/api/v1/system/llm-servers/active");
    assert.equal(result.ok, true);
    assert.equal(calls, 2);
  });

  it("keeps retries bounded and waits for each configured backoff", async () => {
    let calls = 0;
    const timer = mock.method(globalThis, "setTimeout");
    globalThis.fetch = async () => { calls += 1; throw new TypeError("offline"); };
    await assert.rejects(apiFetch("/api/v1/system/llm-servers/active"), /offline/);
    assert.equal(calls, 3);
    assert.deepEqual(timer.mock.calls.map((call) => call.arguments[1]), [200, 500]);
  });

});
