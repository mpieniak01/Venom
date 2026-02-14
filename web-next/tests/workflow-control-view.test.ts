import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getWorkflowStatusMeta,
  shouldShowApplyResultsModal,
} from "../lib/workflow-control-ui-helpers";

describe("workflow-control view helpers", () => {
  it("shows apply results modal only when both flag and data are present", () => {
    assert.equal(shouldShowApplyResultsModal(true, null), false);
    assert.equal(
      shouldShowApplyResultsModal(true, {
        apply_mode: "hot_swap",
      }),
      true
    );
    assert.equal(
      shouldShowApplyResultsModal(false, {
        apply_mode: "hot_swap",
      }),
      false
    );
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
