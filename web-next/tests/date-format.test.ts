import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { formatRelativeTime } from "../lib/date";

describe("date formatting", () => {
  it("formats timestamps with fixed date-time precision to tenths of second", () => {
    const formatted = formatRelativeTime("2026-03-05T08:26:18.987Z");
    assert.match(formatted, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d$/);
  });
});
