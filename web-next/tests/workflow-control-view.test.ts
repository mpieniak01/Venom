import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ApplyResults } from "../types/workflow-control";
import {
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
});
