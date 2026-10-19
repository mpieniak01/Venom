import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { configHref, parseConfigNavigation } from "../lib/config-navigation";

describe("configuration navigation", () => {
  it("accepts old API map and section links, without accepting prototype properties", () => {
    assert.equal(parseConfigNavigation("?tab=apiMap").tab, "integrations");
    assert.equal(parseConfigNavigation("?section=parameters").tab, "parameters");
    for (const tab of ["removed", "__proto__", "constructor"]) {
      assert.equal(parseConfigNavigation(`?tab=${tab}`).tab, "services");
      assert.equal(parseConfigNavigation(`?tab=${tab}`).invalidTab, true);
    }
  });
  it("retains selection and unrelated URL state when navigating to parameters and back", () => {
    const url = configHref({ tab: "parameters", parameter: "OPENAI_API_KEY", query: "" }, "?tab=integrations&integration=core%3Aopenai&scope=external&visibility=all&trace=1");
    const state = parseConfigNavigation(url.slice(url.indexOf("?")));
    assert.equal(state.integration, "core:openai");
    assert.equal(state.parameter, "OPENAI_API_KEY");
    assert.equal(state.scope, "external");
    assert.ok(url.includes("trace=1"));
    assert.equal(configHref({ tab: "integrations", parameter: null }, url.slice(url.indexOf("?"))).includes("parameter="), false);
  });
  it("bounds user input and keeps parameter values out of URLs", () => {
    const state = parseConfigNavigation(`?q=${"a".repeat(200)}&scope=bad&visibility=bad&parameter=secret%3Dvalue`);
    assert.equal(state.query.length, 120);
    assert.equal(state.parameter, null);
    assert.equal(state.scope, "all");
    assert.equal(state.visibility, "environment");
  });
  it("preserves the resource allowlist when simplifying its regex", () => {
    for (const resource of ["core:model", "path/to-file.ext", "a_b-1", "a".repeat(200)]) {
      assert.equal(parseConfigNavigation(`?resource=${encodeURIComponent(resource)}`).resource, resource);
    }
    for (const resource of ["/leading", "bad\\path", "with space", "a".repeat(201)]) {
      assert.equal(parseConfigNavigation(`?resource=${encodeURIComponent(resource)}`).resource, null);
    }
  });

});
