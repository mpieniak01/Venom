import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useChatSend } from "../components/cockpit/cockpit-chat-send";
import type { ChatSendParams, LocalHistoryEntry } from "../components/cockpit/chat-send-helpers";
import { ApiError } from "../lib/api-client";
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


function validQuote(config = "fixed") {
  return Response.json({ estimated_usd: "0.01", currency: "USD", max_output_tokens: 1000, input_token_upper_bound: 2000, context_length: 8000, config_hash: config, quote_hash: "a".repeat(64) });
}

it("an unmounted runtime preflight cannot quote or post after the switch completes", async () => {
  const fixture = chatFixture(); let resolve!: (value: { runtime_id: string; config_hash: string }) => void;
  fixture.params.selectedLlmModel = "vendor/new";
  fixture.params.setActiveLlmRuntime = () => new Promise(ready => { resolve = ready; });
  let quotes = 0; globalThis.fetch = async () => { quotes++; return validQuote(); };
  const hook = renderHook(() => useChatSend(fixture.params));
  let pending!: Promise<boolean>; act(() => { pending = hook.result.current("question"); });
  await waitFor(() => assert.equal(typeof resolve, "function"));
  hook.unmount(); resolve({ runtime_id: "openrouter@vendor/new", config_hash: "new" });
  assert.equal(await pending, false);
  assert.equal(quotes, 0); assert.equal(fixture.calls.paid.length, 0); assert.equal(fixture.calls.optimistic, 0);
});

it("a session reset cancels deferred model preflight without a second request", async () => {
  const fixture = chatFixture(); let resolve!: (value: { runtime_id: string; config_hash: string }) => void;
  fixture.params.selectedLlmModel = "vendor/new";
  let switches = 0; fixture.params.setActiveLlmRuntime = () => { switches++; return new Promise(ready => { resolve = ready; }); };
  let quotes = 0; globalThis.fetch = async () => { quotes++; return validQuote(); };
  const hook = renderHook(({ session }) => useChatSend({ ...fixture.params, sessionId: session }), { initialProps: { session: "one" } });
  let pending!: Promise<boolean>; act(() => { pending = hook.result.current("question"); });
  await waitFor(() => assert.equal(switches, 1));
  assert.equal(await hook.result.current("double click"), false);
  hook.rerender({ session: "two" }); resolve({ runtime_id: "openrouter@vendor/new", config_hash: "new" });
  assert.equal(await pending, false);
  assert.equal(switches, 1); assert.equal(quotes, 0); assert.equal(fixture.calls.paid.length, 0);
});

it("a rejected material POST is not acknowledged, so the composer can preserve its exact draft", async () => {
  const fixture = chatFixture(); fixture.params.materialIds = ["material"];
  globalThis.fetch = async () => validQuote();
  fixture.params.sendSimpleChatStream = async payload => { fixture.calls.paid.push(payload); throw new ApiError("rejected", 413, { detail: { reason_code: "material_context_too_large" } }); };
  const hook = renderHook(() => useChatSend(fixture.params));
  await act(async () => { assert.equal(await hook.result.current("keep me"), false); });
  assert.deepEqual(fixture.calls.paid[0].materialIds, ["material"]);
});

it("Stop retains the streamed answer and marks it cancelled instead of replacing it with an error", async () => {
  const fixture = chatFixture(); let stream!: ReadableStreamDefaultController<Uint8Array>;
  globalThis.fetch = async () => validQuote();
  fixture.params.sendSimpleChatStream = async () => new Response(new ReadableStream<Uint8Array>({ start(controller) { stream = controller; controller.enqueue(new TextEncoder().encode('event: content\ndata: {"text":"real partial answer"}\n\n')); } }));
  const hook = renderHook(() => useChatSend(fixture.params));
  await act(async () => { assert.equal(await hook.result.current("question"), true); });
  await waitFor(() => assert.equal(fixture.history().find(entry => entry.role === "assistant")?.content, "real partial answer"));
  cancelSimpleChatStream(); stream.error(new DOMException("Stopped", "AbortError"));
  await waitFor(() => assert.equal(fixture.history().find(entry => entry.role === "assistant")?.status, "CANCELLED"));
  assert.equal(fixture.history().find(entry => entry.role === "assistant")?.content, "real partial answer");
  assert.equal(fixture.history().find(entry => entry.role === "assistant")?.pending, false);
});
