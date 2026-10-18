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
const cacheKey = "trainable-models-cache";

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
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
    let postError = false;
    const status = () => ({ active: 0, pending: 0, limit: 5, paused });
    releasePending = () => {
      hold = false;
      resolveStatus?.(Response.json(status()));
    };
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      if (init?.method === "POST") {
        posts.push(url);
        return postError
          ? Response.json({ error: "pause denied" }, { status: 400 })
          : Response.json({ message: "accepted" });
      }
      if (url.endsWith("/queue/status")) {
        if (hold) return new Promise<Response>((resolve) => { resolveStatus = resolve; });
        return Response.json(status());
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
      releaseStatus: async (nextPaused: boolean) => {
        assert.ok(resolveStatus);
        paused = nextPaused;
        hold = false;
        await act(async () => { resolveStatus?.(Response.json(status())); });
      },
      statusPending: () => resolveStatus !== undefined,
    };
  }

  const pauseButton = () => screen.getByRole("button", { name: /Pause queue|Wstrzymaj kolejkę|Warteschlange pausieren/i });

  it("keeps the action busy through a delayed refresh then uses the new queue direction", async () => {
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
    await h.releaseStatus(true);
    const resume = await screen.findByRole("button", { name: /Resume queue|Wznów kolejkę|Warteschlange fortsetzen/i });
    fireEvent.click(resume);
    await waitFor(() => assert.equal(h.posts.length, 2));
    assert.ok(h.posts[1].endsWith("/queue/resume"));
    await waitFor(() => assert.equal(h.queue.result.current.refreshing, false));
  });

  it("ignores clicks during an existing refresh and still reports a later POST failure", async () => {
    const h = await mountQueue();
    h.holdStatus();
    let refresh!: Promise<void>;
    act(() => { refresh = h.queue.result.current.refresh(); });
    assert.equal(h.queue.result.current.refreshing, true);
    fireEvent.click(pauseButton());
    assert.deepEqual(h.posts, []);
    await h.releaseStatus(false);
    await refresh;
    h.rejectPost();
    fireEvent.click(pauseButton());
    const error = await screen.findByText(/Request failed: 400/);
    assert.match(error.textContent ?? "", /Request failed: 400/);
    assert.equal(h.posts.length, 1);
    fireEvent.click(pauseButton());
    await waitFor(() => assert.equal(h.posts.length, 2));
  });
});
