import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

import { useHistory, useQueueStatus } from "../hooks/use-api";
import { useTaskStream } from "../hooks/use-task-stream";

const originalFetch = globalThis.fetch;
const originalEventSource = globalThis.EventSource;

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  globalThis.EventSource = originalEventSource;
  mock.restoreAll();
});

describe("shared API polling", () => {
  it("deduplicates subscribers, reports rejection, and stops the final timer", async () => {
    let requests = 0;
    let rejectRequest: (error: Error) => void = () => { throw new Error("request not started"); };
    globalThis.fetch = () => {
      requests += 1;
      return new Promise<Response>((_resolve, reject) => { rejectRequest = reject; });
    };
    const starts = mock.method(globalThis, "setInterval");
    const stops = mock.method(globalThis, "clearInterval");
    const hook = renderHook(() => ({
      first: useHistory(81001, 60_000),
      second: useHistory(81001, 60_000),
    }));

    assert.equal(requests, 1);
    await act(async () => { rejectRequest(new Error("history offline")); });
    await waitFor(() => assert.equal(hook.result.current.first.error, "history offline"));
    assert.equal(hook.result.current.second.error, "history offline");
    assert.equal(requests, 1);
    const timer = starts.mock.calls.find((call) => call.arguments[1] === 60_000);
    assert.ok(timer);
    hook.unmount();
    assert.ok(stops.mock.calls.some((call) => call.arguments[0] === timer.result));
  });

  it("retains the offline backoff and resumes after expiry", async () => {
    let now = 1000;
    let offline = true;
    let requests = 0;
    mock.method(Date, "now", () => now);
    globalThis.fetch = async () => {
      requests += 1;
      return offline ? new Response("Unavailable", { status: 503 }) : Response.json([]);
    };
    const starts = mock.method(globalThis, "setInterval");
    const hook = renderHook(() => useHistory(81002, 60_000));
    await waitFor(() => assert.ok(hook.result.current.error?.includes("503")), { timeout: 2000 });
    assert.equal(requests, 3);
    const timer = starts.mock.calls.find((call) => call.arguments[1] === 60_000);
    assert.ok(timer);
    const tick = timer.arguments[0] as () => Promise<void>;

    now = 15_999;
    await act(async () => { await tick(); });
    assert.equal(requests, 3);
    now = 16_001;
    offline = false;
    await act(async () => { await tick(); });
    assert.equal(requests, 4);
    assert.equal(hook.result.current.error, null);
    assert.deepEqual(hook.result.current.data, []);
  });
});

describe("explicit background refresh", () => {
  it("waits past an old GET snapshot and shares one fresh request per refresh boundary", async () => {
    let paused = false;
    let immediate = false;
    let requests = 0;
    let active = 0;
    let maxActive = 0;
    const pending: (() => void)[] = [];
    globalThis.fetch = () => {
      requests += 1;
      active += 1;
      maxActive = Math.max(maxActive, active);
      const response = Response.json({ active: 0, pending: 0, limit: 5, paused });
      if (immediate) {
        active -= 1;
        return Promise.resolve(response);
      }
      return new Promise<Response>((resolve) => {
        pending.push(() => {
          active -= 1;
          resolve(response);
        });
      });
    };
    const starts = mock.method(globalThis, "setInterval");
    const hook = renderHook(() => ({
      first: useQueueStatus(60_000),
      second: useQueueStatus(60_000),
    }));
    let background: Promise<void> | undefined;
    let firstRefresh: Promise<void> | undefined;
    let secondRefresh: Promise<void> | undefined;
    let laterRefresh: Promise<void> | undefined;
    try {
      assert.equal(requests, 1);
      await act(async () => { pending.shift()?.(); });
      await waitFor(() => assert.equal(hook.result.current.first.data?.paused, false));
      const timer = starts.mock.calls.find((call) => call.arguments[1] === 60_000);
      assert.ok(timer);
      const tick = timer.arguments[0] as () => Promise<void>;
      act(() => { background = tick(); });
      assert.equal(requests, 2);

      // The GET already captured false. A completed mutation now changes the
      // server to true, so neither explicit refresh may settle with that GET.
      paused = true;
      let firstDone = false;
      let secondDone = false;
      act(() => {
        firstRefresh = hook.result.current.first.refresh().then(() => { firstDone = true; });
        secondRefresh = hook.result.current.second.refresh().then(() => { secondDone = true; });
      });
      await act(async () => { await Promise.resolve(); });
      assert.equal(requests, 2);
      assert.equal(firstDone, false);
      assert.equal(secondDone, false);
      await act(async () => {
        pending.shift()?.();
        await background;
      });
      assert.equal(requests, 3);
      assert.equal(maxActive, 1);
      assert.equal(hook.result.current.first.data?.paused, false);
      assert.equal(hook.result.current.first.refreshing, true);
      assert.equal(firstDone, false);
      assert.equal(secondDone, false);

      // A refresh called after this new GET started needs another boundary;
      // it cannot join a response captured before this second mutation.
      paused = false;
      let laterDone = false;
      act(() => {
        laterRefresh = hook.result.current.first.refresh().then(() => { laterDone = true; });
      });
      await act(async () => {
        pending.shift()?.();
        await Promise.all([firstRefresh, secondRefresh]);
      });
      assert.equal(firstDone, true);
      assert.equal(secondDone, true);
      assert.equal(laterDone, false);
      assert.equal(requests, 4);
      assert.equal(hook.result.current.first.data?.paused, true);
      assert.equal(hook.result.current.first.refreshing, true);
      await act(async () => {
        pending.shift()?.();
        await laterRefresh;
      });
      assert.equal(laterDone, true);
      assert.equal(hook.result.current.first.data?.paused, false);
      assert.equal(hook.result.current.second.data?.paused, false);
      assert.equal(hook.result.current.first.refreshing, false);
      assert.equal(hook.result.current.first.error, null);
      assert.equal(requests, 4);
      assert.equal(maxActive, 1);
      assert.equal(active, 0);
    } finally {
      immediate = true;
      await act(async () => {
        pending.splice(0).forEach((release) => release());
        await Promise.allSettled([background, firstRefresh, secondRefresh, laterRefresh]);
      });
      hook.unmount();
    }
  });

  it("contains a deferred manual refresh rejection in hook error state", async () => {
    globalThis.fetch = async () => Response.json([]);
    const hook = renderHook(() => useHistory(81003, 60_000));
    await waitFor(() => assert.deepEqual(hook.result.current.data, []));
    let rejectRefresh!: (error: Error) => void;
    let requests = 0;
    globalThis.fetch = () => {
      requests += 1;
      return new Promise<Response>((_resolve, reject) => { rejectRefresh = reject; });
    };
    let refresh!: Promise<void>;
    act(() => { refresh = hook.result.current.refresh(); });
    assert.equal(requests, 1);
    await act(async () => {
      rejectRefresh(new Error("manual refresh offline"));
      await refresh;
    });
    assert.equal(hook.result.current.error, "manual refresh offline");
    assert.equal(hook.result.current.loading, false);
    assert.deepEqual(hook.result.current.data, []);
    assert.equal(requests, 1);
    hook.unmount();
  });
});

describe("task stream polling fallback", () => {
  for (const completion of ["terminal", "unmount"] as const) {
    it(`handles SSE/fetch errors and releases the retry on ${completion}`, async () => {
      const sources: FakeEventSource[] = [];
      class FakeEventSource extends window.EventTarget {
        onopen: (() => void) | null = null;
        onerror: (() => void) | null = null;
        closed = false;
        constructor() { super(); sources.push(this); }
        close() { this.closed = true; }
      }
      globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
      let fail = false;
      let requests = 0;
      globalThis.fetch = async () => {
        requests += 1;
        if (fail) throw new Error("task offline");
        return Response.json({ status: "PROCESSING", logs: [] });
      };
      const starts = mock.method(window, "setTimeout");
      const stops = mock.method(window, "clearTimeout");
      const taskIds = [`poll-${completion}`];
      const hook = renderHook(() => useTaskStream(taskIds, { throttleMs: 0 }));
      await waitFor(() => assert.equal(hook.result.current.streams[taskIds[0]]?.status, "PROCESSING"));
      assert.equal(sources.length, 1);
      const source = sources[0];
      await act(async () => { source.onopen?.(); });
      fail = true;
      await act(async () => { source.onerror?.(); });
      await waitFor(() => assert.equal(starts.mock.callCount(), 2));
      assert.equal(requests, 2);
      const retry = starts.mock.calls.at(-1)?.result;
      assert.notEqual(retry, undefined);
      await act(async () => { source.onerror?.(); });
      assert.equal(requests, 2);
      assert.equal(starts.mock.callCount(), 2);

      if (completion === "terminal") {
        await act(async () => {
          source.dispatchEvent(new window.MessageEvent("task_finished", {
            data: JSON.stringify({ task_id: taskIds[0], status: "COMPLETED", result: "done" }),
          }));
        });
        assert.equal(hook.result.current.streams[taskIds[0]].status, "COMPLETED");
      } else {
        hook.unmount();
      }
      assert.equal(source.closed, true);
      assert.ok(stops.mock.calls.some((call) => call.arguments[0] === retry));
    });
  }
});
