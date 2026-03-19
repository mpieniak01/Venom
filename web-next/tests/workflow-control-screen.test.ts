import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildControlDomainCards,
  buildExecutionStepLanes,
  buildRuntimeServiceTracks,
  buildSelectionNode,
  findExecutionStep,
  findRuntimeService,
  getStatusTone,
  mapConfigKeyToControlDomain,
} from "../lib/workflow-control-screen";

describe("workflow-control 204B screen helpers", () => {
  const systemState = {
    decision_strategy: "standard",
    intent_mode: "simple",
    kernel: "optimized",
    provider: { active: "ollama", sourceType: "local" },
    provider_source: "local",
    embedding_model: "sentence-transformers",
    embedding_source: "local",
    config_fields: [
      {
        key: "AI_MODE",
        field: "value",
        entity_id: "config:AI_MODE",
        value: "standard",
        effective_value: "standard",
        source: "env",
        editable: true,
        restart_required: false,
        affected_services: [],
      },
      {
        key: "INTENT_MODE",
        field: "value",
        entity_id: "config:INTENT_MODE",
        value: "simple",
        effective_value: "simple",
        source: "default",
        editable: true,
        restart_required: false,
        affected_services: [],
      },
      {
        key: "KERNEL",
        field: "value",
        entity_id: "config:KERNEL",
        value: "optimized",
        effective_value: "optimized",
        source: "env",
        editable: true,
        restart_required: true,
        affected_services: ["backend"],
      },
      {
        key: "ACTIVE_PROVIDER",
        field: "value",
        entity_id: "config:ACTIVE_PROVIDER",
        value: "ollama",
        effective_value: "ollama",
        source: "default",
        editable: true,
        restart_required: true,
        affected_services: ["llm_ollama"],
      },
      {
        key: "EMBEDDING_MODEL",
        field: "value",
        entity_id: "config:EMBEDDING_MODEL",
        value: "sentence-transformers",
        effective_value: "sentence-transformers",
        source: "default",
        editable: true,
        restart_required: false,
        affected_services: [],
      },
    ],
    runtime_services: [
      { id: "backend", name: "backend", status: "running", allowed_actions: ["stop"] },
    ],
    execution_steps: [
      {
        id: "step-1",
        component: "intent",
        action: "classify",
        status: "running",
        stage: "intent",
        related_service_id: "backend",
        related_config_keys: ["INTENT_MODE"],
        depends_on_step_id: null,
        severity: "info",
      },
    ],
  };

  const draftState = {
    ...systemState,
    decision_strategy: "advanced",
    provider: { active: "openai", sourceType: "cloud" },
    provider_source: "cloud",
    config_fields: [
      ...(systemState.config_fields ?? []).map((field) =>
        field.key === "AI_MODE"
          ? { ...field, value: "advanced", effective_value: "advanced" }
          : field
      ),
    ],
  };

  it("builds control domain cards from canonical state instead of execution steps", () => {
    const cards = buildControlDomainCards(systemState, draftState);

    assert.equal(cards.length, 6);
    const decision = cards.find((card) => card.id === "decision");
    const provider = cards.find((card) => card.id === "provider");
    const config = cards.find((card) => card.id === "config");

    assert.equal(decision?.value, "advanced");
    assert.equal(decision?.source, "env");
    assert.equal(decision?.changed, true);
    assert.equal(provider?.value, "openai");
    assert.equal(provider?.changed, true);
    assert.equal(config?.value, "5 fields");
    assert.equal(config?.restartRequired, true);
  });

  it("builds pseudo nodes for selected control domains", () => {
    const providerNode = buildSelectionNode(
      { kind: "control-domain", id: "provider" },
      draftState,
    );
    const configNode = buildSelectionNode(
      { kind: "control-domain", id: "config" },
      draftState,
    );

    assert.equal(providerNode?.type, "provider");
    assert.equal(
      (providerNode?.data as { provider?: { active?: string } }).provider?.active,
      "openai",
    );
    assert.equal(configNode?.type, "config");
    assert.equal(
      ((configNode?.data as { configFields?: unknown[] }).configFields ?? []).length,
      5,
    );
  });

  it("maps runtime services, execution steps and status tones", () => {
    assert.equal(findRuntimeService(systemState.runtime_services, "backend")?.name, "backend");
    assert.equal(findExecutionStep(systemState.execution_steps, "step-1")?.action, "classify");
    assert.equal(findExecutionStep(systemState.execution_steps, "step-1")?.related_service_id, "backend");
    assert.equal(mapConfigKeyToControlDomain("INTENT_MODE"), "intent");
    assert.equal(getStatusTone("running"), "success");
    assert.equal(getStatusTone("paused"), "warning");
    assert.equal(getStatusTone("failed"), "danger");
  });

  it("groups runtime services into dependency tracks and steps into stage lanes", () => {
    const runtimeTracks = buildRuntimeServiceTracks([
      { id: "backend", name: "backend", dependencies: [] },
      { id: "ui", name: "ui", dependencies: ["backend"] },
      { id: "academy", name: "academy", dependencies: ["ui"] },
    ]);
    const executionLanes = buildExecutionStepLanes([
      { id: "step-1", component: "intent", action: "classify", status: "ok", stage: "intent" },
      { id: "step-2", component: "kernel", action: "route", status: "ok", stage: "kernel" },
      { id: "step-3", component: "intent", action: "finalize", status: "ok", stage: "intent" },
    ]);

    assert.equal(runtimeTracks.length, 3);
    assert.deepEqual(runtimeTracks.map((track) => track.depth), [0, 1, 2]);
    assert.equal(runtimeTracks[1].services[0].id, "ui");
    assert.equal(executionLanes.length, 2);
    assert.equal(executionLanes[0].stage, "intent");
    assert.equal(executionLanes[0].steps.length, 2);
  });
});
