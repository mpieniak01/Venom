import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  extractSystemStateFromPayload,
  readApiErrorMessage,
} from "../hooks/useWorkflowState";

describe("workflow-control hook helpers", () => {
  it("extracts system_state from valid payload", () => {
    const payload = {
      system_state: {
        decision_strategy: "standard",
        intent_mode: "simple",
      },
    };
    const state = extractSystemStateFromPayload(payload);
    assert.equal(state?.decision_strategy, "standard");
    assert.equal(state?.intent_mode, "simple");
  });

  it("returns null for invalid payload", () => {
    const payload = { invalid: true };
    const state = extractSystemStateFromPayload(payload);
    assert.equal(state, null);
  });

  it("reads API detail message from JSON payload", async () => {
    const response = new Response(
      JSON.stringify({ detail: "state endpoint failed" }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }
    );
    const msg = await readApiErrorMessage(response, "fallback");
    assert.equal(msg, "state endpoint failed");
  });

  it("falls back to raw text for non-JSON response", async () => {
    const response = new Response("plain-text-error", {
      status: 500,
      headers: { "Content-Type": "text/plain" },
    });
    const msg = await readApiErrorMessage(response, "fallback");
    assert.equal(msg, "plain-text-error");
  });
});
