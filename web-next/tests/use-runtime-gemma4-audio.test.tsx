import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { LanguageProvider } from "../lib/i18n";
import { ToastProvider } from "../components/ui/toast";
import { useRuntime } from "../components/models/hooks/use-runtime";
import { getRuntimeForProvider } from "../components/models/models-helpers";

afterEach(() => cleanup());

const originalFetch = globalThis.fetch;

function makeFetchPayloads() {
  return {
    models: {
      success: true,
      models: [],
      count: 0,
      providers: {
        gemma4_audio: [
          {
            name: "google/gemma-4-E2B-it",
            provider: "gemma4_audio",
            source: "local-runtime",
            installed: true,
            active: true,
          },
        ],
      },
      active: {
        provider: "gemma4_audio",
        model: "google/gemma-4-E2B-it",
        endpoint: "http://localhost:8014/v1",
        status: "ready",
      },
    },
    runtimeOptions: {
      status: "success",
      active: {
        runtime_id: "gemma4_audio",
        active_server: "gemma4_audio",
        active_model: "google/gemma-4-E2B-it",
        active_endpoint: "http://localhost:8014/v1",
        config_hash: "cfg123",
        source_type: "local-runtime",
      },
      runtimes: [
        {
          runtime_id: "gemma4_audio",
          source_type: "local-runtime",
          configured: true,
          available: true,
          status: "ready",
          active: true,
          models: [
            {
              name: "google/gemma-4-E2B-it",
              provider: "gemma4_audio",
              source_type: "local-runtime",
              chat_compatible: true,
            },
          ],
        },
      ],
      selector_flow: ["server", "model"],
    },
    activeServer: {
      status: "success",
      active_server: "gemma4_audio",
      active_endpoint: "http://localhost:8014/v1",
      active_model: "google/gemma-4-E2B-it",
      config_hash: "cfg123",
      runtime_id: "gemma4_audio",
      source_type: "local-runtime",
    },
    modelOperations: {
      success: true,
      operations: [],
      count: 0,
    },
  };
}

beforeEach(() => {
  const payloads = makeFetchPayloads();
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.includes("/api/v1/models/operations")) {
      return new Response(JSON.stringify(payloads.modelOperations), { status: 200 });
    }
    if (url.endsWith("/api/v1/models")) {
      return new Response(JSON.stringify(payloads.models), { status: 200 });
    }
    if (url.endsWith("/api/v1/system/llm-runtime/options")) {
      return new Response(JSON.stringify(payloads.runtimeOptions), { status: 200 });
    }
    if (url.endsWith("/api/v1/system/llm-servers/active")) {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body ?? "{}")) as Record<string, string>;
        assert.equal(body.server_name, "multi_runtime");
        assert.equal(body.model, "google/gemma-4-E2B-it");
        return new Response(JSON.stringify(payloads.activeServer), { status: 200 });
      }
      return new Response(JSON.stringify(payloads.activeServer), { status: 200 });
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  }) as typeof fetch;
  (globalThis as typeof globalThis & { __requests?: Array<{ url: string; init?: RequestInit }> }).__requests =
    requests;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function RuntimeHarness() {
  const runtime = useRuntime();
  return (
    <div>
      <div data-testid="selected-server">{runtime.selectedServer ?? ""}</div>
      <div data-testid="selected-model">{runtime.selectedModel ?? ""}</div>
      <button
        type="button"
        data-testid="apply-runtime"
        onClick={() =>
          runtime.activateRuntimeSelection("gemma4_audio", "google/gemma-4-E2B-it")
        }
      >
        Apply
      </button>
    </div>
  );
}

describe("useRuntime gemma4_audio activation", () => {
  it("canonicalizes gemma4_audio to multi_runtime and does not switch via /models/switch", async () => {
    render(
      <LanguageProvider>
        <ToastProvider>
          <RuntimeHarness />
        </ToastProvider>
      </LanguageProvider>,
    );

    await screen.findByText("gemma4_audio");
    await screen.findByText("google/gemma-4-E2B-it");

    await act(async () => {
      fireEvent.click(screen.getByTestId("apply-runtime"));
    });

    const requests = (globalThis as typeof globalThis & {
      __requests?: Array<{ url: string; init?: RequestInit }>;
    }).__requests ?? [];
    const postBodies = requests
      .filter((request) => request.init?.method === "POST")
      .map((request) => request.url);

    assert.ok(
      postBodies.some((url) => url.endsWith("/api/v1/system/llm-servers/active")),
    );
    assert.equal(
      postBodies.some((url) => url.endsWith("/api/v1/models/switch")),
      false,
    );
  });

  it("routes gemma4_audio provider to multi_runtime for model activation", () => {
    assert.equal(getRuntimeForProvider("gemma4_audio"), "multi_runtime");
    assert.equal(getRuntimeForProvider("multi_runtime"), "multi_runtime");
    assert.equal(getRuntimeForProvider("GeMmA4_AuDiO"), "multi_runtime");
  });
});
