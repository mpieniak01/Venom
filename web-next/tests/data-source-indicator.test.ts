import assert from "node:assert/strict";
import test from "node:test";

import { calculateDataSourceStatus } from "@/components/strategy/data-source-indicator";

const STALE_THRESHOLD_MS = 60000;

test("returns live when live data is available", () => {
  const status = calculateDataSourceStatus(true, false, null, STALE_THRESHOLD_MS);
  assert.equal(status, "live");
});

test("returns cache for fresh cached data", () => {
  const now = Date.now();
  const status = calculateDataSourceStatus(false, true, now - 30000, STALE_THRESHOLD_MS);
  assert.equal(status, "cache");
});

test("returns stale for outdated cache data", () => {
  const now = Date.now();
  const status = calculateDataSourceStatus(false, true, now - 90000, STALE_THRESHOLD_MS);
  assert.equal(status, "stale");
});

test("returns offline when no data is available", () => {
  const status = calculateDataSourceStatus(false, false, null, STALE_THRESHOLD_MS);
  assert.equal(status, "offline");
});

test("returns cache when timestamp is missing", () => {
  const status = calculateDataSourceStatus(false, true, null, STALE_THRESHOLD_MS);
  assert.equal(status, "cache");
});
