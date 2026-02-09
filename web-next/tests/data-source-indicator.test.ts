import assert from "node:assert/strict";
import { describe, it } from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  DataSourceIndicator,
  calculateDataSourceStatus,
} from "@/components/strategy/data-source-indicator";

const STALE_THRESHOLD_MS = 60_000;

describe("calculateDataSourceStatus", () => {
  it("returns live when live data is available", () => {
    const status = calculateDataSourceStatus(true, false, null, STALE_THRESHOLD_MS);
    assert.equal(status, "live");
  });

  it("returns cache for fresh cached data", () => {
    const now = Date.now();
    const status = calculateDataSourceStatus(false, true, now - 30_000, STALE_THRESHOLD_MS);
    assert.equal(status, "cache");
  });

  it("returns stale for old cached data", () => {
    const now = Date.now();
    const status = calculateDataSourceStatus(false, true, now - 90_000, STALE_THRESHOLD_MS);
    assert.equal(status, "stale");
  });

  it("returns offline when there is no data", () => {
    const status = calculateDataSourceStatus(false, false, null, STALE_THRESHOLD_MS);
    assert.equal(status, "offline");
  });

  it("returns cache when cache exists without timestamp", () => {
    const status = calculateDataSourceStatus(false, true, null, STALE_THRESHOLD_MS);
    assert.equal(status, "cache");
  });
});

describe("DataSourceIndicator", () => {
  const globalRef = globalThis as { React?: typeof React };
  globalRef.React = React;
  it("renders badge label and icon for live status", () => {
    const html = renderToStaticMarkup(
      React.createElement(DataSourceIndicator, { status: "live" }),
    );

    assert.match(html, /Live/);
    assert.match(html, /🟢/);
  });

  it("renders relative timestamp only when timestamp is provided", () => {
    const now = Date.now();
    const withTimestamp = renderToStaticMarkup(
      React.createElement(DataSourceIndicator, {
        status: "cache",
        timestamp: now - 60_000,
      }),
    );
    const withoutTimestamp = renderToStaticMarkup(
      React.createElement(DataSourceIndicator, { status: "cache" }),
    );

    assert.match(withTimestamp, /text-hint/);
    assert.doesNotMatch(withoutTimestamp, /text-hint/);
  });
});
