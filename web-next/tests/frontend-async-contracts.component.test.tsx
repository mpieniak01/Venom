import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";

import { ControlPanels } from "../components/workflow-control/ControlPanels";
import { AcademyDashboard } from "../components/academy/academy-dashboard";
import { QuickActions } from "../components/layout/quick-actions";
import { useQueueStatus } from "../hooks/use-api";
import { LanguageSwitcher } from "../components/layout/language-switcher";
import { useTrainableModels } from "../components/models/hooks/use-trainable-models";
import { LanguageProvider } from "../lib/i18n";
import type { PlanRequest } from "../types/workflow-control";

const originalFetch = globalThis.fetch;
const originalConfirm = globalThis.confirm;
const cacheKey = "trainable-models-cache";

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  globalThis.confirm = originalConfirm;
  window.localStorage.removeItem(cacheKey);
  window.localStorage.removeItem("venom-language");
  mock.restoreAll();
});

function chooseStrategy() {
  const select = document.querySelector<HTMLSelectElement>("select");
  assert.ok(select);
  fireEvent.change(select, { target: { value: "advanced" } });
}

describe("ControlPanels async apply boundary", () => {
  it("submits once, blocks duplicate clicks and shows callback rejection", async () => {
    const requests: PlanRequest[] = [];
    let rejectApply!: (error: Error) => void;
    render(<form onSubmit={(event) => event.preventDefault()}><ControlPanels systemState={{ decision_strategy: "standard" }} isLoading={false}
      onApply={(request) => {
        requests.push(request);
        return new Promise<void>((_resolve, reject) => { rejectApply = reject; });
      }} /></form>);
    chooseStrategy();
    const button = screen.getByRole("button", { name: /Plan & Apply|Zaplanuj i zastosuj|planen/i });
    fireEvent.click(button);
    assert.equal((button as HTMLButtonElement).disabled, true);
    fireEvent.click(button);
    assert.equal(requests.length, 1);
    assert.deepEqual(requests[0], {
      changes: [{ resource_type: "decision_strategy", resource_id: "system", action: "update", current_value: "standard", new_value: "advanced" }],
      dry_run: false,
      force: false,
    });
    await act(async () => { rejectApply(new Error("apply denied")); });
    assert.match((await screen.findByRole("alert")).textContent ?? "", /apply denied/);
    assert.equal((button as HTMLButtonElement).disabled, false);
    assert.equal(requests.length, 1);
  });

  it("does not submit while externally loading or when no change was selected", () => {
    const onApply = mock.fn(() => Promise.resolve());
    const view = render(<form onSubmit={(event) => event.preventDefault()}><ControlPanels systemState={{ decision_strategy: "standard" }} isLoading onApply={onApply} /></form>);
    chooseStrategy();
    fireEvent.click(screen.getByRole("button", { name: /Applying|Stosowanie|angewendet/i }));
    assert.equal(onApply.mock.callCount(), 0);
    view.unmount();
    render(<form onSubmit={(event) => event.preventDefault()}><ControlPanels systemState={{ decision_strategy: "standard" }} isLoading={false} onApply={onApply} /></form>);
    fireEvent.click(screen.getByRole("button", { name: /Plan & Apply|Zaplanuj i zastosuj|planen/i }));
    assert.equal(onApply.mock.callCount(), 0);
  });
});

describe("detached initialization preserves its error boundary", () => {
  it("ends trainable loading on a rejected initial request", async () => {
    mock.method(console, "error", () => {});
    globalThis.fetch = async () => { throw new Error("catalog offline"); };
    const hook = renderHook(() => useTrainableModels());
    await waitFor(() => assert.equal(hook.result.current.loading, false), { timeout: 2000 });
    assert.equal(hook.result.current.error, "catalog offline");
    assert.deepEqual(hook.result.current.trainableModels, []);
  });

  it("keeps a fresh trainable cache without a request", async () => {
    window.localStorage.setItem(cacheKey, JSON.stringify({ data: [], timestamp: Date.now() }));
    const fetch = mock.fn(async () => Response.json({}));
    globalThis.fetch = fetch;
    const hook = renderHook(() => useTrainableModels());
    await waitFor(() => assert.equal(hook.result.current.loading, false));
    assert.equal(hook.result.current.error, null);
    assert.deepEqual(hook.result.current.trainableModels, []);
    assert.equal(fetch.mock.callCount(), 0);
  });

  it("continues without cache if storage is unavailable", async () => {
    mock.method(Object.getPrototypeOf(window.localStorage), "getItem", () => { throw new Error("storage denied"); });
    globalThis.fetch = async () => Response.json({ model_catalog: { trainable_models: [] } });
    const hook = renderHook(() => useTrainableModels());
    await waitFor(() => assert.equal(hook.result.current.loading, false));
    assert.equal(hook.result.current.error, null);
    assert.deepEqual(hook.result.current.trainableModels, []);
  });

  it("shows the Academy initial request error and finishes loading", async () => {
    mock.method(console, "error", () => {});
    globalThis.fetch = async () => { throw new Error("academy offline"); };
    render(<AcademyDashboard />);
    const error = await screen.findByText(/academy offline/, {}, { timeout: 2000 });
    assert.match(error.textContent ?? "", /academy offline/);
  });
});

describe("decorative language flags", () => {
  it("keeps the named control and hides its decorative flag", async () => {
    render(<LanguageProvider><LanguageSwitcher /></LanguageProvider>);
    const button = screen.getByRole("button", { name: /language|język|sprache/i });
    assert.ok(button.textContent?.match(/PL|EN|DE/));
    const flag = button.querySelector('svg[viewBox="0 0 24 16"]');
    assert.ok(flag);
    assert.equal(flag.getAttribute("aria-hidden"), "true");
  });
});


describe("QuickActions queue refresh boundary", () => {
  let releasePending: (() => void) | undefined;
  afterEach(async () => {
    await act(async () => { releasePending?.(); });
    releasePending = undefined;
  });
  async function mountQueue() {
    const posts: string[] = [];
    let paused = false;
    let hold = false;
    let resolveStatus: ((response: Response) => void) | undefined;
    let resolveTasks: ((response: Response) => void) | undefined;
    let postError = false;
    let statusError = false;
    let statusReads = 0;
    const status = () => ({ active: 0, pending: 0, limit: 5, paused });
    releasePending = () => {
      hold = false;
      resolveStatus?.(Response.json(status()));
      resolveTasks?.(Response.json([]));
    };
    globalThis.confirm = () => true;
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      if (init?.method === "POST") {
        posts.push(url);
        if (postError) return Response.json({ error: "action denied" }, { status: 400 });
        paused = !url.endsWith("/queue/resume");
        return Response.json({ message: "accepted" });
      }
      if (url.endsWith("/queue/status")) {
        statusReads += 1;
        if (statusError) return new Response("Unavailable", { status: 400 });
        if (hold) return new Promise<Response>((resolve) => { resolveStatus = resolve; });
        return Response.json(status());
      }
      if (url.endsWith("/tasks") && hold) {
        return new Promise<Response>((resolve) => { resolveTasks = resolve; });
      }
      return Response.json([]);
    };
    render(<QuickActions open onOpenChange={() => {}} />);
    const queue = renderHook(() => useQueueStatus());
    await waitFor(() => {
      assert.equal(queue.result.current.data?.paused, false);
      assert.equal(queue.result.current.refreshing, false);
    });
    return {
      posts, queue,
      holdStatus: () => { hold = true; },
      rejectPost: () => { postError = true; },
      rejectStatus: () => { statusError = true; },
      releaseStatus: async (stalePaused: boolean) => {
        assert.ok(resolveStatus);
        hold = false;
        await act(async () => {
          resolveStatus?.(Response.json({ ...status(), paused: stalePaused }));
          resolveTasks?.(Response.json([]));
        });
      },
      statusPending: () => resolveStatus !== undefined,
      tasksPending: () => resolveTasks !== undefined,
      statusReads: () => statusReads,
    };
  }

  const emergencyButton = () => screen.getByRole("button", { name: /Emergency stop|Awaryjne zatrzymanie|Notstopp/i });
  const pauseButton = () => screen.getByRole("button", { name: /Pause queue|Wstrzymaj kolejkę|Warteschlange pausieren/i });

  it("blocks stale toggles but allows emergency during delayed queue and task refresh", async () => {
    const h = await mountQueue();
    h.holdStatus();
    fireEvent.click(pauseButton());
    await waitFor(() => assert.equal(h.statusPending(), true));
    assert.equal(h.queue.result.current.loading, false);
    assert.equal(h.queue.result.current.refreshing, true);
    assert.equal(h.queue.result.current.data?.paused, false);
    fireEvent.click(pauseButton());
    assert.equal(h.posts.length, 1);
    assert.ok(screen.getByText(/Sending|Wysyłam|Senden/));
    assert.ok(h.posts[0].endsWith("/queue/pause"));
    assert.equal(h.tasksPending(), true);
    fireEvent.click(emergencyButton());
    await waitFor(() => assert.equal(h.posts.length, 2));
    assert.ok(h.posts[1].endsWith("/queue/emergency-stop"));
    assert.equal(h.queue.result.current.refreshing, true);
    const readsBeforeRelease = h.statusReads();
    await h.releaseStatus(false);
    await waitFor(() => assert.ok(h.statusReads() > readsBeforeRelease));
    await waitFor(() => assert.equal(h.queue.result.current.data?.paused, true));
    const resume = await screen.findByRole("button", { name: /Resume queue|Wznów kolejkę|Warteschlange fortsetzen/i });
    await waitFor(() => assert.equal(screen.queryByText(/Sending|Wysyłam|Senden/), null));
    fireEvent.click(resume);
    await waitFor(() => assert.equal(h.posts.length, 3));
    assert.ok(h.posts[2].endsWith("/queue/resume"));
    await waitFor(() => assert.equal(h.queue.result.current.refreshing, false));
  });

  it("does not toggle from a failed status read but still allows emergency", async () => {
    const h = await mountQueue();
    h.holdStatus();
    let refresh!: Promise<void>;
    act(() => { refresh = h.queue.result.current.refresh(); });
    fireEvent.click(emergencyButton());
    await waitFor(() => assert.equal(h.posts.length, 1));
    h.rejectStatus();
    await h.releaseStatus(false);
    await refresh;
    await waitFor(() => assert.equal(h.queue.result.current.error, "Request failed: 400"));
    fireEvent.click(pauseButton());
    assert.equal(h.posts.length, 1);
    assert.match(screen.getByText(/Request failed: 400/).textContent ?? "", /Request failed: 400/);
    fireEvent.click(emergencyButton());
    await waitFor(() => assert.equal(h.posts.length, 2));
    assert.ok(h.posts[1].endsWith("/queue/emergency-stop"));
  });

  it("blocks only toggle during a background refresh and preserves later POST errors", async () => {
    const h = await mountQueue();
    h.holdStatus();
    let refresh!: Promise<void>;
    act(() => { refresh = h.queue.result.current.refresh(); });
    assert.equal(h.queue.result.current.refreshing, true);
    fireEvent.click(pauseButton());
    assert.equal(h.posts.length, 0);
    fireEvent.click(emergencyButton());
    await waitFor(() => assert.equal(h.posts.length, 1));
    assert.ok(h.posts[0].endsWith("/queue/emergency-stop"));
    assert.equal(h.queue.result.current.refreshing, true);
    const readsBeforeRelease = h.statusReads();
    await h.releaseStatus(false);
    await refresh;
    await waitFor(() => assert.ok(h.statusReads() > readsBeforeRelease));
    await waitFor(() => assert.equal(h.queue.result.current.data?.paused, true));
    const resume = await screen.findByRole("button", { name: /Resume queue|Wznów kolejkę|Warteschlange fortsetzen/i });
    await waitFor(() => assert.equal(screen.queryByText(/Sending|Wysyłam|Senden/), null));
    h.rejectPost();
    fireEvent.click(resume);
    const error = await screen.findByText(/Request failed: 400/);
    assert.match(error.textContent ?? "", /Request failed: 400/);
    assert.equal(h.posts.length, 2);
    assert.ok(h.posts[1].endsWith("/queue/resume"));
    fireEvent.click(resume);
    await waitFor(() => assert.equal(h.posts.length, 3));
  });
});
