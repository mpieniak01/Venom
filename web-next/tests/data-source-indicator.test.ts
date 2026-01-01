import assert from "node:assert/strict";

import { calculateDataSourceStatus } from "@/components/strategy/data-source-indicator";

// Test: Live data available
const liveStatus = calculateDataSourceStatus(true, false, null, 60000);
assert.equal(liveStatus, "live", "Should return 'live' when live data is available");

// Test: Cache data available (not stale)
const now = Date.now();
const cacheStatus = calculateDataSourceStatus(false, true, now - 30000, 60000);
assert.equal(cacheStatus, "cache", "Should return 'cache' when cached data is fresh");

// Test: Stale cache data
const staleStatus = calculateDataSourceStatus(false, true, now - 90000, 60000);
assert.equal(staleStatus, "stale", "Should return 'stale' when cached data is old");

// Test: No data available
const offlineStatus = calculateDataSourceStatus(false, false, null, 60000);
assert.equal(offlineStatus, "offline", "Should return 'offline' when no data is available");

// Test: Cache without timestamp
const cacheNoTimestamp = calculateDataSourceStatus(false, true, null, 60000);
assert.equal(cacheNoTimestamp, "cache", "Should return 'cache' when no timestamp is available");

console.log("✅ All data source indicator tests passed!");
