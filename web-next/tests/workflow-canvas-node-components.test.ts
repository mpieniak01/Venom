import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { handleExecutionGroupToggleClick } from "../components/workflow-control/canvas/node-components";

describe("workflow canvas node interaction helpers", () => {
  it("stops propagation and toggles execution group when group key exists", () => {
    let stopPropagationCalls = 0;
    const toggledGroups: string[] = [];

    handleExecutionGroupToggleClick(
      {
        stopPropagation: () => {
          stopPropagationCalls += 1;
        },
      },
      "group:execution:1",
      (groupKey) => {
        toggledGroups.push(groupKey);
      },
    );

    assert.equal(stopPropagationCalls, 1);
    assert.deepEqual(toggledGroups, ["group:execution:1"]);
  });

  it("stops propagation and skips toggle when group key is missing", () => {
    let stopPropagationCalls = 0;
    let toggleCalled = false;

    handleExecutionGroupToggleClick(
      {
        stopPropagation: () => {
          stopPropagationCalls += 1;
        },
      },
      undefined,
      () => {
        toggleCalled = true;
      },
    );

    assert.equal(stopPropagationCalls, 1);
    assert.equal(toggleCalled, false);
  });
});
