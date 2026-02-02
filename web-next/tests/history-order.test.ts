import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { orderHistoryEntriesByRequestId } from "../components/cockpit/hooks/history-order";

describe("orderHistoryEntriesByRequestId", () => {
  it("keeps user/assistant pairs together per request_id", () => {
    const entries = [
      {
        role: "assistant",
        request_id: "r1",
        timestamp: "2026-02-02T10:00:05Z",
        content: "A1",
      },
      {
        role: "user",
        request_id: "r2",
        timestamp: "2026-02-02T10:01:00Z",
        content: "Q2",
      },
      {
        role: "user",
        request_id: "r1",
        timestamp: "2026-02-02T10:00:00Z",
        content: "Q1",
      },
      {
        role: "assistant",
        request_id: "r2",
        timestamp: "2026-02-02T10:01:05Z",
        content: "A2",
      },
    ];

    const ordered = orderHistoryEntriesByRequestId(entries);

    assert.deepStrictEqual(ordered.map((e) => `${e.request_id}:${e.role}`), [
      "r1:user",
      "r1:assistant",
      "r2:user",
      "r2:assistant",
    ]);
  });

  it("appends entries without request_id after grouped pairs", () => {
    const entries = [
      {
        role: "user",
        request_id: "r1",
        timestamp: "2026-02-02T10:00:00Z",
        content: "Q1",
      },
      {
        role: "assistant",
        request_id: "r1",
        timestamp: "2026-02-02T10:00:05Z",
        content: "A1",
      },
      {
        role: "assistant",
        timestamp: "2026-02-02T10:00:06Z",
        content: "stream",
      },
    ];

    const ordered = orderHistoryEntriesByRequestId(entries);

    assert.deepStrictEqual(ordered.map((e) => e.content), ["Q1", "A1", "stream"]);
  });
});
