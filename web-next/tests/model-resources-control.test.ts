import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ModelResourcesControl } from "../components/models/model-resources-control";

const t = (key: string) => key;
const memory = { rss_mib: 400, gpu: [{ index: 0, used_mib: 1000, total_mib: 12000 }] };

describe("global model memory control", () => {
  it("exposes global release and observed RAM/VRAM without claiming success", () => {
    const html = renderToStaticMarkup(React.createElement(ModelResourcesControl, {
      releasing: false, memory, result: null, error: null, onRelease: async () => {}, t,
    }));
    assert.match(html, /release-all-models/);
    assert.match(html, /1000/);
    assert.match(html, /12000/);
    assert.match(html, /400/);
    assert.doesNotMatch(html, /models.resources.released/);
  });
  it("disables duplicate requests and distinguishes partial failure from success", () => {
    const html = renderToStaticMarkup(React.createElement(ModelResourcesControl, {
      releasing: true, memory, result: null, error: "partial release", onRelease: async () => {}, t,
    }));
    assert.match(html, /disabled/);
    assert.match(html, /models.resources.releasing/);
    assert.match(html, /partial release/);
    assert.doesNotMatch(html, /models.resources.released/);
  });
  it("shows the measured post-release values, not a fabricated zero", () => {
    const html = renderToStaticMarkup(React.createElement(ModelResourcesControl, {
      releasing: false, memory, error: null, onRelease: async () => {}, t,
      result: { status: "success", released: true, memory_before: memory,
        memory_after: { ...memory, gpu: [{ index: 0, used_mib: 300, total_mib: 12000 }] }, runtimes: [] },
    }));
    assert.match(html, /300/);
    assert.match(html, /models.resources.released/);
  });
});
