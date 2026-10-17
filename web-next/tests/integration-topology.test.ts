import assert from "node:assert/strict";
import { it } from "node:test";
import { buildIntegrationTopology, resourceCountKey, resourceNodeId, topologyEntries } from "../lib/integration-topology";
import type { Integration } from "../lib/integration-inventory";
import { parseConfigNavigation, configHref } from "../lib/config-navigation";
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
