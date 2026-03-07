import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, render, screen } from "@testing-library/react";

import { ChatComposer } from "../components/cockpit/cockpit-chat-thread";
import { LanguageProvider } from "../lib/i18n";

const originalFetch = globalThis.fetch;
const LANGUAGE_STORAGE_KEY = "venom-language";

function renderComposer() {
  return render(
    <LanguageProvider>
      <ChatComposer
        onSend={async () => true}
        sending={false}
        chatMode="normal"
        setChatMode={() => {}}
        labMode={false}
        setLabMode={() => {}}
        selectedLlmServer="ollama"
        llmServerOptions={[{ value: "ollama", label: "OLLAMA" }]}
        setSelectedLlmServer={() => {}}
        selectedLlmModel="gemma3:latest"
        llmModelOptions={[{ value: "gemma3:latest", label: "gemma3:latest" }]}
        llmModelMetadata={{
          "gemma3:latest": { canonical_model_id: "gemma-3-4b-it" },
        }}
        setSelectedLlmModel={() => {}}
        hasModels
        onOpenTuning={() => {}}
        tuningLabel="Tune"
        adapterDeploySupported
      />
    </LanguageProvider>,
  );
}

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
  });
  await act(async () => {
    await Promise.resolve();
  });
}

function installFetchMock(params: {
  auditCategory: "compatible" | "blocked_mismatch";
  auditMessage: string;
}) {
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/v1/system/llm-runtime/options")) {
      return new Response(
        JSON.stringify({
          active: {
            runtime_id: "ollama",
            active_model: "gemma3:latest",
          },
          runtimes: [
            {
              runtime_id: "ollama",
              source_type: "local-runtime",
              configured: true,
              available: true,
              status: "running",
              active: true,
              supports_adapter_runtime_apply: true,
            },
          ],
          model_catalog: {
            chat_models: [
              {
                id: "gemma3:latest",
                name: "gemma3:latest",
                provider: "ollama",
                runtime_id: "ollama",
                source_type: "local-runtime",
                active: true,
                canonical_model_id: "gemma-3-4b-it",
              },
            ],
          },
          adapter_catalog: {
            all_adapters: [
              {
                adapter_id: "adapter-gemma",
                adapter_path: "/tmp/adapter-gemma",
                base_model: "gemma-3-4b-it",
                canonical_base_model_id: "gemma-3-4b-it",
                is_active: true,
                compatible_runtimes: ["ollama"],
              },
            ],
            by_runtime: {
              ollama: [
                {
                  adapter_id: "adapter-gemma",
                  adapter_path: "/tmp/adapter-gemma",
                  base_model: "gemma-3-4b-it",
                  canonical_base_model_id: "gemma-3-4b-it",
                  is_active: true,
                  compatible_runtimes: ["ollama"],
                },
              ],
            },
            by_runtime_model: {
              ollama: {
                "gemma-3-4b-it": [
                  {
                    adapter_id: "adapter-gemma",
                    adapter_path: "/tmp/adapter-gemma",
                    base_model: "gemma-3-4b-it",
                    canonical_base_model_id: "gemma-3-4b-it",
                    is_active: true,
                    compatible_runtimes: ["ollama"],
                  },
                ],
              },
            },
          },
          selector_flow: ["server", "model", "adapter"],
        }),
        { status: 200 },
      );
    }

    if (url.includes("/api/v1/academy/adapters/audit")) {
      return new Response(
        JSON.stringify({
          count: 1,
          adapters: [
            {
              adapter_id: "adapter-gemma",
              adapter_path: "/tmp/adapter-gemma",
              base_model: "gemma-3-4b-it",
              canonical_base_model: "gemma-3-4b-it",
              trusted_metadata: true,
              category: params.auditCategory,
              reason_code:
                params.auditCategory === "compatible"
                  ? null
                  : "ADAPTER_BASE_MODEL_MISMATCH",
              message: params.auditMessage,
              is_active: true,
              sources: [],
              manual_repair_hint: null,
            },
          ],
          summary: {
            compatible: params.auditCategory === "compatible" ? 1 : 0,
            blocked_unknown_base: 0,
            blocked_mismatch: params.auditCategory === "blocked_mismatch" ? 1 : 0,
          },
          runtime_id: "ollama",
          model_id: "gemma3:latest",
        }),
        { status: 200 },
      );
    }

    throw new Error(`Unexpected fetch URL: ${url}`);
  }) as typeof fetch;
}

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  window.localStorage.removeItem(LANGUAGE_STORAGE_KEY);
});

describe("ChatComposer adapter status", () => {
  it("shows active adapter as compatible for current runtime model", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "compatible",
      auditMessage: "Adapter metadata is consistent",
    });

    renderComposer();
    await flushEffects();

    assert.ok(screen.getByText("Active adapter"));
    assert.equal(screen.getAllByText("adapter-gemma").length >= 1, true);
    assert.ok(
      screen.getByText("active adapter matches the current selection"),
    );
    assert.ok(screen.getByText("Adapter metadata is consistent"));
  });

  it("shows active adapter as blocked when runtime model mismatches", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "blocked_mismatch",
      auditMessage: "Adapter base model does not match selected runtime model",
    });

    renderComposer();
    await flushEffects();

    assert.ok(
      screen.getByText("active adapter does not match the current runtime model"),
    );
    assert.ok(
      screen.getByText(
        "Switch runtime model to one compatible with the adapter base or disable the adapter before continuing.",
      ),
    );
  });
});
