import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ApplyResults, WorkflowControlOptions } from "../types/workflow-control";
import {
  buildWorkflowSelectionSummary,
  buildDraftCompatibilityReport,
  buildWorkflowDraftVisualState,
  generatePlanRequest,
  getWorkflowStatusMeta,
  shouldShowApplyResultsModal,
} from "../lib/workflow-control-ui-helpers";

describe("workflow-control view helpers", () => {
  it("shows apply results modal only when both flag and data are present", () => {
    const applyResults: ApplyResults = {
      execution_ticket: "ticket-1",
      apply_mode: "hot_swap",
      reason_code: "success_hot_swap",
      message: "applied",
      applied_changes: [],
      rollback_available: false,
    };
    assert.equal(shouldShowApplyResultsModal(true, null), false);
    assert.equal(shouldShowApplyResultsModal(true, applyResults), true);
    assert.equal(shouldShowApplyResultsModal(false, applyResults), false);
  });

  it("computes operation availability from workflow status", () => {
    const running = getWorkflowStatusMeta("running");
    assert.equal(running.canPause, true);
    assert.equal(running.canResume, false);
    assert.equal(running.canCancel, true);
    assert.equal(running.canRetry, false);

    const failed = getWorkflowStatusMeta("failed");
    assert.equal(failed.canPause, false);
    assert.equal(failed.canResume, false);
    assert.equal(failed.canCancel, false);
    assert.equal(failed.canRetry, true);
  });

  it("includes config resource changes when config_fields values differ", () => {
    const original = {
      decision_strategy: "standard",
      intent_mode: "simple",
      kernel: "standard",
      provider: { active: "ollama" },
      embedding_model: "sentence-transformers",
      config_fields: [
        { key: "AI_MODE", value: "standard", entity_id: "config:AI_MODE", field: "AI_MODE" },
        { key: "INTENT_MODE", value: "simple", entity_id: "config:INTENT_MODE", field: "INTENT_MODE" },
      ],
    };
    const draft = {
      ...original,
      config_fields: [
        { key: "AI_MODE", value: "advanced", entity_id: "config:AI_MODE", field: "AI_MODE" },
        { key: "INTENT_MODE", value: "simple", entity_id: "config:INTENT_MODE", field: "INTENT_MODE" },
      ],
    };

    const result = generatePlanRequest(original, draft);
    const configChanges = result.changes.filter((c) => c.resource_type === "config");

    assert.equal(configChanges.length, 1);
    assert.equal(configChanges[0].resource_id, "AI_MODE");
    assert.equal(configChanges[0].entity_id, "config:AI_MODE");
    assert.equal(configChanges[0].field, "AI_MODE");
    assert.equal(configChanges[0].new_value, "advanced");
    assert.equal(configChanges[0].action, "update");
  });

  it("does not emit config changes when config_fields remain unchanged", () => {
    const original = {
      config_fields: [
        { key: "KERNEL", value: "standard", entity_id: "config:KERNEL", field: "KERNEL" },
      ],
    };
    const draft = {
      config_fields: [
        { key: "KERNEL", value: "standard", entity_id: "config:KERNEL", field: "KERNEL" },
      ],
    };

    const result = generatePlanRequest(original, draft);
    const configChanges = result.changes.filter((c) => c.resource_type === "config");
    assert.equal(configChanges.length, 0);
  });

  it("builds draft compatibility report before plan", () => {
    const controlOptions: WorkflowControlOptions = {
      kernels: ["standard", "minimal"],
      intent_modes: ["simple", "advanced"],
      providers: { local: ["ollama"], cloud: ["openai"] },
      embeddings: { local: ["sentence-transformers"], cloud: ["openai-embeddings"] },
      kernel_runtimes: { standard: ["python", "docker"], minimal: ["python"] },
      intent_requirements: {
        simple: { requires_embedding: false },
        advanced: { requires_embedding: true },
      },
      provider_embeddings: {
        ollama: ["sentence-transformers"],
        openai: ["openai-embeddings"],
      },
      embedding_providers: {
        "sentence-transformers": ["ollama"],
        "openai-embeddings": ["openai"],
      },
      active: { provider_source: "local", embedding_source: "local" },
    };
    const systemState = {
      provider: { active: "ollama", sourceType: "local" },
      provider_source: "local",
      embedding_model: "sentence-transformers",
      embedding_source: "local",
      kernel: "standard",
      intent_mode: "simple",
      config_fields: [
        { key: "WORKFLOW_RUNTIME", value: "docker", entity_id: "config:WORKFLOW_RUNTIME", field: "WORKFLOW_RUNTIME" },
      ],
    };
    const draftState = {
      ...systemState,
      kernel: "minimal",
      intent_mode: "advanced",
      embedding_model: "",
      provider: { active: "openai", sourceType: "cloud" },
      provider_source: "cloud",
    };

    const report = buildDraftCompatibilityReport(controlOptions, systemState, draftState);

    assert.equal(report.issues.length, 2);
    assert.equal(report.issuesByDomain.kernel?.[0]?.code, "kernel_runtime_mismatch");
    assert.equal(report.issuesByDomain.intent?.[0]?.code, "intent_requires_embedding");
    assert.equal(report.issuesByDomain.embedding?.[0]?.code, "intent_requires_embedding");
  });

  it("summarizes draft visual state for header status rail", () => {
    const conflictState = buildWorkflowDraftVisualState(3, 1, false);
    const readyState = buildWorkflowDraftVisualState(2, 0, true);

    assert.equal(conflictState.changedDomainCount, 3);
    assert.equal(conflictState.hasConflicts, true);
    assert.equal(conflictState.isPlanReady, false);
    assert.equal(readyState.hasConflicts, false);
    assert.equal(readyState.isPlanReady, true);
  });

  it("builds selection summary for control domain/runtime service/execution step", () => {
    const systemState = {
      runtime_services: [{ id: "backend", name: "backend", status: "running" }],
      execution_steps: [
        { id: "s1", component: "router", action: "route-safe", status: "ok" },
      ],
    };

    const domainSummary = buildWorkflowSelectionSummary(
      { kind: "control-domain", id: "intent" },
      systemState,
    );
    const serviceSummary = buildWorkflowSelectionSummary(
      { kind: "runtime-service", serviceId: "backend" },
      systemState,
    );
    const stepSummary = buildWorkflowSelectionSummary(
      { kind: "execution-step", stepId: "s1" },
      systemState,
    );

    assert.deepEqual(domainSummary, {
      kind: "control-domain",
      label: "control-domain",
      value: "intent",
      id: "intent",
    });
    assert.deepEqual(serviceSummary, {
      kind: "runtime-service",
      label: "runtime-service",
      value: "backend",
      id: "backend",
    });
    assert.deepEqual(stepSummary, {
      kind: "execution-step",
      label: "execution-step",
      value: "router:route-safe",
      id: "s1",
    });
  });
});
