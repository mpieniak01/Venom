import "./component-test-setup";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, describe, it } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useTelemetryFeed } from "../hooks/use-telemetry";
import { useOptimisticRequests } from "../components/cockpit/cockpit-chat-hooks";
import { useModelIntrospectionSnapshot } from "../components/inspector/use-model-introspection-snapshot";
import { useModelIntrospectionAnalysisStream } from "../components/inspector/use-model-introspection-analysis-stream";

const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
const originalSocket = globalThis.WebSocket;
const originalFetch = globalThis.fetch;
const originalEnv = { ...process.env };
const sockets: FixtureSocket[] = [];
class FixtureSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly url: string) { sockets.push(this); }
  close() {} // No network/timers; unmount only releases this fixture.
}

beforeEach(() => {
  sockets.length = 0;
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) },
  });
  Object.defineProperty(globalThis, "WebSocket", { configurable: true, value: FixtureSocket });
  process.env.NEXT_PUBLIC_TRANSPORT_PROFILE = "trusted_lan";
  process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
  process.env.NEXT_PUBLIC_DISABLE_WS_EVENTS = "false";
});
afterEach(() => {
  cleanup();
  if (originalCrypto) Object.defineProperty(globalThis, "crypto", originalCrypto);
  Object.defineProperty(globalThis, "WebSocket", { configurable: true, value: originalSocket });
  globalThis.fetch = originalFetch;
  for (const key of Object.keys(process.env)) if (!(key in originalEnv)) delete process.env[key];
  Object.assign(process.env, originalEnv);
});

describe("HTTP browser hook regressions without randomUUID", () => {
  it("receives telemetry through the normal socket hook without crashing mobile navigation", () => {
    const { result } = renderHook(() => useTelemetryFeed(2));
    assert.equal(typeof globalThis.crypto.randomUUID, "undefined");
    assert.equal(sockets.length, 1);
    act(() => {
      sockets[0].onopen?.();
      for (const sequence of [1, 2, 3]) sockets[0].onmessage?.({ data: JSON.stringify({ sequence }) });
    });
    assert.equal(result.current.connected, true);
    assert.equal(result.current.entries.length, 2);
    assert.deepEqual(result.current.entries.map((entry) => entry.payload), [{ sequence: 3 }, { sequence: 2 }]);
    for (const entry of result.current.entries) {
      assert.match(entry.id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    }
  });
  it("creates and links optimistic requests with CSPRNG IDs over HTTP", () => {
    const { result } = renderHook(() => useOptimisticRequests());
    let clientId = "";
    act(() => { clientId = result.current.enqueueOptimisticRequest("fixture prompt"); });
    assert.match(clientId, /^opt-[0-9a-z]+-[0-9a-f]{32}$/);
    act(() => result.current.linkOptimisticRequest(clientId, "server-request"));
    assert.equal(result.current.optimisticRequests[0].requestId, "server-request");
    assert.equal(result.current.optimisticRequests[0].confirmed, true);
  });
  it("routes snapshot and streaming inspector requests through the browser origin", async () => {
    const calls: { url: string; method: string }[] = [];
    globalThis.fetch = async (input, init) => {
      calls.push({ url: String(input), method: init?.method || "GET" });
      return new Response('{"snapshot":null}', { status: init?.method === "POST" ? 503 : 200 });
    };
    const snapshot = renderHook(() => useModelIntrospectionSnapshot({ autoLoad: false }));
    await act(async () => { await snapshot.result.current.loadSnapshot(); });
    const stream = renderHook(() => useModelIntrospectionAnalysisStream({ analysisMechanismEnabled: false, analysisPrompt: "fixture" }));
    await act(async () => { await stream.result.current.runAnalysis(); });
    assert.deepEqual(calls, [
      { url: "/api/v1/models/introspection", method: "GET" },
      { url: "/api/v1/models/introspection/analyze/stream", method: "POST" },
    ]);
  });
});
