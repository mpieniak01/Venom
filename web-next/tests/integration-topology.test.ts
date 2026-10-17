import assert from "node:assert/strict";
import { it } from "node:test";
import { buildIntegrationTopology, resourceCountKey, resourceNodeId, visibleTopologyResources, topologyResourceLimits, topologyEntries } from "../lib/integration-topology";
import type { Integration } from "../lib/integration-inventory";
import { parseConfigNavigation, configHref } from "../lib/config-navigation";
/** Build independent inventory entries with explicit overrides for domain regressions. */
const entry = (id: string, overrides: Partial<Integration> = {}): Integration => ({ id, label: "Same label", scope: "external", location: "local", kind: "module", state: "unverified", configuration: "configured", activation: "enabled", connectivity: "unknown", source: "configuration", reason_code: "not_probed", resource_support: "supported", can_probe: false, resources_complete: false, ...overrides });
const resource = { id: "same", label: "Same label", kind: "robot", state: "offline", configuration: "configured", selected: true, source: "configuration", reason_code: "not_observed" } as const;
it("builds ownership from stable IDs including duplicate labels and offline resources", () => {
  const graph = buildIntegrationTopology([entry("rider", { resources: [resource] }), entry("other", { resources: [resource], location: "cloud" })]);
  assert.equal(graph.nodes.length, 5);
  assert.equal(new Set(graph.nodes.map((node) => node.id)).size, 5);
  assert.equal(graph.edges.find((edge) => edge.target === resourceNodeId("rider", "same"))?.source, "integration:rider");
  assert.equal(graph.nodes.find((node) => node.id === "integration:rider")?.position.x, -340);
  assert.equal(graph.nodes.find((node) => node.id === "integration:other")?.position.x, 340);
  assert.notEqual(resourceNodeId("a:b", "c"), resourceNodeId("a", "b:c"));
});
it("keeps positions stable across status changes and input order", () => {
  const first = [entry("b"), entry("a", { resources: [resource] })];
  const positions = (rows: Integration[]) => buildIntegrationTopology(rows).nodes.map(({ id, position }) => ({ id, position }));
  assert.deepEqual(positions(first), positions([...first].reverse().map((row) => ({ ...row, connectivity: "down", observed_at: new Date().toISOString() }))));
});
it("handles empty inventory, optional modules, core grouping and bounded expansion", () => {
  assert.equal(buildIntegrationTopology([]).nodes.length, 1);
  const rows = [entry("core", { scope: "internal", kind: "api" }), entry("rider", { resources: Array.from({ length: 64 }, (_, i) => ({ ...resource, id: String(i) })) })];
  assert.equal(buildIntegrationTopology(rows).nodes.length, 7);
  assert.equal(buildIntegrationTopology(rows, true, { rider: 12 }).nodes.length, 15);
  assert.equal(topologyEntries([entry("missing", { configuration: "unconfigured" })], "environment").length, 0);
  assert.equal(topologyEntries([entry("missing", { configuration: "unconfigured" })], "all").length, 1);
});
it("distinguishes missing observation, incomplete inventory and an observed zero", () => {
  assert.equal(resourceCountKey(entry("vast", { resource_count: 0, resources_complete: true })), "config.topology.notObserved");
  assert.equal(resourceCountKey(entry("vast", { resource_count: 0, observed_at: "2026-10-17T10:00:00Z" })), "config.integrations.partialResources");
  assert.equal(resourceCountKey(entry("vast", { resource_count: 0, resources_complete: true, observed_at: "2026-10-17T10:00:00Z" })), null);
});
it("retains resource selection across topology and existing tabs and bounds URL input", () => {
  const search = "?tab=topology&integration=rider&resource=device&trace=1";
  assert.equal(parseConfigNavigation(search).tab, "topology");
  assert.equal(parseConfigNavigation(search).resource, "device");
  const href = configHref({ tab: "integrations" }, search);
  assert.ok(href.includes("resource=device"));
  assert.ok(href.includes("trace=1"));
  assert.equal(parseConfigNavigation(`?resource=${"a".repeat(300)}`).resource, null);
  assert.equal(parseConfigNavigation("?resource=../private").resource, null);
});

it("keeps resource pages identical between graph and text list regardless of inventory order", () => {
  const integration = entry("rider", { resources: ["3", "2", "11", "10", "1", "0"].map((id) => ({ ...resource, id })) });
  const page = visibleTopologyResources(integration);
  assert.deepEqual(page.map((item) => item.id), ["0", "1", "10", "11"]);
  const graphResources = buildIntegrationTopology([integration]).nodes.flatMap((node) => node.data.resource ? [node.data.resource.id] : []);
  assert.deepEqual(graphResources, page.map((item) => item.id));
  assert.equal(visibleTopologyResources(integration, 12).length, 6);
  assert.deepEqual(integration.resources?.map((item) => item.id), ["3", "2", "11", "10", "1", "0"]);
});

it("restores resources beyond the initial page without changing other owners or manual expansion", () => {
  const rows = [entry("rider", { resources: Array.from({ length: 64 }, (_, index) => ({ ...resource, id: String(index) })) })];
  const limits = topologyResourceLimits(rows, { other: 12 }, "rider", "63");
  const page = visibleTopologyResources(rows[0], limits.rider);
  assert.ok(page.some((item) => item.id === "63"));
  assert.equal(limits.other, 12);
  assert.ok(buildIntegrationTopology(rows, false, limits).nodes.some((node) => node.data.resource?.id === "63"));
  assert.equal(topologyResourceLimits(rows, { rider: 64 }, "rider", "0").rider, 64);
  assert.deepEqual(topologyResourceLimits(rows, {}, "rider", "removed"), {});
});
it("retains namespaced worker IDs containing slashes across URL reloads", () => {
  const href = configHref({ tab: "topology", integration: "core:nexus", resource: "nexus:worker/1" });
  assert.equal(parseConfigNavigation(href.slice(href.indexOf("?"))).resource, "nexus:worker/1");
  assert.equal(parseConfigNavigation("?resource=../private").resource, null);
});
