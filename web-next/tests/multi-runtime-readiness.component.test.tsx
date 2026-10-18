import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useMultiRuntimeProfile } from "../hooks/use-multi-runtime-profile";

const originalFetch = globalThis.fetch;
const originalTimeout = globalThis.setTimeout;

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  mock.restoreAll();
});

function pendingResponse() {
  let resolve!: (response: Response) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Response>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function fastReadinessTimers(onDelay: () => void = () => {}) {
  const delays: number[] = [];
  mock.method(globalThis, "setTimeout", ((callback: (...args: unknown[]) => void, delay?: number, ...args: unknown[]) => {
    if (delay === 1000) {
      delays.push(delay);
      return originalTimeout(() => { onDelay(); callback(...args); }, 0);
    }
    return originalTimeout(callback, delay, ...args);
  }) as typeof setTimeout);
  return delays;
}

function serveProfile(status: () => Promise<Response>) {
  const counts = { mutations: 0, reloads: 0, statuses: 0 };
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/daemon/status")) {
      counts.statuses += 1;
      return status();
    }
    if (url.endsWith("/v1/daemon/reload")) {
      counts.reloads += 1;
      return Response.json({ ok: true });
    }
    assert.ok(url.endsWith("/api/v1/runtime/multi-runtime/profile"), url);
    if (init?.method === "POST") {
      counts.mutations += 1;
      return Response.json({ required_apply_mode: "soft_reload", applied: false });
    }
    return Response.json({ runtime_id: "multi_runtime", profile: {}, daemon_reachable: true });
  };
  return counts;
}

describe("dependent daemon readiness polling", () => {
  it("waits for each result, tolerates restart downtime and never repeats the mutation", async () => {
    const delays = fastReadinessTimers();
    const first = pendingResponse();
    let statusAttempt = 0;
    const counts = serveProfile(() => {
      statusAttempt += 1;
      if (statusAttempt === 1) return first.promise;
      return Promise.resolve(Response.json({ pending_reload: statusAttempt === 2 }));
    });
    const hook = renderHook(() => useMultiRuntimeProfile(60_000));
    await waitFor(() => assert.equal(hook.result.current.loading, false), { timeout: 2000 });
    let update!: ReturnType<typeof hook.result.current.applyUpdate>;
    await act(async () => { update = hook.result.current.applyUpdate({ max_new_tokens: 128 }); });
    await waitFor(() => assert.equal(counts.statuses, 1), { timeout: 2000 });
    assert.equal(hook.result.current.updatePending, true);
    assert.equal(delays.length, 0);
    await act(async () => { first.reject(new Error("restarting")); await update; });
    assert.equal(counts.statuses, 3);
    assert.deepEqual(delays, [1000, 1000]);
    assert.equal(counts.mutations, 1);
    assert.equal(counts.reloads, 1);
    assert.equal(hook.result.current.updatePending, false);
    assert.equal(hook.result.current.error, null);
    hook.unmount();
  });

  it("reports readiness timeout without replaying the accepted update", async () => {
    const counts = serveProfile(() => Promise.resolve(Response.json({ pending_reload: true })));
    const hook = renderHook(() => useMultiRuntimeProfile(60_000));
    await waitFor(() => assert.equal(hook.result.current.loading, false), { timeout: 2000 });
    let now = 1000;
    mock.method(Date, "now", () => now);
    fastReadinessTimers(() => { now += 180_001; });
    let result: unknown;
    await act(async () => { result = await hook.result.current.applyUpdate({ max_new_tokens: 128 }); });
    assert.equal(result, null);
    assert.match(hook.result.current.error ?? "", /Timed out/);
    assert.equal(hook.result.current.updatePending, false);
    assert.equal(counts.mutations, 1);
    assert.equal(counts.reloads, 1);
    assert.equal(counts.statuses, 1);
    hook.unmount();
  });

  it("stops readiness polling after unmount without repeating effects", async () => {
    fastReadinessTimers();
    const first = pendingResponse();
    const counts = serveProfile(() => first.promise);
    const hook = renderHook(() => useMultiRuntimeProfile(60_000));
    await waitFor(() => assert.equal(hook.result.current.loading, false), { timeout: 2000 });
    let update!: ReturnType<typeof hook.result.current.applyUpdate>;
    await act(async () => { update = hook.result.current.applyUpdate({ max_new_tokens: 128 }); });
    await waitFor(() => assert.equal(counts.statuses, 1), { timeout: 2000 });
    hook.unmount();
    await act(async () => { first.resolve(Response.json({ pending_reload: true })); await update; });
    assert.equal(counts.statuses, 1);
    assert.equal(counts.mutations, 1);
    assert.equal(counts.reloads, 1);
  });
});
