import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useCockpitModelActivation } from "../components/cockpit/hooks/use-cockpit-model-activation";
import { preferChatModelAliases } from "../lib/chat-model-options";
import { filterRuntimeBaseModels } from "../lib/runtime-model-filters";
import { syncTargetServerIfNeeded } from "../components/cockpit/cockpit-chat-send";

const models = ["vendor/model-one", "vendor/model-two:free"];
afterEach(cleanup);

describe("Connected OpenRouter models in chat", () => {
  it("retains every connected model and never activates one when the catalogue changes", async () => {
    const calls: string[] = [];
    const options = models.map((name) => ({ name, provider: "openrouter", runtime_id: "openrouter", is_adapter_artifact: false }));
    assert.deepEqual(preferChatModelAliases(filterRuntimeBaseModels(options), models[1]).map((model) => model.name), models);
    const input = {
      selectedLlmServer: "openrouter", selectedLlmModel: "", activeServer: "ollama",
      setSelectedLlmModel: () => {}, setActiveLlmRuntimeFn: async (provider: string, model: string) => { calls.push(`${provider}:${model}`); },
      setActiveLlmServerFn: async () => { throw new Error("local activation must not run"); },
      refreshActiveServer: () => {}, pushToast: () => {}, t: (key: string) => key,
    };
    const { rerender } = renderHook((props) => useCockpitModelActivation(props), { initialProps: input });
    rerender({ ...input, selectedLlmModel: models[1] });
    assert.deepEqual(calls, []);
  });

  it("activates either connected model exactly through the cloud route", async () => {
    const calls: string[] = [];
    const selections: string[] = [];
    const { result, rerender } = renderHook((selectedLlmModel: string) => useCockpitModelActivation({
      selectedLlmServer: "openrouter", selectedLlmModel, activeServer: "openrouter",
      setSelectedLlmModel: (model) => { selections.push(model); },
      setActiveLlmRuntimeFn: async (provider, model) => { calls.push(`${provider}:${model}`); },
      setActiveLlmServerFn: async () => { throw new Error("local activation must not run"); },
      refreshActiveServer: () => {}, pushToast: () => {}, t: (key) => key,
    }), { initialProps: "" });
    await act(async () => { assert.equal(await result.current.handleActivateModel(models[0]), true); });
    rerender(models[0]);
    await act(async () => { assert.equal(await result.current.handleActivateModel(models[1]), true); });
    assert.deepEqual(calls, models.map((model) => `openrouter:${model}`));
    assert.deepEqual(selections, models);
  });

  it("restores the previous selection when activating another connected model fails", async () => {
    const selections: string[] = [];
    const { result } = renderHook(() => useCockpitModelActivation({
      selectedLlmServer: "openrouter", selectedLlmModel: models[0], activeServer: "openrouter",
      setSelectedLlmModel: (model) => { selections.push(model); },
      setActiveLlmRuntimeFn: async () => { throw new Error("provider unavailable"); },
      setActiveLlmServerFn: async () => { throw new Error("must not fall back"); },
      refreshActiveServer: () => {}, pushToast: () => {}, t: (key) => key,
    }));
    await act(async () => { assert.equal(await result.current.handleActivateModel(models[1]), false); });
    assert.deepEqual(selections, [models[1], models[0]]);
  });

  it("switches between models on the same provider before sending a turn", async () => {
    const calls: string[] = [];
    const activated = await syncTargetServerIfNeeded({
      selectedLlmServer: "openrouter", selectedLlmModel: models[1],
      activeServerInfo: { active_server: "openrouter", active_model: models[0], runtime_id: `openrouter@${models[0]}`, config_hash: "model-one-config" },
      setActiveLlmRuntime: async (provider, model) => { calls.push(`${provider}:${model}`); return { active_server: provider, active_model: model, runtime_id: `openrouter@${model}`, config_hash: "model-two-config" }; },
      setActiveLlmServer: async () => { throw new Error("must not use local route"); },
      refreshActiveServer: () => {}, setMessage: () => {}, t: (key) => key,
    });
    assert.deepEqual(calls, [`openrouter:${models[1]}`]);
    assert.equal(activated && activated.active_model, models[1]);
  });
});
