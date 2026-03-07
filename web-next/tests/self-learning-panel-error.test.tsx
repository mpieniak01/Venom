import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ApiError } from "../lib/api-client";
import { resolveSelfLearningStartErrorMessage } from "../components/academy/self-learning-panel";
import { SelfLearningPanel } from "../components/academy/self-learning-panel";
import { LanguageProvider } from "../lib/i18n";
import { ToastProvider } from "../components/ui/toast";

const originalFetch = globalThis.fetch;

function renderPanel() {
  return render(
    <LanguageProvider>
      <ToastProvider>
        <SelfLearningPanel />
      </ToastProvider>
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

function selectBaseModel(modelId: string) {
  fireEvent.click(
    screen.getByRole("button", {
      name: /Training base model|Model bazowy treningu|Trainings-Basismodell/i,
    }),
  );
  fireEvent.click(screen.getByText(modelId));
}

function installFetchMock() {
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes("/api/v1/academy/self-learning/list")) {
      return new Response(JSON.stringify({ runs: [] }), { status: 200 });
    }

    if (url.includes("/api/v1/academy/self-learning/capabilities")) {
      return new Response(
        JSON.stringify({
          trainable_models: [
            {
              model_id: "gemma-3-4b-it",
              label: "gemma-3-4b-it",
              provider: "vllm",
              recommended: true,
              runtime_compatibility: { ollama: true, vllm: true },
              recommended_runtime: "ollama",
            },
          ],
          embedding_profiles: [],
          default_embedding_profile_id: null,
        }),
        { status: 200 },
      );
    }

    if (url.includes("/api/v1/system/llm-runtime/options")) {
      return new Response(
        JSON.stringify({
          active: {
            runtime_id: "ollama",
            active_server: "ollama",
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
            },
          ],
          model_catalog: {
            trainable_base_models: [
              {
                model_id: "gemma-3-4b-it",
                label: "gemma-3-4b-it",
                provider: "vllm",
                recommended: true,
                runtime_compatibility: { ollama: true, vllm: true },
                recommended_runtime: "ollama",
              },
            ],
          },
          model_audit: {
            issues_count: 0,
          },
        }),
        { status: 200 },
      );
    }

    if (url.includes("/api/v1/academy/self-learning/start")) {
      assert.equal(init?.method, "POST");
      return new Response(
        JSON.stringify({
          detail: {
            message: "Model does not expose compatible runtime targets.",
            reason_code: "MODEL_RUNTIME_TARGETS_UNAVAILABLE",
            requested_runtime_id: "ollama",
            requested_base_model: "gemma-3-4b-it",
          },
        }),
        { status: 400 },
      );
    }

    throw new Error(`Unexpected fetch URL: ${url}`);
  }) as typeof fetch;
}

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("resolveSelfLearningStartErrorMessage", () => {
  it("formats structured backend validation detail with requested context", () => {
    const error = new ApiError("Request failed: 400", 400, {
      detail: {
        message: "Model does not expose compatible runtime targets.",
        requested_runtime_id: "ollama",
        requested_base_model: "gemma-3-4b-it",
      },
    });

    assert.equal(
      resolveSelfLearningStartErrorMessage(error, "fallback"),
      "Model does not expose compatible runtime targets. (runtime=ollama, base_model=gemma-3-4b-it)",
    );
  });

  it("returns plain string detail from backend when present", () => {
    const error = new ApiError("Request failed: 400", 400, {
      detail: "Simple backend error",
    });

    assert.equal(resolveSelfLearningStartErrorMessage(error, "fallback"), "Simple backend error");
  });

  it("falls back to regular error message when backend detail is missing", () => {
    const error = new Error("Generic error");

    assert.equal(resolveSelfLearningStartErrorMessage(error, "fallback"), "Generic error");
  });

  it("uses fallback message when there is no usable error payload", () => {
    assert.equal(resolveSelfLearningStartErrorMessage(null, "fallback"), "fallback");
  });

  it("shows structured backend validation detail in panel toast for selected runtime and model", async () => {
    installFetchMock();

    renderPanel();
    await flushEffects();

    fireEvent.click(screen.getByText(/LLM Fine-tune/i));
    selectBaseModel("gemma-3-4b-it");
    fireEvent.click(screen.getByText(/README/i));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Start Self-Learning/i }));
    });
    await flushEffects();

    assert.ok(
      screen.getByText(
        "Model does not expose compatible runtime targets. (runtime=ollama, base_model=gemma-3-4b-it)",
      ),
    );
  });
});
