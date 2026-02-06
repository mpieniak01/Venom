import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { filterHistoryAfterReset, mergeHistoryFallbacks } from "../components/cockpit/hooks/history-merge";
import { sessionEntryKey } from "../components/cockpit/cockpit-hooks";

describe("mergeHistoryFallbacks", () => {
  it("adds missing user prompt from history requests", () => {
    const sessionHistory = [
      {
        role: "assistant",
        request_id: "r1",
        content: "A1",
        timestamp: "2026-02-02T10:00:05Z",
      },
    ];
    const historyRequests = [
      {
        request_id: "r1",
        prompt: "Q1",
        created_at: "2026-02-02T10:00:00Z",
      },
    ];

    const merged = mergeHistoryFallbacks({
      sessionHistory,
      localSessionHistory: [],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      historyRequests: historyRequests as any,
      tasks: [],
      sessionId: null,
      sessionEntryKey,
    });

    assert.ok(merged.some((entry) => entry.role === "user" && entry.content === "Q1"));
  });

  it("adds missing assistant result from tasks", () => {
    const sessionHistory = [
      {
        role: "user",
        request_id: "r2",
        content: "Q2",
        timestamp: "2026-02-02T10:01:00Z",
      },
    ];
    const tasks = [
      {
        task_id: "r2",
        status: "COMPLETED",
        result: "A2",
        updated_at: "2026-02-02T10:01:05Z",
      },
    ];

    const merged = mergeHistoryFallbacks({
      sessionHistory,
      localSessionHistory: [],
      historyRequests: [],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      tasks: tasks as any,
      sessionId: null,
      sessionEntryKey,
    });

    assert.ok(merged.some((entry) => entry.role === "assistant" && entry.content === "A2"));
  });

  it("does not mix tasks from other sessions", () => {
    const sessionHistory = [
      {
        role: "user",
        request_id: "r3",
        content: "Q3",
        timestamp: "2026-02-02T10:02:00Z",
      },
    ];
    const tasks = [
      {
        task_id: "r3",
        status: "COMPLETED",
        result: "A3",
        context_history: { session: { session_id: "session-other" } },
      },
    ];

    const merged = mergeHistoryFallbacks({
      sessionHistory,
      localSessionHistory: [],
      historyRequests: [],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      tasks: tasks as any,
      sessionId: "session-current",
      sessionEntryKey,
    });

    assert.ok(!merged.some((entry) => entry.role === "assistant" && entry.content === "A3"));
  });

  it("ignores history requests without session_id when sessionId is set", () => {
    const sessionHistory = [
      {
        role: "assistant",
        request_id: "r5",
        content: "A5",
        timestamp: "2026-02-02T10:04:00Z",
      },
    ];
    const historyRequests = [
      {
        request_id: "r5",
        prompt: "Q5",
        created_at: "2026-02-02T10:04:00Z",
        session_id: null,
      },
    ];

    const merged = mergeHistoryFallbacks({
      sessionHistory,
      localSessionHistory: [],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      historyRequests: historyRequests as any,
      tasks: [],
      sessionId: "session-current",
      sessionEntryKey,
    });

    assert.ok(!merged.some((entry) => entry.role === "user" && entry.content === "Q5"));
  });

  it("keeps existing content without overwriting", () => {
    const sessionHistory = [
      {
        role: "assistant",
        request_id: "r4",
        content: "A4",
        timestamp: "2026-02-02T10:03:00Z",
      },
    ];
    const tasks = [
      {
        task_id: "r4",
        status: "COMPLETED",
        result: "A4-from-task",
        updated_at: "2026-02-02T10:03:05Z",
      },
    ];

    const merged = mergeHistoryFallbacks({
      sessionHistory,
      localSessionHistory: [],
      historyRequests: [],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      tasks: tasks as any,
      sessionId: null,
      sessionEntryKey,
    });

    const entry = merged.find((item) => item.role === "assistant" && item.request_id === "r4");
    assert.equal(entry?.content, "A4");
  });

  it("filters out entries older than reset timestamp", () => {
    const entries = [
      {
        role: "user",
        request_id: "r1",
        content: "Q1",
        timestamp: "2026-02-02T10:00:00Z",
      },
      {
        role: "assistant",
        request_id: "r1",
        content: "A1",
        timestamp: "2026-02-02T10:00:05Z",
      },
      {
        role: "user",
        request_id: "r2",
        content: "Q2",
        timestamp: "2026-02-02T10:10:00Z",
      },
    ];

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const filtered = filterHistoryAfterReset(entries as any, "2026-02-02T10:05:00Z");

    assert.deepStrictEqual(filtered.map((e) => e.request_id), ["r2"]);
  });
});
