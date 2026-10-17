import type { Integration } from "./integration-inventory";

export type Resource = NonNullable<Integration["resources"]>[number];
export type TopologyNode = {
  id: string;
  position: { x: number; y: number };
  data: { entry?: Integration; resource?: Resource; coreCount?: number };
};
export type TopologyEdge = { id: string; source: string; target: string; sourceHandle?: string };
export const isCoreApi = (entry: Integration) => entry.scope === "internal" && entry.kind === "api";
export const integrationNodeId = (id: string) => `integration:${encodeURIComponent(id)}`;
export const resourceNodeId = (parent: string, id: string) => `resource:${encodeURIComponent(parent)}:${encodeURIComponent(id)}`;

export function topologyEntries(entries: Integration[], visibility: string) {
  return entries.filter((entry) => visibility === "all" || entry.scope === "internal" || entry.configuration === "configured" || (entry.configuration === "not_required" && entry.activation === "enabled"));
}

// Only inventory nesting establishes ownership. Labels and legacy connection names never do.
export function buildIntegrationTopology(entries: Integration[], coreExpanded = false, resourceLimits: Record<string, number> = {}) {
  const nodes: TopologyNode[] = [{ id: "venom:root", position: { x: 0, y: 0 }, data: {} }];
  const edges: TopologyEdge[] = [];
  const core = entries.filter(isCoreApi);
  if (core.length && !coreExpanded) {
    nodes.push({ id: "venom:core", position: { x: -340, y: 0 }, data: { coreCount: core.length } });
    edges.push({ id: "edge:core", source: "venom:root", sourceHandle: "left", target: "venom:core" });
  }
  const rows = entries.filter((entry) => coreExpanded || !isCoreApi(entry)).toSorted((a, b) => a.id.localeCompare(b.id));
  const offsets = { local: core.length && !coreExpanded ? 180 : 0, cloud: 0 };
  for (const entry of rows) {
    const side = entry.location === "cloud" ? "cloud" : "local";
    const direction = side === "cloud" ? 1 : -1;
    const y = offsets[side];
    const id = integrationNodeId(entry.id);
    nodes.push({ id, position: { x: direction * 340, y }, data: { entry } });
    edges.push({ id: `edge:${id}`, source: "venom:root", sourceHandle: side === "cloud" ? "right" : "left", target: id });
    const resources = (entry.resources ?? []).toSorted((a, b) => a.id.localeCompare(b.id)).slice(0, resourceLimits[entry.id] ?? 4);
    resources.forEach((resource, index) => {
      const resourceId = resourceNodeId(entry.id, resource.id);
      nodes.push({ id: resourceId, position: { x: direction * 680, y: y + index * 180 }, data: { entry, resource } });
      edges.push({ id: `edge:${resourceId}`, source: id, target: resourceId });
    });
    offsets[side] += Math.max(1, resources.length) * 180;
  }
  nodes[0].position.y = Math.max(0, Math.max(offsets.local, offsets.cloud) / 2 - 90);
  return { nodes, edges };
}

export function resourceCountKey(entry: Integration) {
  if (entry.resource_support === "not_applicable") return "config.integrations.notApplicable";
  if (!entry.observed_at || !Number.isFinite(Date.parse(entry.observed_at)) || entry.state === "stale" || entry.resource_count == null) return "config.topology.notObserved";
  if (!entry.resources_complete) return "config.integrations.partialResources";
  return null;
}
