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
      active_server: "vast_ollama", active_model: "gemma4:latest", active_endpoint: "http://127.0.0.1:23456/v1",
      runtime_id: "ollama@vast:plan:instance:new", config_hash: "remote-config",
    };
    const calls: string[] = [];
    const result = await syncTargetServerIfNeeded({
      selectedLlmServer: "vast_ollama", selectedLlmModel: "gemma4:latest",
      activeServerInfo: {active_server: "ollama", runtime_id: "ollama@local", config_hash: "local-config"},
      setActiveLlmRuntime: async () => {throw new Error("remote target must not activate cloud provider");},
      setActiveLlmServer: async (server, model) => {calls.push(server + "/" + model); return response;},
      refreshActiveServer: () => {}, setMessage: () => {}, t: (key) => key,
    });
    assert.deepEqual(result, response);
    assert.deepEqual(calls, ["vast_ollama/gemma4:latest"]);
  });

  it("stops the send after failed attachment activation instead of falling back locally", async () => {
    const result = await syncTargetServerIfNeeded({
      selectedLlmServer: "vast_ollama", selectedLlmModel: "gemma4:latest",
      activeServerInfo: {active_server: "ollama", runtime_id: "ollama@local"},
      setActiveLlmRuntime: async () => ({}), setActiveLlmServer: async () => {throw new Error("unavailable");},
      refreshActiveServer: () => {}, setMessage: () => {}, t: (key) => key,
    });
    assert.equal(result, false);
  });
});
