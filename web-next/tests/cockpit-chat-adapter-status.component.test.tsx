import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ChatComposer } from "../components/cockpit/cockpit-chat-thread";
import { LanguageProvider } from "../lib/i18n";

const originalFetch = globalThis.fetch;
const LANGUAGE_STORAGE_KEY = "venom-language";

type ComposerParams = {
  server?: string;
  selectedModel?: string;
  activeRuntimeModel?: string;
  adapterDeploySupported?: boolean;
  adapterDeployReason?: string;
  runtimeDisabled?: boolean;
  onActivateModel?: (model: string) => Promise<boolean>;
};

function ComposerHarness(params: ComposerParams) {
  const selectedServer = params?.server ?? "ollama";
  const selectedModel = params?.selectedModel ?? "gemma3:latest";
  const activeRuntimeModel = params?.activeRuntimeModel ?? "venom-adapter-training_1234";
  return (
    <LanguageProvider>
      <ChatComposer
        onSend={async () => true}
        sending={false}
        chatMode="normal"
        setChatMode={() => {}}
        labMode={false}
        setLabMode={() => {}}
        selectedLlmServer={selectedServer}
        llmServerOptions={[
          { value: "ollama", label: "OLLAMA", disabled: params.runtimeDisabled },
          { value: "onnx", label: "ONNX" },
        ]}
        setSelectedLlmServer={() => {}}
        selectedLlmModel={selectedModel}
        activeRuntimeModel={activeRuntimeModel}
        llmModelOptions={[
          { value: "__none__", label: "Not selected" },
          { value: "gemma3:latest", label: "gemma3:latest" },
        ]}
        llmModelMetadata={{
          "gemma3:latest": { canonical_model_id: "gemma-3-4b-it" },
        }}
        setSelectedLlmModel={() => {}}
        onActivateModel={params.onActivateModel}
        hasModels
        onOpenTuning={() => {}}
        tuningLabel="Tune"
        adapterDeploySupported={params?.adapterDeploySupported ?? true}
        adapterDeployReason={params.adapterDeployReason}
      />
    </LanguageProvider>
  );
}

function renderComposer(params: ComposerParams = {}) {
  return render(<ComposerHarness {...params} />);
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
  runtimeId?: "ollama" | "onnx";
}) {
  const runtimeId = params.runtimeId ?? "ollama";
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/v1/system/llm-runtime/options")) {
      return new Response(
        JSON.stringify({
          active: {
            runtime_id: runtimeId,
            active_model: "gemma3:latest",
          },
          runtimes: [
            {
              runtime_id: runtimeId,
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
                provider: runtimeId,
                runtime_id: runtimeId,
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
                compatible_runtimes: [runtimeId],
              },
            ],
            by_runtime: {
              [runtimeId]: [
                {
                  adapter_id: "adapter-gemma",
                  adapter_path: "/tmp/adapter-gemma",
                  base_model: "gemma-3-4b-it",
                  canonical_base_model_id: "gemma-3-4b-it",
                  is_active: true,
                  compatible_runtimes: [runtimeId],
                },
              ],
            },
            by_runtime_model: {
              [runtimeId]: {
                "gemma-3-4b-it": [
                  {
                    adapter_id: "adapter-gemma",
                    adapter_path: "/tmp/adapter-gemma",
                    base_model: "gemma-3-4b-it",
                    canonical_base_model_id: "gemma-3-4b-it",
                    is_active: true,
                    compatible_runtimes: [runtimeId],
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
          runtime_id: runtimeId,
          model_id: "gemma3:latest",
        }),
        { status: 200 },
      );
    }

    throw new Error(`Unexpected fetch URL: ${url}`);
  }) as typeof fetch;
}

afterEach(() => {
  mock.restoreAll();
  cleanup();
  globalThis.fetch = originalFetch;
  window.localStorage.removeItem(LANGUAGE_STORAGE_KEY);
});

describe("ChatComposer adapter status", () => {
  it("does not request Academy audit when deployment is unavailable", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({ auditCategory: "compatible", auditMessage: "unused" });
    const originalMock = globalThis.fetch;
    let auditCalls = 0;
    globalThis.fetch = (async (input, init) => {
      if (String(input).includes("/academy/adapters/audit")) auditCalls += 1;
      return originalMock(input, init);
    }) as typeof fetch;
    const errors = mock.method(console, "error", () => {});
    renderComposer({ adapterDeploySupported: false, adapterDeployReason: "Academy is disabled." });
    await flushEffects();
    assert.ok(screen.getByText("Academy is disabled."));
    assert.equal(auditCalls, 0);
    assert.equal(errors.mock.callCount(), 0);
  });

  it("shows expected Academy 503 as unavailable without a console error", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({ auditCategory: "compatible", auditMessage: "unused" });
    const originalMock = globalThis.fetch;
    globalThis.fetch = (async (input, init) => String(input).includes("/academy/adapters/audit")
      ? new Response(JSON.stringify({ detail: "Academy disabled" }), { status: 503 })
      : originalMock(input, init)) as typeof fetch;
    const errors = mock.method(console, "error", () => {});
    renderComposer();
    await waitFor(() => assert.ok(screen.getByText("Academy is unavailable.")), { timeout: 3000 });
    assert.equal(errors.mock.callCount(), 0);
  });

  it("keeps unexpected audit failures visible", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({ auditCategory: "compatible", auditMessage: "unused" });
    const originalMock = globalThis.fetch;
    globalThis.fetch = (async (input, init) => String(input).includes("/academy/adapters/audit")
      ? new Response(JSON.stringify({ detail: "Audit storage failed" }), { status: 500 })
      : originalMock(input, init)) as typeof fetch;
    const errors = mock.method(console, "error", () => {});
    renderComposer();
    await waitFor(() => assert.ok(screen.getByText(/Audit storage failed/)), { timeout: 3000 });
    assert.equal(errors.mock.callCount(), 1);
  });

  it("ignores an old audit response after adapter deployment becomes unavailable", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({ auditCategory: "compatible", auditMessage: "STALE AUDIT" });
    const originalMock = globalThis.fetch;
    let releaseAudit: (() => void) | undefined;
    const pendingAudit = new Promise<void>((resolve) => { releaseAudit = resolve; });
    let auditCalls = 0;
    globalThis.fetch = (async (input, init) => {
      if (String(input).includes("/academy/adapters/audit")) {
        auditCalls += 1;
        await pendingAudit;
      }
      return originalMock(input, init);
    }) as typeof fetch;
    const view = renderComposer();
    await waitFor(() => assert.equal(auditCalls, 1));
    view.rerender(<ComposerHarness adapterDeploySupported={false} adapterDeployReason="Academy is disabled." />);
    await act(async () => { releaseAudit?.(); await pendingAudit; });
    await flushEffects();
    assert.equal(screen.queryByText("STALE AUDIT"), null);
    assert.ok(screen.getByText("Academy is disabled."));
  });

  it("does not offer model activation for a disabled runtime", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({ auditCategory: "compatible", auditMessage: "unused" });
    const activate = mock.fn(async () => true);
    renderComposer({ runtimeDisabled: true, adapterDeploySupported: false, onActivateModel: activate });
    await flushEffects();
    const modelSelect = screen.getByTestId("llm-model-select") as HTMLButtonElement;
    assert.equal(modelSelect.disabled, true);
    fireEvent.click(modelSelect);
    assert.equal(screen.queryByTestId("llm-model-option-gemma3:latest"), null);
    fireEvent.click(screen.getByTestId("llm-server-select"));
    const disabledOption = screen.getByTestId("llm-server-option-ollama") as HTMLButtonElement;
    assert.equal(disabledOption.disabled, true);
    assert.equal(activate.mock.callCount(), 0);
  });

  it("shows active adapter as compatible for current runtime model", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "compatible",
      auditMessage: "Adapter metadata is consistent",
      runtimeId: "ollama",
    });

    renderComposer();
    await flushEffects();

    assert.ok(screen.getByText("Active runtime model:"));
    assert.ok(screen.getByText("venom-adapter-training_1234"));
    assert.ok(screen.getByText("Selected base model:"));
    assert.equal(screen.getAllByText("gemma3:latest").length >= 1, true);
    assert.ok(screen.getByText("Active adapter"));
    assert.equal(screen.getAllByText("adapter-gemma").length >= 1, true);
    assert.ok(
      screen.getByText("active adapter matches the current selection"),
    );
    assert.ok(screen.getByText("Adapter metadata is consistent"));
  });

  it("treats runtime-model mismatch as informational in cockpit adapter flow", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "blocked_mismatch",
      auditMessage: "Adapter base model does not match selected runtime model",
      runtimeId: "ollama",
    });

    renderComposer();
    await flushEffects();

    assert.equal(
      screen.queryByText("active adapter does not match the current runtime model"),
      null,
    );
    assert.ok(screen.getByText("Adapter base model does not match selected runtime model"));
  });

  it("does not show runtime-not-supported warning for ONNX when adapter apply capability is enabled", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "compatible",
      auditMessage: "Adapter metadata is consistent",
      runtimeId: "onnx",
    });

    renderComposer({ server: "onnx" });
    await flushEffects();

    assert.equal(
      screen.queryByText(/chat adapter deploy is not supported for runtime/i),
      null,
    );
  });

  it("shows runtime-not-supported warning when adapter apply capability is disabled", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "compatible",
      auditMessage: "Adapter metadata is consistent",
      runtimeId: "onnx",
    });

    renderComposer({ server: "onnx", adapterDeploySupported: false });
    await flushEffects();

    assert.ok(
      screen.getByText(/chat adapter deploy is not supported for runtime/i),
    );
  });

  it("shows runtime-model context in model selector when base model is not selected", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "compatible",
      auditMessage: "Adapter metadata is consistent",
      runtimeId: "onnx",
    });

    renderComposer({
      server: "onnx",
      selectedModel: "",
      activeRuntimeModel: "/runtime/onnx/venom-adapter-1234",
    });
    await flushEffects();

    assert.ok(
      screen.getByText(
        "Not selected · Active runtime model: /runtime/onnx/venom-adapter-1234",
      ),
    );
  });

  it("does not mark adapter as blocked when base model is not explicitly selected", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    installFetchMock({
      auditCategory: "blocked_mismatch",
      auditMessage: "Adapter base model does not match selected runtime model",
      runtimeId: "onnx",
    });

    renderComposer({
      server: "onnx",
      selectedModel: "",
      activeRuntimeModel: "/runtime/onnx/venom-adapter-1234",
    });
    await flushEffects();

    assert.equal(
      screen.queryByText(/does not match selected runtime model/i),
      null,
    );
  });
});
