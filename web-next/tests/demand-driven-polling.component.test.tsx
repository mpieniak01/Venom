import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { act, cleanup, fireEvent, render, renderHook, waitFor } from "@testing-library/react";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { useQueueStatus, useServiceStatus } from "../hooks/use-api";
import { useTelemetryFeed } from "../hooks/use-telemetry";
import { CommandCenter } from "../components/layout/command-center";
import { ServiceStatusDrawer } from "../components/layout/service-status-drawer";
import { QuickActions } from "../components/layout/quick-actions";
import { LanguageProvider } from "../lib/i18n";

const originalFetch = globalThis.fetch;
const originalWebSocket = globalThis.WebSocket;
const router = { bfcacheId: "test-router", back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };

beforeEach(() => {
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  globalThis.fetch = async () => Response.json({ active: 0, pending: 0, limit: 5, paused: false });
});

afterEach(() => {
  cleanup();
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  globalThis.fetch = originalFetch;
  globalThis.WebSocket = originalWebSocket;
  mock.restoreAll();
});

describe("demand-driven polling subscriptions", () => {
  it("does not fetch or refresh until enabled, and detaches when disabled again", async () => {
    let requests = 0;
    globalThis.fetch = async () => { requests += 1; return Response.json([]); };
    const hook = renderHook(({ enabled }) => useServiceStatus(60_000, enabled), { initialProps: { enabled: false } });
    assert.equal(requests, 0);
    assert.equal(hook.result.current.loading, false);
    await act(async () => { await hook.result.current.refresh(); });
    assert.equal(requests, 0);
    hook.rerender({ enabled: true });
    await waitFor(() => assert.equal(requests, 1));
    await waitFor(() => assert.deepEqual(hook.result.current.data, []));
    hook.rerender({ enabled: false });
    await act(async () => { await hook.result.current.refresh(); });
    assert.equal(requests, 1);
    hook.rerender({ enabled: true });
    await waitFor(() => assert.equal(requests, 2));
    hook.unmount();
  });

  it("restores the slower interval when the last fast subscriber closes", async () => {
    const starts = mock.method(globalThis, "setInterval");
    const stops = mock.method(globalThis, "clearInterval");
    const hook = renderHook(({ fast }) => ({
      slow: useQueueStatus(60_000),
      fast: useQueueStatus(5000, fast),
    }), { initialProps: { fast: true } });
    await waitFor(() => assert.ok(hook.result.current.slow.data));
    const fastTimer = starts.mock.calls.findLast((call) => call.arguments[1] === 5000);
    assert.ok(fastTimer);
    hook.rerender({ fast: false });
    assert.ok(stops.mock.calls.some((call) => call.arguments[0] === fastTimer.result));
    const restoredTimer = starts.mock.calls.at(-1);
    assert.equal(restoredTimer?.arguments[1], 60_000);
    hook.unmount();
    assert.ok(stops.mock.calls.some((call) => call.arguments[0] === restoredTimer?.result));
  });

  it("pauses hidden telemetry and shares a single fresh GET on returning to a visible document", async () => {
    let requests = 0;
    globalThis.fetch = async () => { requests += 1; return Response.json({ active: 0 }); };
    const starts = mock.method(globalThis, "setInterval");
    const stops = mock.method(globalThis, "clearInterval");
    const hook = renderHook(() => ({
      first: useQueueStatus(60_000),
      second: useQueueStatus(60_000),
    }));
    await waitFor(() => assert.equal(hook.result.current.first.loading, false));
    assert.equal(requests, 1);
    const timer = starts.mock.calls.findLast((call) => call.arguments[1] === 60_000);
    assert.ok(timer);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    fireEvent(document, new Event("visibilitychange"));
    assert.ok(stops.mock.calls.some((call) => call.arguments[0] === timer.result));
    await act(async () => { await (timer.arguments[0] as () => Promise<void>)(); });
    assert.equal(requests, 1);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    await act(async () => { fireEvent(document, new Event("visibilitychange")); });
    assert.equal(requests, 2);
    assert.deepEqual(hook.result.current.first.data, hook.result.current.second.data);
    hook.unmount();
  });

  it("mounts closed global panels without starting their API subscriptions", async () => {
    let requests = 0;
    globalThis.fetch = async () => { requests += 1; return Response.json([]); };
    render(<AppRouterContext.Provider value={router}><LanguageProvider>
      <CommandCenter open={false} onOpenChange={() => {}} />
      <QuickActions open={false} onOpenChange={() => {}} />
      <ServiceStatusDrawer open={false} onOpenChange={() => {}} />
    </LanguageProvider></AppRouterContext.Provider>);
    await act(async () => { await Promise.resolve(); });
    assert.equal(requests, 0);
  });
});

describe("closed panel telemetry transport", () => {
  it("does not connect while disabled, keeps entries, and never reconnects after a deliberate close", async () => {
    const sockets: FakeSocket[] = [];
    class FakeSocket {
      onopen: (() => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      closed = false;
      constructor() { sockets.push(this); }
      close() { this.closed = true; this.onclose?.(); }
    }
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
    const timeouts = mock.method(globalThis, "setTimeout");
    const hook = renderHook(({ enabled }) => useTelemetryFeed(10, enabled), { initialProps: { enabled: false } });
    assert.equal(sockets.length, 0);
    hook.rerender({ enabled: true });
    assert.equal(sockets.length, 1);
    act(() => {
      sockets[0].onopen?.();
      sockets[0].onmessage?.({ data: JSON.stringify({ message: "retained" }) });
    });
    assert.equal(hook.result.current.connected, true);
    assert.equal(hook.result.current.entries.length, 1);
    const beforeClose = timeouts.mock.calls.length;
    hook.rerender({ enabled: false });
    assert.equal(sockets[0].closed, true);
    assert.equal(hook.result.current.connected, false);
    assert.equal(hook.result.current.entries.length, 1);
    assert.equal(timeouts.mock.calls.length, beforeClose);
    hook.rerender({ enabled: true });
    assert.equal(sockets.length, 2);
    assert.equal(hook.result.current.connected, false);
    act(() => { sockets[1].onopen?.(); });
    assert.equal(hook.result.current.connected, true);
    hook.unmount();
    assert.equal(sockets[1].closed, true);
  });
});
