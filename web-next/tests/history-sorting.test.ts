import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { sortHistoryByCreatedAtAsc } from "../hooks/use-api";
import { selectHistoryWindow } from "../components/history/history-list";

describe("history sorting helpers", () => {
  it("sortHistoryByCreatedAtAsc sorts ascending by created_at", () => {
    const input = [
      { request_id: "b", created_at: "2026-02-02T10:01:00Z" },
      { request_id: "a", created_at: "2026-02-02T10:00:00Z" },
      { request_id: "c", created_at: "2026-02-02T10:02:00Z" },
    ];

    const ordered = sortHistoryByCreatedAtAsc(input as any);

    assert.deepStrictEqual(ordered.map((e) => e.request_id), ["a", "b", "c"]);
  });

  it("selectHistoryWindow returns last N entries", () => {
    const input = [
      { request_id: "r1" },
      { request_id: "r2" },
      { request_id: "r3" },
      { request_id: "r4" },
    ];

    const windowed = selectHistoryWindow(input as any, 2);

    assert.deepStrictEqual(windowed.map((e: any) => e.request_id), ["r3", "r4"]);
  });
});
