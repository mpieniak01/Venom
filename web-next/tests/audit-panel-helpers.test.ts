import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isNearBottom, mergeAuditEntries, nextVisibleCount } from "../lib/audit-panel-helpers";

type Entry = {
  id: string;
  timestamp: string;
  value: string;
};

describe("audit panel helpers", () => {
  it("merges incoming entries without duplicates by id + timestamp", () => {
    const current: Entry[] = [
      { id: "a", timestamp: "2026-02-26T11:00:00Z", value: "first" },
      { id: "b", timestamp: "2026-02-26T11:01:00Z", value: "second" },
    ];
    const incoming: Entry[] = [
      { id: "b", timestamp: "2026-02-26T11:01:00Z", value: "duplicate" },
      { id: "c", timestamp: "2026-02-26T11:02:00Z", value: "third" },
    ];

    const merged = mergeAuditEntries(current, incoming);

    assert.equal(merged.length, 3);
    assert.deepEqual(merged.map((entry) => entry.id), ["a", "b", "c"]);
  });

  it("detects when scroll is close enough to bottom", () => {
    assert.equal(isNearBottom(1000, 860, 120), true);
    assert.equal(isNearBottom(1000, 700, 120), false);
  });

  it("computes next visible count with upper bound", () => {
    assert.equal(nextVisibleCount(60, 200, 60), 120);
    assert.equal(nextVisibleCount(180, 200, 60), 200);
  });
});
