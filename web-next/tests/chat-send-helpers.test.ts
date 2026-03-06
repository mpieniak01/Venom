import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { handleStandardTaskSend } from "../components/cockpit/chat-send-helpers";
import type { LocalHistoryEntry } from "../components/cockpit/chat-send-helpers";
import type { Dispatch, SetStateAction } from "react";

type LocalEntry = {
  role?: string;
  content?: string;
  request_id?: string;
  session_id?: string;
  timestamp?: string;
};

function createHistoryStore(initial: LocalEntry[]) {
  let history: LocalHistoryEntry[] = [...initial];
  const setLocalSessionHistory: Dispatch<SetStateAction<LocalHistoryEntry[]>> = (value) => {
    history = typeof value === "function" ? value(history) : value;
  };
  return {
    getHistory: () => history,
    setLocalSessionHistory,
  };
}

describe("handleStandardTaskSend", () => {
  it("adds assistant placeholder immediately and remaps it to backend request id", async () => {
    const historyStore = createHistoryStore([
      { role: "user", content: "hej", request_id: "client-1", session_id: "sess-1" },
    ]);

    await handleStandardTaskSend({
      trimmed: "hej",
      labMode: false,
      generationParams: null,
      runtimeOverride: null,
      activeServerInfo: null,
      parsed: {
        cleaned: "hej",
        forcedTool: undefined,
        forcedProvider: undefined,
        sessionReset: false,
      },
      forcedIntent: null,
      language: "pl",
      resolvedSession: "sess-1",
      clientId: "client-1",
      sendTask: async () => ({ task_id: "req-1" }),
      linkOptimisticRequest: () => {},
      setLocalSessionHistory: historyStore.setLocalSessionHistory,
      refreshTasks: async () => {},
      refreshQueue: async () => {},
      refreshHistory: async () => {},
      refreshSessionHistory: async () => {},
      dropOptimisticRequest: () => {},
      setMessage: () => {},
      setSending: () => {},
      t: (key) => key,
    });

    const history = historyStore.getHistory();
    assert.ok(
      history.some((entry) => entry.request_id === "req-1" && entry.role === "user"),
    );
    assert.ok(
      history.some(
        (entry) =>
          entry.request_id === "req-1" &&
          entry.role === "assistant" &&
          (entry.content ?? "") === "",
      ),
    );
  });

  it("removes empty assistant placeholder when sendTask fails", async () => {
    const historyStore = createHistoryStore([
      { role: "user", content: "hej", request_id: "client-2", session_id: "sess-1" },
    ]);

    await handleStandardTaskSend({
      trimmed: "hej",
      labMode: false,
      generationParams: null,
      runtimeOverride: null,
      activeServerInfo: null,
      parsed: {
        cleaned: "hej",
        forcedTool: undefined,
        forcedProvider: undefined,
        sessionReset: false,
      },
      forcedIntent: null,
      language: "pl",
      resolvedSession: "sess-1",
      clientId: "client-2",
      sendTask: async () => {
        throw new Error("network");
      },
      linkOptimisticRequest: () => {},
      setLocalSessionHistory: historyStore.setLocalSessionHistory,
      refreshTasks: async () => {},
      refreshQueue: async () => {},
      refreshHistory: async () => {},
      refreshSessionHistory: async () => {},
      dropOptimisticRequest: () => {},
      setMessage: () => {},
      setSending: () => {},
      t: (key) => key,
    });

    const history = historyStore.getHistory();
    assert.ok(
      !history.some(
        (entry) =>
          entry.request_id === "client-2" &&
          entry.role === "assistant" &&
          (entry.content ?? "") === "",
      ),
    );
  });
});
