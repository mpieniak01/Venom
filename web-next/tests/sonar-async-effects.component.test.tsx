import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

import { useInspectorState } from "../app/(console)/inspector/use-inspector-state";
import { useGemma4Daemon } from "../hooks/use-gemma4-daemon";
import { useAppMeta } from "../lib/app-meta";

const originalFetch = globalThis.fetch;
const originalEventSource = globalThis.EventSource;

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  globalThis.EventSource = originalEventSource;
  mock.restoreAll();
  delete globalThis.__VENOM_APP_META__;
});

describe("detached effects with internal error handling", () => {
  it("reports a rejected daemon poll without an unhandled promise", async () => {
    globalThis.fetch = async () => {
      throw new Error("daemon offline");
    };
    const { result } = renderHook(() => useGemma4Daemon(60_000));

    await waitFor(() => assert.equal(result.current.loading, false));
    assert.equal(result.current.error, "daemon offline");
    assert.equal(result.current.status, null);
  });

  it("falls back after a rejected meta request and reuses the cached value", async () => {
    let requests = 0;
    globalThis.fetch = async () => {
      requests += 1;
      throw new Error("meta offline");
    };
    const warnings = mock.method(console, "warn", () => {});
    const first = renderHook(() => useAppMeta());

    await waitFor(() => assert.equal(warnings.mock.callCount(), 1));
    await act(async () => { await Promise.resolve(); });
    assert.equal(requests, 1);
    assert.equal(first.result.current?.version, process.env.NEXT_PUBLIC_APP_VERSION);
    const fallback = first.result.current;
    first.unmount();

    const cached = renderHook(() => useAppMeta());
    await act(async () => { await Promise.resolve(); });
    assert.deepEqual(cached.result.current, fallback);
    assert.equal(requests, 1);
  });

  it("handles both inspector trace and history fallback rejection", async () => {
    const failures = mock.method(console, "error");
    class FakeEventSource extends EventTarget {
      onopen = null;
      onerror = null;
      close() {}
    }
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
    globalThis.fetch = async (input) => {
      const url = String(input);
      if (url.includes("/api/v1/history/requests?")) {
        return Response.json([{
          request_id: "trace-1",
          status: "COMPLETED",
          prompt: "Test request",
          created_at: new Date().toISOString(),
        }]);
      }
      if (url.endsWith("/api/v1/tasks")) return Response.json([]);
      if (url.endsWith("/api/v1/tasks/trace-1")) {
        return Response.json({ id: "trace-1", status: "COMPLETED", logs: [] });
      }
      throw new Error("trace offline");
    };
    const { result } = renderHook(() => useInspectorState((key) => key));

    await waitFor(() => assert.equal(result.current.selectedId, "trace-1"));
    await waitFor(() => assert.equal(result.current.diagramLoading, false));
    assert.equal(result.current.detailError, "trace offline");
    assert.equal(result.current.diagram, "inspector.panels.diagram.fallback");
    assert.equal(result.current.steps.length, 0);
    assert.ok(failures.mock.callCount() >= 2);

    await act(async () => { window.dispatchEvent(new Event("focus")); });
    assert.equal(result.current.diagramLoading, false);
  });
});
