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

  it("prefers canonical payload sections over nested system_state fields", () => {
    const payload = {
      system_state: {
        config_fields: [{ key: "AI_MODE", value: "standard" }],
        runtime_services: [{ id: "backend", status: "stopped" }],
      },
      config_fields: [{ key: "AI_MODE", value: "advanced" }],
      runtime_services: [{ id: "backend", status: "running" }],
      execution_steps: [{ id: "step-1", component: "intent", action: "classify", status: "ok" }],
    };

    const state = extractSystemStateFromPayload(payload);
    assert.equal(state?.config_fields?.[0]?.value, "advanced");
    assert.equal(state?.runtime_services?.[0]?.status, "running");
    assert.equal(state?.execution_steps?.[0]?.id, "step-1");
  });

  it("maps workflow_target fields into system state", () => {
    const payload = {
      system_state: {
        workflow_status: "idle",
        active_request_id: null,
      },
      workflow_target: {
        request_id: "req-123",
        task_status: "PROCESSING",
        workflow_status: "running",
        runtime_id: "runtime-1",
        provider: "ollama",
        model: "llama3",
        allowed_operations: ["pause", "cancel"],
      },
    };

    const state = extractSystemStateFromPayload(payload);
    assert.equal(state?.active_request_id, "req-123");
    assert.equal(state?.active_task_status, "PROCESSING");
    assert.equal(state?.workflow_status, "running");
    assert.equal(state?.llm_runtime_id, "runtime-1");
    assert.equal(state?.llm_provider_name, "ollama");
    assert.equal(state?.llm_model, "llama3");
    assert.deepEqual(state?.allowed_operations, ["pause", "cancel"]);
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
