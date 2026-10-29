import "./component-test-setup";
import React from "react";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { RemoteProviderCard } from "../components/models/remote-provider-card";
import { useRemoteModels } from "../components/models/hooks/use-remote-models";
import { en } from "../lib/i18n/locales/en";
import { pl } from "../lib/i18n/locales/pl";
import { de } from "../lib/i18n/locales/de";

const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });
const t = (key: string) => key.split(".").reduce<unknown>((value, part) => (value as Record<string, unknown>)[part], en) as string;
const provider = { provider: "vast_ollama", status: "unavailable", enabled: true, configured: true, available: false, selected: true, last_check: null, error: null, latency_ms: null };

describe("Remote API operator controls", () => {
  it("keeps enabled, unavailable and selected states separate and explains VAST infrastructure", () => {
    const calls: [string, boolean?][] = [];
    render(<RemoteProviderCard provider={provider} pending={false} manage={async (...args) => { calls.push(args); }} connectVast={async () => {}} t={t} />);
    assert.ok(screen.getByText("API enabled"));
    assert.ok(screen.getByText("Unavailable"));
    assert.ok(screen.getByText("Selected for chat"));
    assert.ok(screen.getByText(/does not stop the rented instance/));
    assert.equal(screen.getByRole("link").getAttribute("href"), "/config?tab=integrations&integration=core%3Avast");
    fireEvent.click(screen.getByRole("button", { name: "Check connection" }));
    fireEvent.click(screen.getByRole("button", { name: "VAST · Ollama: Disable API" }));
    assert.deepEqual(calls, [["vast_ollama"], ["vast_ollama", false]]);
  });

  it("disables both controls while an operation is pending", () => {
    render(<RemoteProviderCard provider={{ ...provider, provider: "openrouter" }} pending={true} manage={async () => { throw new Error("must not run"); }} connectVast={async () => {}} t={t} />);
    for (const button of screen.getAllByRole("button")) assert.equal((button as HTMLButtonElement).disabled, true);
  });

  it("changes enablement without activating a model or running a generation", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    globalThis.fetch = async (input, init) => {
      const url = String(input); calls.push({ url, init });
      return Response.json(url.endsWith("/connectivity") ? { bindings: [] } : { providers: [provider] });
    };
    const { result } = renderHook(() => useRemoteModels());
    await waitFor(() => assert.equal(result.current.providersLoading, false));
    await act(async () => { await result.current.manageProvider("vast_ollama", false); });
    const posts = calls.filter((call) => call.init?.method === "POST");
    assert.equal(posts.length, 1);
    assert.equal(posts[0].url, "/api/v1/models/remote/providers/vast_ollama/enable");
    assert.deepEqual(JSON.parse(String(posts[0].init?.body)), { enabled: false });
    assert.equal(result.current.providerActions.vast_ollama, false);
  });

  it("reports a rejected connection check without changing displayed provider state", async () => {
    globalThis.fetch = async (input, init) => init?.method === "POST" ? new Response(null, { status: 503 }) : Response.json(String(input).endsWith("/connectivity") ? { bindings: [] } : { providers: [provider] });
    const { result } = renderHook(() => useRemoteModels());
    await waitFor(() => assert.equal(result.current.providersLoading, false));
    await act(async () => { await result.current.manageProvider("vast_ollama"); });
    assert.equal(result.current.providerActionError, "HTTP 503");
    assert.equal(result.current.providers[0].available, false);
    assert.equal(result.current.providerActions.vast_ollama, false);
  });

  it("attaches only a valid prepared plan and disconnects without a host-stop action", () => {
    const calls: (string | null)[] = [];
    render(<RemoteProviderCard provider={provider} pending={false} manage={async () => {}} connectVast={async (id) => { calls.push(id); }} t={t} />);
    const attach = screen.getByRole("button", { name: "Attach prepared API" }) as HTMLButtonElement;
    assert.equal(attach.disabled, true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "bad-id" } });
    assert.equal(attach.disabled, true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "a".repeat(32) } });
    fireEvent.click(attach);
    fireEvent.click(screen.getByRole("button", { name: "Disconnect API" }));
    assert.deepEqual(calls, ["a".repeat(32), null]);
  });

  it("uses existing attach/detach endpoints and never stops the VAST instance", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    globalThis.fetch = async (input, init) => {
      const url = String(input); calls.push({ url, init });
      return Response.json(url.endsWith("/connectivity") ? { bindings: [] } : { providers: [provider] });
    };
    const { result } = renderHook(() => useRemoteModels());
    await waitFor(() => assert.equal(result.current.providersLoading, false));
    await act(async () => { await result.current.connectVast("a".repeat(32)); });
    await act(async () => { await result.current.connectVast(null); });
    const posts = calls.filter((call) => call.init?.method === "POST");
    assert.deepEqual(posts.map((call) => call.url), ["/api/v1/system/vast-chat/attach", "/api/v1/system/vast-chat/detach"]);
    assert.deepEqual(JSON.parse(String(posts[0].init?.body)), { plan_id: "a".repeat(32) });
  });

  it("has matching operator-control translations in all supported languages", () => {
    const keys = Object.keys(en.models.sections.remote.controls).sort();
    for (const locale of [pl, de]) assert.deepEqual(Object.keys(locale.models.sections.remote.controls).sort(), keys);
  });
});
