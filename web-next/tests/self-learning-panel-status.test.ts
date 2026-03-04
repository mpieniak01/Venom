import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isTerminalSelfLearningStatus } from "../components/academy/self-learning-panel";

describe("isTerminalSelfLearningStatus", () => {
  it("returns false for non-terminal statuses", () => {
    assert.equal(isTerminalSelfLearningStatus("pending"), false);
    assert.equal(isTerminalSelfLearningStatus("running"), false);
  });

  it("returns true for terminal statuses", () => {
    assert.equal(isTerminalSelfLearningStatus("completed"), true);
    assert.equal(isTerminalSelfLearningStatus("completed_with_warnings"), true);
    assert.equal(isTerminalSelfLearningStatus("failed"), true);
  });
});
