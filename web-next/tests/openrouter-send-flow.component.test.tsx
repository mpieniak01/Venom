import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useChatSend } from "../components/cockpit/cockpit-chat-send";
import type { ChatSendParams, LocalHistoryEntry } from "../components/cockpit/chat-send-helpers";
import { cancelSimpleChatStream } from "../hooks/use-api";

const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); cancelSimpleChatStream(); globalThis.fetch = originalFetch; });
function chatFixture() {
  const calls = { paid: [] as Parameters<ChatSendParams["sendSimpleChatStream"]>[0][], optimistic: 0, standard: 0, sending: [] as boolean[] };
  let history: LocalHistoryEntry[] = [];
  const params: ChatSendParams = {
    labMode: false, chatMode: "direct", generationParams: null,
    selectedLlmModel: "vendor/model", selectedLlmServer: "openrouter",
    activeServerInfo: { active_server: "openrouter", active_model: "vendor/model", runtime_id: "openrouter@vendor/model", config_hash: "fixed" },
    sessionId: "session", language: "pl", resetSession: () => "session", refreshActiveServer: () => {},
    setActiveLlmRuntime: async () => { throw new Error("must preserve the active provider"); },
    setActiveLlmServer: async () => { throw new Error("must not fall back locally"); },
    sendSimpleChatStream: async payload => { calls.paid.push(payload); return new Response('event: done\ndata: {}\n\n'); },
    sendTask: async () => { calls.standard++; return { task_id: "task" }; },
    ingestMemoryEntry: async () => {}, refreshTasks: async () => {}, refreshQueue: async () => {}, refreshHistory: async () => {}, refreshSessionHistory: async () => {},
    enqueueOptimisticRequest: () => { calls.optimistic++; return "request"; }, linkOptimisticRequest: () => {}, dropOptimisticRequest: () => {}, updateSimpleStream: () => {}, recordUiTiming: () => {}, uiTimingsRef: { current: new Map() }, clearSimpleStream: () => {},
    setLocalSessionHistory: update => { history = typeof update === "function" ? update(history) : update; },
    setSimpleRequestDetails: () => {}, setMessage: () => {}, setSending: value => { calls.sending.push(value); }, setLastResponseDurationMs: () => {}, setResponseDurations: () => {}, scrollChatToBottom: () => {}, autoScrollEnabled: { current: false },
  };
  return { calls, params, history: () => history };
}

describe("OpenRouter send flow", () => {
  it("cancels during the quote and never enqueues or dispatches a paid request", async () => {
    const fixture = chatFixture();
    let quotes = 0;
    globalThis.fetch = async (_input, options) => {
      quotes++;
      return new Promise((_resolve, reject) => options?.signal?.addEventListener("abort", () => reject(new DOMException("Stopped", "AbortError"))));
    };
    const { result } = renderHook(() => useChatSend(fixture.params));
    let pending: Promise<boolean>;
    act(() => { pending = result.current("question"); });
    await waitFor(() => assert.equal(quotes, 1));
    cancelSimpleChatStream();
    await act(async () => { assert.equal(await pending, false); });
    assert.equal(fixture.calls.optimistic, 0);
    assert.equal(fixture.calls.paid.length, 0);
    assert.equal(fixture.calls.standard, 0);
    assert.deepEqual(fixture.calls.sending, [true, false]);
  });

  it("a rejected quote cannot fall back or create an optimistic generation", async () => {
    const fixture = chatFixture();
    globalThis.fetch = async () => Response.json({ detail: "budget_exceeded" }, { status: 409 });
    const { result } = renderHook(() => useChatSend(fixture.params));
    await act(async () => { assert.equal(await result.current("question"), false); });
    assert.equal(fixture.calls.optimistic, 0);
    assert.equal(fixture.calls.paid.length, 0);
    assert.equal(fixture.calls.standard, 0);
    assert.deepEqual(fixture.calls.sending, [true, false]);
  });

  it("standard requests retain one initial user entry after extracting history updates", async () => {
    const fixture = chatFixture();
    fixture.params.chatMode = "normal";
    fixture.params.selectedLlmServer = "ollama";
    fixture.params.selectedLlmModel = "local";
    fixture.params.activeServerInfo = { active_server: "ollama", active_model: "local", runtime_id: "ollama@local" };
    const { result } = renderHook(() => useChatSend(fixture.params));
    await act(async () => { assert.equal(await result.current("question"), true); });
    await waitFor(() => assert.equal(fixture.calls.standard, 1));
    assert.equal(fixture.calls.optimistic, 1);
    assert.equal(fixture.calls.paid.length, 0);
    assert.deepEqual(fixture.history().filter(entry => entry.role === "user").map(entry => [entry.role, entry.content, entry.session_id, entry.request_id]), [["user", "question", "session", "task"]]);
  });
});
