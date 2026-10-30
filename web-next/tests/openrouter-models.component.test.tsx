import "./component-test-setup";
import React from "react";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { OpenRouterModelsSection } from "../components/models/openrouter-models-section";
import { useOpenRouterModels, type OpenRouterModel } from "../components/models/hooks/use-openrouter-models";
import { en } from "../lib/i18n/locales/en";
import { pl } from "../lib/i18n/locales/pl";
import { de } from "../lib/i18n/locales/de";

const t = (key: string) => key.split(".").reduce<unknown>((value, part) => (value as Record<string, unknown>)[part], en) as string;
const model = (id: string, extra: Partial<OpenRouterModel> = {}): OpenRouterModel => ({ id, name: id, description: "Text model", context_length: 8192, input_price_per_million: "0", output_price_per_million: null, supports_tools: true, connected: false, ...extra });
const results = (models: OpenRouterModel[], offset = 0) => ({ models, total: 26, count: models.length, offset, limit: 25, next_offset: offset === 0 ? 25 : null, fetched_at: "2026-10-29T00:00:00Z", source: "live" });
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });

describe("OpenRouter model connections", () => {
  it("connects multiple models and disconnects one without activating or affecting the other", async () => {
    let connected = [model("vendor/a", { connected: true, available: true })];
    const calls: string[] = []; let changed = 0;
    globalThis.fetch = async (input, init) => {
      const path = String(input); calls.push(path);
      if (init?.method === "POST") {
        const id = JSON.parse(String(init.body)).model_id;
        connected = path.endsWith("/disconnect") ? connected.filter(row => row.id !== id) : [...connected, model(id, { connected: true, available: true })];
      }
      return Response.json({ models: connected, count: connected.length });
    };
    const { result } = renderHook(() => useOpenRouterModels(async () => { changed++; }));
    await waitFor(() => assert.equal(result.current.connectedLoading, false));
    await act(async () => { await result.current.manage("vendor/b", true); });
    assert.deepEqual(result.current.connected.map(row => row.id), ["vendor/a", "vendor/b"]);
    await act(async () => { await result.current.manage("vendor/a", false); });
    assert.deepEqual(result.current.connected.map(row => row.id), ["vendor/b"]);
    assert.equal(changed, 2);
    assert.ok(calls.every(path => path.startsWith("/api/v1/openrouter/models/")));
  });

  it("searches only after submission and shows unknown prices distinctly from zero", async () => {
    const calls: string[] = [];
    globalThis.fetch = async input => { const path = String(input); calls.push(path); return Response.json(path.includes("/search?") ? results([model("vendor/found")]) : { models: [], count: 0 }); };
    render(<OpenRouterModelsSection t={t} />);
    await waitFor(() => assert.ok(screen.getByText(/No models connected/)));
    fireEvent.change(screen.getByLabelText("Model name or ID"), { target: { value: "found" } });
    assert.equal(calls.filter(path => path.includes("/search?")).length, 0);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Connect model: vendor/found" })));
    assert.ok(screen.getByText("Output USD / 1M tokens: Unknown"));
    assert.ok(screen.getByText("Input USD / 1M tokens: 0"));
    assert.ok(calls.some(path => path.includes("q=found") && path.includes("purpose=chat")));
  });

  it("paginates without changing the submitted criteria", async () => {
    const calls: string[] = [];
    globalThis.fetch = async input => { const path = String(input); calls.push(path); return Response.json(path.includes("/search?") ? results([model("vendor/next")], Number(new URL(path, "http://localhost").searchParams.get("offset"))) : { models: [] }); };
    const { result } = renderHook(() => useOpenRouterModels());
    await waitFor(() => assert.equal(result.current.connectedLoading, false));
    act(() => { result.current.setQuery("code"); result.current.setPurpose("tasks"); });
    await act(async () => { await result.current.search(); });
    await act(async () => { await result.current.search(25); });
    assert.equal(result.current.results?.offset, 25);
    assert.ok(calls.at(-1)?.includes("purpose=tasks"));
    assert.ok(calls.at(-1)?.includes("q=code"));
  });

  it("ignores a late result after criteria change and newer search", async () => {
    let resolveOld: (response: Response) => void = () => {};
    globalThis.fetch = async input => {
      const path = String(input);
      if (!path.includes("/search?")) return Response.json({ models: [] });
      if (path.includes("q=old")) return new Promise<Response>(resolve => { resolveOld = resolve; });
      return Response.json(results([model("vendor/new")]));
    };
    const { result } = renderHook(() => useOpenRouterModels());
    await waitFor(() => assert.equal(result.current.connectedLoading, false));
    act(() => result.current.setQuery("old"));
    let old: Promise<void>;
    act(() => { old = result.current.search(); });
    act(() => result.current.setQuery("new"));
    await act(async () => { await result.current.search(); });
    await act(async () => { resolveOld(Response.json(results([model("vendor/old")]))); await old; });
    assert.equal(result.current.results?.models[0].id, "vendor/new");
  });

  it("keeps connected models on rejection and releases pending state", async () => {
    let changed = 0;
    globalThis.fetch = async (_input, init) => init?.method === "POST" ? new Response(null, { status: 503 }) : Response.json({ models: [model("vendor/a", { connected: true })] });
    const { result } = renderHook(() => useOpenRouterModels(async () => { changed++; }));
    await waitFor(() => assert.equal(result.current.connectedLoading, false));
    await act(async () => { await result.current.manage("vendor/a", false); });
    assert.equal(result.current.connected[0].id, "vendor/a");
    assert.equal(result.current.pending["vendor/a"], false);
    assert.equal(result.current.error, "HTTP 503");
    assert.equal(changed, 0);
  });

  it("deduplicates double connection clicks before state renders", async () => {
    let finish: (response: Response) => void = () => {}; let posts = 0;
    globalThis.fetch = async (_input, init) => {
      if (init?.method === "POST") { posts++; return new Promise<Response>(resolve => { finish = resolve; }); }
      return Response.json({ models: [] });
    };
    const { result } = renderHook(() => useOpenRouterModels());
    await waitFor(() => assert.equal(result.current.connectedLoading, false));
    let first: Promise<void>;
    act(() => { first = result.current.manage("vendor/a", true); void result.current.manage("vendor/a", true); });
    assert.equal(posts, 1);
    await act(async () => { finish(Response.json({ status: "success" })); await first; });
  });

  it("refreshes an unavailable connected model through connect without disconnecting", async () => {
    const posts: string[] = []; let available = false;
    globalThis.fetch = async (input, init) => {
      if (init?.method === "POST") { posts.push(String(input)); available = true; }
      return Response.json({ models: [model("vendor/a", { connected: true, available })] });
    };
    render(<OpenRouterModelsSection t={t} />);
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Refresh model: vendor/a" })));
    fireEvent.click(screen.getByRole("button", { name: "Refresh model: vendor/a" }));
    await waitFor(() => assert.ok(screen.queryByRole("button", { name: "Refresh model: vendor/a" }) === null));
    assert.deepEqual(posts, ["/api/v1/openrouter/models/connect"]);
  });
});


for (const [language, locale] of Object.entries({ pl, en, de })) {
  it(`localizes category labels and preserves API identifiers in ${language}`, async () => {
    const calls: string[] = [];
    globalThis.fetch = async input => {
      const path = String(input); calls.push(path);
      return Response.json(path.includes("/search?") ? results([]) : { models: [] });
    };
    const translate = (key: string) => key.split(".").reduce<unknown>((value, part) => (value as Record<string, unknown>)[part], locale) as string;
    render(<OpenRouterModelsSection t={translate} />);
    assert.ok(screen.getByRole("checkbox", { name: locale.models.openrouter.freeOnly }));
    const category = screen.getByLabelText(locale.models.openrouter.category) as HTMLSelectElement;
    const option = Array.from(category.options).find(item => item.text === locale.models.openrouter.categories.programming);
    assert.equal(option?.value, "programming");
    fireEvent.change(category, { target: { value: "programming" } });
    fireEvent.click(screen.getByRole("button", { name: locale.models.openrouter.search }));
    await waitFor(() => assert.ok(calls.some(path => path.includes("category=programming"))));
  });
}


it("shows the effective budget output cap for a connected model", async () => {
  globalThis.fetch = async () => Response.json({ models: [model("vendor/a", { connected: true, available: true, max_output_tokens: 256 })] });
  render(<OpenRouterModelsSection t={t} />);
  await waitFor(() => assert.ok(screen.getByText("Maximum output (tokens, MVP budget cap): 256")));
});


it("submits the free-only checkbox explicitly and clears stale results on toggle", async () => {
  const searches: URLSearchParams[] = [];
  globalThis.fetch = async input => {
    const path = String(input);
    if (!path.includes("/search?")) return Response.json({ models: [] });
    const params = new URL(path, "http://localhost").searchParams;
    searches.push(params);
    return Response.json(results([model("vendor/result")]));
  };
  render(<OpenRouterModelsSection t={t} />);
  await waitFor(() => assert.ok(screen.getByText(/No models connected/)));
  const checkbox = screen.getByRole("checkbox", { name: "Free models only" }) as HTMLInputElement;
  assert.equal(checkbox.checked, false);
  fireEvent.click(checkbox);
  assert.equal(searches.length, 0);
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => assert.ok(screen.getByRole("button", { name: "Connect model: vendor/result" })));
  assert.equal(searches[0].get("free_only"), "true");
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => assert.equal(searches.length, 2));
  assert.equal(searches[1].get("free_only"), "true");
  assert.equal(searches[1].get("offset"), "25");
  fireEvent.click(checkbox);
  assert.equal(screen.queryByRole("button", { name: "Connect model: vendor/result" }), null);
  assert.equal(searches.length, 2);
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => assert.equal(searches.length, 3));
  assert.equal(searches[2].has("free_only"), false);
  assert.equal(searches[2].get("offset"), "0");
});

it("ignores an unfiltered response arriving after the free-only filter changes", async () => {
  let finish: (response: Response) => void = () => {};
  globalThis.fetch = async input => String(input).includes("/search?")
    ? new Promise<Response>(resolve => { finish = resolve; })
    : Response.json({ models: [] });
  const { result } = renderHook(() => useOpenRouterModels());
  await waitFor(() => assert.equal(result.current.connectedLoading, false));
  let pending: Promise<void>;
  act(() => { pending = result.current.search(); });
  act(() => result.current.setFreeOnly(true));
  await act(async () => { finish(Response.json(results([model("vendor/paid")]))); await pending; });
  assert.equal(result.current.results, null);
  assert.equal(result.current.loading, false);
});
