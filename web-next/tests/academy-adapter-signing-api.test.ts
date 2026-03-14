import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { activateAdapter, signAdapterForChat } from "../lib/academy-api";

describe("academy adapter signing api client", () => {
  it("calls adapter sign endpoint with runtime/model/signer payload", async () => {
    const originalFetch = globalThis.fetch;
    const calls: Array<{ url: string; method: string; body: unknown }> = [];

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({
        url,
        method: init?.method || "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      return new Response(
        JSON.stringify({
          success: true,
          adapter_id: "adapter-1",
          signature: { adapter_id: "adapter-1" },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    };

    try {
      const response = await signAdapterForChat("adapter-1", {
        runtime_id: "ollama",
        model_id: "gemma3:latest",
        signer: "academy-ui",
      });

      assert.equal(response.success, true);
      assert.equal(response.adapter_id, "adapter-1");
      assert.equal(calls.length, 1);
      assert.equal(calls[0]?.url.includes("/api/v1/academy/adapters/adapter-1/sign"), true);
      assert.equal(calls[0]?.method, "POST");
      assert.deepEqual(calls[0]?.body, {
        runtime_id: "ollama",
        model_id: "gemma3:latest",
        signer: "academy-ui",
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("passes require_chat_signature in activate payload", async () => {
    const originalFetch = globalThis.fetch;
    const calls: Array<{ url: string; method: string; body: unknown }> = [];

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({
        url,
        method: init?.method || "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      return new Response(
        JSON.stringify({
          success: true,
          message: "activated",
          deployed: true,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    };

    try {
      await activateAdapter({
        adapter_id: "adapter-1",
        adapter_path: "/tmp/adapter-1",
        runtime_id: "ollama",
        model_id: "gemma3:latest",
        deploy_to_chat_runtime: true,
        require_chat_signature: true,
      });

      assert.equal(calls.length, 1);
      assert.equal(calls[0]?.url.includes("/api/v1/academy/adapters/activate"), true);
      assert.equal(calls[0]?.method, "POST");
      assert.equal((calls[0]?.body as Record<string, unknown>).require_chat_signature, true);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
