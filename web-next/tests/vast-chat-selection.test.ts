import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isCockpitRuntimeDisabled,
  normalizeRuntimeId,
  resolveCockpitActiveRuntimeInfo,
  resolveCockpitSelectedRuntimeId,
} from "../lib/cockpit-runtime-selection";
import { canonicalRuntimeId } from "../lib/runtime-id";
import { resolveEffectiveChatModelSelection, syncTargetServerIfNeeded } from "../components/cockpit/cockpit-chat-send";
import { useCockpitModelActivation } from "../components/cockpit/hooks/use-cockpit-model-activation";
import { chatModelLabel } from "../lib/chat-model-options";
import type { LlmRuntimeTargetOption } from "../lib/types";

const remote: LlmRuntimeTargetOption = {
  runtime_id: "vast_ollama", label: "Ollama · Vast", source_type: "remote",
  configured: true, available: true, status: "running", active: true,
  models: [{id: "remote-model", name: "gemma4:latest", runtime_id: "vast_ollama", provider: "ollama", source_type: "remote", active: true}],
  adapter_deploy_supported: false,
};

describe("Vast chat runtime selection", () => {
  it("keeps remote identity distinct from a local Ollama with the same model", () => {
    const id = "ollama@vast:plan:instance:generation";
    assert.equal(normalizeRuntimeId(id), "vast_ollama");
    assert.equal(canonicalRuntimeId(id), "vast_ollama");
    assert.equal(normalizeRuntimeId("ollama@http://localhost:11434"), "ollama");
    const active = resolveCockpitActiveRuntimeInfo(
      {active: {runtime_id: "vast_ollama", active_model: "gemma4:latest"}, runtimes: [remote]},
      {active_server: "vast_ollama", active_model: "gemma4:latest", runtime_id: id},
    );
    assert.equal(active?.runtime_id, id);
    assert.equal(active?.active_server, "vast_ollama");
    assert.equal(resolveCockpitSelectedRuntimeId("", null, active), "vast_ollama");
  });

  it("disables remote selection without a host, tunnel, API or installed models", () => {
    assert.equal(isCockpitRuntimeDisabled(remote), false);
    assert.equal(isCockpitRuntimeDisabled({...remote, available: false, status: "offline"}), true);
    assert.equal(isCockpitRuntimeDisabled({...remote, models: []}), true);
    assert.equal(isCockpitRuntimeDisabled({...remote, models: undefined}), true);
    assert.equal(isCockpitRuntimeDisabled({...remote, configured: false}), true);
  });

  it("does not use the active local model as a remote catalog fallback", () => {
    assert.equal(resolveEffectiveChatModelSelection("", "local-only", "vast_ollama", "ollama"), "");
    assert.equal(resolveEffectiveChatModelSelection("", "remote-only", "ollama", "vast_ollama"), "");
    assert.equal(resolveEffectiveChatModelSelection("chosen", "local-only", "vast_ollama", "ollama"), "chosen");
  });

  it("uses the returned target identity for the first turn after switching", async () => {
    const response = {
      active_server: "vast_ollama", active_model: "gemma4:e4b", active_endpoint: "http://127.0.0.1:23456/v1",
      runtime_id: "ollama@vast:plan:instance:new", config_hash: "remote-config",
    };
    const calls: string[] = [];
    const result = await syncTargetServerIfNeeded({
      selectedLlmServer: "vast_ollama", selectedLlmModel: "gemma4:e4b",
      activeServerInfo: {active_server: "ollama", runtime_id: "ollama@local", config_hash: "local-config"},
      setActiveLlmRuntime: async () => {throw new Error("remote target must not activate cloud provider");},
      setActiveLlmServer: async (server, model) => {calls.push(server + "/" + model); return response;},
      refreshActiveServer: () => {}, setMessage: () => {}, t: (key) => key,
    });
    assert.deepEqual(result, response);
    assert.deepEqual(calls, ["vast_ollama/gemma4:e4b"]);
  });

  it("stops the send after failed attachment activation instead of falling back locally", async () => {
    const result = await syncTargetServerIfNeeded({
      selectedLlmServer: "vast_ollama", selectedLlmModel: "gemma4:e4b",
      activeServerInfo: {active_server: "ollama", runtime_id: "ollama@local"},
      setActiveLlmRuntime: async () => ({}), setActiveLlmServer: async () => {throw new Error("unavailable");},
      refreshActiveServer: () => {}, setMessage: () => {}, t: (key) => key,
    });
    assert.equal(result, false);
  });
});


it("rejects persisted or fallback unverified Gemma latest before remote activation", async () => {
  const calls: string[] = [];
  const messages: Array<string | null> = [];
  const active = {active_server:"vast_ollama",active_model:"gemma4:latest",runtime_id:"ollama@vast:plan:instance"};
  assert.equal(resolveEffectiveChatModelSelection("gemma4:latest","gemma4:latest","vast_ollama","vast_ollama"), "");
  assert.equal(resolveEffectiveChatModelSelection("","gemma4:latest","vast_ollama","vast_ollama"), "");
  for (const selected of ["gemma4:latest",""]) {
    const result = await syncTargetServerIfNeeded({
      selectedLlmServer:"vast_ollama", selectedLlmModel:selected, activeServerInfo:active,
      setActiveLlmRuntime:async()=>{calls.push("cloud");return {};},
      setActiveLlmServer:async()=>{calls.push("vast");return {};},
      refreshActiveServer:()=>{calls.push("refresh");}, setMessage:message=>messages.push(message),t:key=>key,
    });
    assert.equal(result,false);
  }
  assert.deepEqual(calls,[]);
  assert.deepEqual(messages,["models.status.chooseGemmaVariant","models.status.chooseGemmaVariant"]);
});

it("shared explicit activation rejects unknown Gemma latest before state mutation or network", async () => {
  const calls: string[] = [];
  const activation = useCockpitModelActivation({
    selectedLlmServer:"vast_ollama",selectedLlmModel:"gemma4:e4b",activeServer:"vast_ollama",
    setSelectedLlmModel:()=>{calls.push("selection");},
    setActiveLlmRuntimeFn:async()=>{calls.push("cloud");},
    setActiveLlmServerFn:async()=>{calls.push("runtime");},
    refreshActiveServer:()=>{calls.push("refresh");},pushToast:()=>{},t:key=>key,
  });
  assert.equal(await activation.handleActivateModel("gemma4:latest"),false);
  assert.deepEqual(calls,[]);
});

it("remote labels stay explicit and other providers or observed Saluki remain available", () => {
  assert.equal(chatModelLabel("gemma4:e4b",undefined,"vast_ollama"),"Gemma4 E4B IT");
  assert.equal(resolveEffectiveChatModelSelection("gemma4:latest",null,"openrouter","openrouter"),"gemma4:latest");
  assert.equal(resolveEffectiveChatModelSelection("saluki:latest",null,"vast_ollama","vast_ollama"),"saluki:latest");
});
