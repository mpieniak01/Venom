import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { ChatComposer, type ChatMode } from "../components/cockpit/cockpit-chat-thread";
import { LanguageProvider } from "../lib/i18n";

const originalFetch = globalThis.fetch;
const LANGUAGE_STORAGE_KEY = "venom-language";

type CatalogState = {
  activeAdapterId: string | null;
  catalogActiveAdapterId?: string | null;
};

function TestHarness(params: {
  onSend: (payload: string) => Promise<boolean>;
  onActivateModelCall?: (value: string) => void;
}) {
  const [selectedLlmServer, setSelectedLlmServer] = useState("vllm");
  const [selectedLlmModel, setSelectedLlmModel] = useState("phi3-mini");
  const [chatMode, setChatMode] = useState<ChatMode>("normal");
  const [labMode, setLabMode] = useState(false);

  const llmServerOptions = [
    { value: "vllm", label: "VLLM" },
    { value: "ollama", label: "OLLAMA" },
  ];
  const llmModelOptions =
    selectedLlmServer === "ollama"
      ? [{ value: "gemma3:latest", label: "gemma3:latest" }]
      : [{ value: "phi3-mini", label: "phi3-mini" }];

  return (
    <LanguageProvider>
      <ChatComposer
        onSend={params.onSend}
        sending={false}
        chatMode={chatMode}
        setChatMode={setChatMode}
        labMode={labMode}
        setLabMode={setLabMode}
        selectedLlmServer={selectedLlmServer}
        llmServerOptions={llmServerOptions}
        setSelectedLlmServer={setSelectedLlmServer}
        selectedLlmModel={selectedLlmModel}
        llmModelOptions={llmModelOptions}
        llmModelMetadata={{
          "gemma3:latest": { canonical_model_id: "gemma-3-4b-it" },
          "phi3-mini": { canonical_model_id: "unsloth/phi-3-mini-4k-instruct" },
        }}
        setSelectedLlmModel={setSelectedLlmModel}
        onActivateModel={(value) => {
          params.onActivateModelCall?.(value);
          setSelectedLlmModel(value);
          return true;
        }}
        hasModels
        onOpenTuning={() => {}}
        tuningLabel="Tune"
        adapterDeploySupported
      />
    </LanguageProvider>
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

function installFetchMock(state: CatalogState) {
  let activationCount = 0;
  let deactivationCount = 0;
  let deactivationUsedExplicitNoDeploy = false;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes("/api/v1/system/llm-runtime/options")) {
      const adapterList = [
        {
          adapter_id: "adapter-gemma",
          adapter_path: "/tmp/adapter-gemma",
          base_model: "gemma-3-4b-it",
          canonical_base_model_id: "gemma-3-4b-it",
          is_active:
            (state.catalogActiveAdapterId ?? state.activeAdapterId) === "adapter-gemma",
          compatible_runtimes: ["ollama"],
        },
      ];
      return new Response(
        JSON.stringify({
          active: {
            runtime_id: "ollama",
            active_model: "gemma3:latest",
          },
          runtimes: [
            {
              runtime_id: "vllm",
              source_type: "local-runtime",
              configured: true,
              available: true,
              status: "running",
              active: false,
              supports_adapter_runtime_apply: true,
            },
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
                id: "phi3-mini",
                name: "phi3-mini",
                provider: "vllm",
                runtime_id: "vllm",
                source_type: "local-runtime",
                active: state.selectedRuntime === "vllm",
                canonical_model_id: "unsloth/phi-3-mini-4k-instruct",
              },
              {
                id: "gemma3:latest",
                name: "gemma3:latest",
                provider: "ollama",
                runtime_id: "ollama",
                source_type: "local-runtime",
                active: state.selectedRuntime === "ollama",
                canonical_model_id: "gemma-3-4b-it",
              },
            ],
          },
          adapter_catalog: {
            all_adapters: adapterList,
            by_runtime: {
              vllm: [],
              ollama: adapterList,
            },
            by_runtime_model: {
              vllm: {
                "unsloth/phi-3-mini-4k-instruct": [],
              },
              ollama: {
                "gemma-3-4b-it": adapterList,
              },
            },
          },
          selector_flow: ["server", "model", "adapter"],
        }),
        { status: 200 },
      );
    }

    if (url.includes("/api/v1/academy/adapters/audit")) {
      const search = new URL(url, window.location.origin).searchParams;
      const runtimeId = search.get("runtime_id");
      const modelId = search.get("model_id");
      const adapters =
        runtimeId === "ollama" && modelId === "gemma3:latest"
          ? [
              {
                adapter_id: "adapter-gemma",
                adapter_path: "/tmp/adapter-gemma",
                base_model: "gemma-3-4b-it",
                canonical_base_model: "gemma-3-4b-it",
                trusted_metadata: true,
                category: "compatible",
                reason_code: null,
                message: "Adapter metadata is consistent",
                is_active: state.activeAdapterId === "adapter-gemma",
                sources: [],
                manual_repair_hint: null,
              },
            ]
          : [];
      return new Response(
        JSON.stringify({
          count: adapters.length,
          adapters,
          summary: {
            compatible: adapters.length,
            blocked_unknown_base: 0,
            blocked_mismatch: 0,
          },
          runtime_id: runtimeId,
          model_id: modelId,
        }),
        { status: 200 },
      );
    }

    if (url.includes("/api/v1/academy/adapters/activate")) {
      assert.equal(init?.method, "POST");
      const payload = JSON.parse(String(init?.body || "{}")) as Record<string, string>;
      assert.equal(payload.runtime_id, "ollama");
      assert.equal(payload.model_id, "gemma-3-4b-it");
      assert.equal(payload.adapter_id, "adapter-gemma");
      state.activeAdapterId = "adapter-gemma";
      activationCount += 1;
      return new Response(
        JSON.stringify({
          success: true,
          message: "Adapter activated",
        }),
        { status: 200 },
      );
    }

    if (url.includes("/api/v1/academy/adapters/deactivate")) {
      state.activeAdapterId = null;
      deactivationCount += 1;
      const search = new URL(url, window.location.origin).searchParams;
      deactivationUsedExplicitNoDeploy =
        deactivationUsedExplicitNoDeploy ||
        search.get("deploy_to_chat_runtime") === "false";
      return new Response(
        JSON.stringify({
          success: true,
          message: "Adapter deactivated",
        }),
        { status: 200 },
      );
    }

    throw new Error(`Unexpected fetch URL: ${url}`);
  }) as typeof fetch;
  return {
    getActivationCount: () => activationCount,
    getDeactivationCount: () => deactivationCount,
    usedExplicitNoDeploy: () => deactivationUsedExplicitNoDeploy,
  };
}

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  window.localStorage.removeItem(LANGUAGE_STORAGE_KEY);
});

describe("ChatComposer adapter flow", () => {
  it("activates adapter for selected server and model before sending prompt", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    const sendCalls: string[] = [];
    const state: CatalogState = {
      activeAdapterId: null,
    };
    const fetchControl = installFetchMock(state);

    render(
      <TestHarness
        onSend={async (payload) => {
          sendCalls.push(payload);
          return true;
        }}
      />,
    );
    await flushEffects();

    fireEvent.click(screen.getByTestId("llm-server-select"));
    fireEvent.click(screen.getByText("OLLAMA"));
    await flushEffects();

    fireEvent.click(screen.getByTestId("llm-model-select"));
    fireEvent.click(screen.getByText("gemma3:latest"));
    await flushEffects();

    fireEvent.click(screen.getByTestId("chat-adapter-select"));
    const adapterOption = document.querySelector(
      '[data-value="adapter-gemma"]',
    ) as HTMLButtonElement | null;
    assert.ok(adapterOption);
    fireEvent.click(adapterOption);
    await flushEffects();

    assert.equal(fetchControl.getActivationCount(), 1);
    assert.match(
      String(screen.getByTestId("chat-adapter-select").textContent || ""),
      /adapter-gemma/i,
    );

    fireEvent.change(screen.getByTestId("cockpit-prompt-input"), {
      target: { value: "co to jest Venom" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("cockpit-send-button"));
    });

    assert.deepEqual(sendCalls, ["co to jest Venom"]);
  });

  it("switches to base profile with explicit no-adapter deploy path", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    const activatedModels: string[] = [];
    const state: CatalogState = {
      activeAdapterId: null,
    };
    const fetchControl = installFetchMock(state);

    render(
      <TestHarness
        onSend={async () => true}
        onActivateModelCall={(value) => activatedModels.push(value)}
      />,
    );
    await flushEffects();

    fireEvent.click(screen.getByTestId("llm-server-select"));
    fireEvent.click(screen.getByText("OLLAMA"));
    await flushEffects();

    fireEvent.click(screen.getByTestId("llm-model-select"));
    fireEvent.click(screen.getByText("gemma3:latest"));
    await flushEffects();

    fireEvent.click(screen.getByTestId("chat-adapter-select"));
    const adapterOption = document.querySelector(
      '[data-value="adapter-gemma"]',
    ) as HTMLButtonElement | null;
    assert.ok(adapterOption);
    fireEvent.click(adapterOption);
    await flushEffects();

    fireEvent.click(screen.getByTestId("chat-adapter-select"));
    const baseOption = document.querySelector(
      '[data-value="__base_model__"]',
    ) as HTMLButtonElement | null;
    assert.ok(baseOption);
    fireEvent.click(baseOption);
    await flushEffects();

    assert.equal(fetchControl.getDeactivationCount(), 1);
    assert.equal(fetchControl.usedExplicitNoDeploy(), true);
    assert.ok(activatedModels.includes("gemma3:latest"));
  });

  it("defaults selector to base model when runtime audit has no active adapter", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");
    const state: CatalogState = {
      activeAdapterId: null,
      catalogActiveAdapterId: "adapter-gemma",
    };
    installFetchMock(state);

    render(<TestHarness onSend={async () => true} />);
    await flushEffects();

    fireEvent.click(screen.getByTestId("llm-server-select"));
    fireEvent.click(screen.getByText("OLLAMA"));
    await flushEffects();

    fireEvent.click(screen.getByTestId("llm-model-select"));
    fireEvent.click(screen.getByText("gemma3:latest"));
    await flushEffects();

    assert.match(
      String(screen.getByTestId("chat-adapter-select").textContent || ""),
      /base model/i,
    );
  });
});
