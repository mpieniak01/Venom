import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { formatDateTime, formatRelativeTime } from "@/lib/date";

describe("formatRelativeTime", () => {
  it("returns em dash for empty values", () => {
    assert.equal(formatRelativeTime(), "—");
    assert.equal(formatRelativeTime(null), "—");
  });

  it("returns original input for invalid date", () => {
    assert.equal(formatRelativeTime("not-a-date"), "not-a-date");
  });

  it("returns formatted relative text for valid date", () => {
    const now = Date.now();
    const value = new Date(now - 5 * 60_000).toISOString();
    const result = formatRelativeTime(value);

    assert.equal(typeof result, "string");
    assert.notEqual(result, value);
    assert.notEqual(result, "—");
  });

  it("uses language from localStorage when window exists", () => {
    const originalWindow = (globalThis as { window?: unknown }).window;
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: {
        localStorage: {
          getItem: () => "en",
        },
      },
    });

    try {
      const now = Date.now();
      const value = new Date(now - 120_000).toISOString();
      const result = formatRelativeTime(value);
      assert.equal(typeof result, "string");
      assert.notEqual(result, "—");
    } finally {
      if (originalWindow === undefined) {
        delete (globalThis as { window?: unknown }).window;
      } else {
        Object.defineProperty(globalThis, "window", {
          configurable: true,
          value: originalWindow,
        });
      }
    }
  });
});

describe("formatDateTime", () => {
  const sample = "2026-02-09T12:34:00.000Z";

  it("returns em dash for empty values", () => {
    assert.equal(formatDateTime(), "—");
    assert.equal(formatDateTime(null), "—");
  });

  it("returns original input for invalid date", () => {
    assert.equal(formatDateTime("bad-value"), "bad-value");
  });

  it("formats using requested locale and format", () => {
    const result = formatDateTime(sample, "en", "date");

    assert.equal(typeof result, "string");
    assert.match(result, /2026/);
  });

  it("falls back safely for unknown locale/format", () => {
    const result = formatDateTime(
      sample,
      "xx" as "pl",
      "unknown" as "medium",
    );

    assert.equal(typeof result, "string");
    assert.match(result, /2026/);
  });
});
