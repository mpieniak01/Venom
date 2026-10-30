import "./component-test-setup";
import React from "react";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { LanguageProvider } from "../lib/i18n";
import { ToastProvider } from "../components/ui/toast";
import { useRuntime } from "../components/models/hooks/use-runtime";

const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });
function Wrapper({ children }: { children: React.ReactNode }) { return <LanguageProvider><ToastProvider>{children}</ToastProvider></LanguageProvider>; }

describe("Explicit external catalogue model activation", () => {
  for (const server of ["vast_ollama", "openrouter"]) {
    for (const cached of [false, true]) {
      it(`activates the exact selected ${server} model with cached catalogue=${cached}`, async () => {
        const posts: { url: string; body: Record<string, string> }[] = [];
        globalThis.fetch = async (input, init) => {
          const url = String(input);
          if (init?.method === "POST") posts.push({ url, body: JSON.parse(String(init.body)) });
          if (url.endsWith("/api/v1/models")) return Response.json({ models: [], providers: {}, active: { provider: server, model: "old-model" } });
          if (url.endsWith("/api/v1/models/operations")) return Response.json({ operations: [] });
          if (url.endsWith("/api/v1/system/llm-runtime/options")) return Response.json({ runtimes: cached ? [{ runtime_id: server, models: [{ name: "old-model", chat_compatible: true }], available: true }] : [], active: { runtime_id: server } });
          return Response.json({ status: "success", active_server: server, active_model: "old-model", active_endpoint: "https://fixture.invalid", config_hash: "fixture" });
        };
        const { result } = renderHook(() => useRuntime(), { wrapper: Wrapper });
        await act(async () => { await result.current.activeServer.refresh(); });
        await act(async () => { await result.current.activateRuntimeSelection(server, "chosen-model"); });
        assert.equal(posts.length, 1);
        assert.equal(posts[0].url, server === "openrouter" ? "/api/v1/system/llm-runtime/active" : "/api/v1/system/llm-servers/active");
        assert.equal(posts[0].body.model, "chosen-model");
        assert.equal(posts[0].body[server === "openrouter" ? "provider" : "server_name"], server);
      });
    }
  }
});
