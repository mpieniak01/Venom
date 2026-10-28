import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cancelSimpleChatStream, sendSimpleChatStream } from "../hooks/use-api";
import { appendVastChatTurn, vastChatHistoryKey } from "../lib/vast-chat-history";
import { handleSimpleTaskSend } from "../components/cockpit/chat-send-helpers";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; cancelSimpleChatStream(); });

describe("Vast Direct transport", () => {
  it("serializes expected identity and bounded conversation history", async () => {
    let body: Record<string, unknown> = {};
    globalThis.fetch = async (_url, options) => {
      body = JSON.parse(String(options?.body));
      return new Response("event: done\ndata: {}\n\n");
    };
    await sendSimpleChatStream({content: "next", model: "same-name", expectedRuntimeId: "ollama@vast:plan:instance:generation", expectedConfigHash: "hash", history: [{role: "assistant", content: "prior"}]});
    assert.equal(body.expected_runtime_id, "ollama@vast:plan:instance:generation");
    assert.equal(body.expected_config_hash, "hash");
    assert.deepEqual(body.history, [{role: "assistant", content: "prior"}]);
  });

  it("does not repeat a remote POST after a network failure", async () => {
    let count = 0;
    globalThis.fetch = async () => {count += 1; throw new Error("connection lost");};
    await assert.rejects(sendSimpleChatStream({content: "hello", expectedRuntimeId: "ollama@vast:plan:instance:generation"}));
    assert.equal(count, 1);
  });

  it("cancels the active HTTP request without sending another prompt", async () => {
    globalThis.fetch = async (_url, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(new Error("cancelled")));
    });
    const pending = sendSimpleChatStream({content: "hello", expectedRuntimeId: "ollama@vast:plan:instance:generation"});
    cancelSimpleChatStream();
    await assert.rejects(pending, /cancelled/);
  });

  it("isolates and bounds completed history by session, model and target generation", () => {
    const key = vastChatHistoryKey("ollama@vast:p:i:g", "model", "session");
    assert.notEqual(key, vastChatHistoryKey("ollama@vast:p:i:new", "model", "session"));
    assert.notEqual(key, vastChatHistoryKey("ollama@vast:p:i:g", "other", "session"));
    assert.notEqual(key, vastChatHistoryKey("ollama@vast:p:i:g", "model", "other"));
    assert.equal(vastChatHistoryKey("ollama@local", "model", "session"), null);
    assert.notEqual(vastChatHistoryKey("ollama@vast:p:i:g", "model", "session", "old"), vastChatHistoryKey("ollama@vast:p:i:g", "model", "session", "new"));
    let history = appendVastChatTurn([], "first", "answer");
    for (let i = 0; i < 15; i += 1) history = appendVastChatTurn(history, "q" + i, "a" + i);
    assert.equal(history.length, 20);
    assert.equal(history[0].role, "user");
    assert.deepEqual(appendVastChatTurn([], "x".repeat(50001), "too long"), []);
  });

  it("rejects EOF without done and never saves an incomplete remote turn", async () => {
    let completed = false;
    let status = "";
    const args: Parameters<typeof handleSimpleTaskSend>[0] = {
      clientId: "id", trimmed: "question", resolvedSession: "session",
      generationParams: null, selectedLlmModel: "remote",
      activeServerInfo: {runtime_id: "ollama@vast:p:i:g"},
      onCompleted: () => {completed = true;},
      sendSimpleChatStream: async () => new Response('event: content\ndata: {"text":"partial"}\n\n'),
      linkOptimisticRequest: () => {}, setLocalSessionHistory: () => {},
      updateSimpleStream: (_id, update) => {status = update.status ?? status;},
      recordUiTiming: () => {}, uiTimingsRef: {current: new Map()},
      setSimpleRequestDetails: () => {}, ingestMemoryEntry: async () => {},
      setLastResponseDurationMs: () => {}, setResponseDurations: () => {},
      dropOptimisticRequest: () => {}, clearSimpleStream: () => {},
      setMessage: () => {}, setSending: () => {},
    };
    await handleSimpleTaskSend(args);
    assert.equal(completed, false);
    assert.equal(status, "FAILED");
  });
});
