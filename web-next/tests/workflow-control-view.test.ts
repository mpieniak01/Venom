import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ApplyResults } from "../types/workflow-control";
import {
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
});
