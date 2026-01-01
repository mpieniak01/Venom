import assert from "node:assert/strict";

import { calculateDataSourceStatus } from "@/components/strategy/data-source-indicator";

const STALE_THRESHOLD_MS = 60000;

// Test: Dane live dostępne
const liveStatus = calculateDataSourceStatus(true, false, null, STALE_THRESHOLD_MS);
assert.equal(liveStatus, "live", "Powinno zwrócić 'live' gdy dane live są dostępne");

// Test: Dane cache dostępne (świeże)
const now = Date.now();
const cacheStatus = calculateDataSourceStatus(false, true, now - 30000, STALE_THRESHOLD_MS);
assert.equal(cacheStatus, "cache", "Powinno zwrócić 'cache' gdy dane cache są świeże");

// Test: Przestarzałe dane cache
const staleStatus = calculateDataSourceStatus(false, true, now - 90000, STALE_THRESHOLD_MS);
assert.equal(staleStatus, "stale", "Powinno zwrócić 'stale' gdy dane cache są stare");

// Test: Brak danych
const offlineStatus = calculateDataSourceStatus(false, false, null, STALE_THRESHOLD_MS);
assert.equal(offlineStatus, "offline", "Powinno zwrócić 'offline' gdy brak danych");

// Test: Cache bez timestampu
const cacheNoTimestamp = calculateDataSourceStatus(false, true, null, STALE_THRESHOLD_MS);
assert.equal(cacheNoTimestamp, "cache", "Powinno zwrócić 'cache' gdy brak timestampu");

console.log("✅ Wszystkie testy wskaźnika źródła danych przeszły!");
