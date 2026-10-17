"use client";

import "@xyflow/react/dist/style.css";
import { memo, useMemo, useState } from "react";
import Link from "next/link";
import { ReactFlow, Background, Controls, Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { useTranslation } from "@/lib/i18n";
import { configHref, type useConfigNavigation } from "@/lib/config-navigation";
import { useIntegrationInventory } from "@/lib/integration-inventory";
import { buildIntegrationTopology, isCoreApi, topologyEntries, visibleTopologyResources, resourceCountKey, type TopologyNode } from "@/lib/integration-topology";
import { Button } from "@/components/ui/button";
import { IntegrationStatusDetails } from "./integration-status-details";
import { stateColor } from "./integration-connections";

/** Render a stable read-only inventory card with independent configuration and connectivity. */
const TopologyCard = memo(function TopologyCard({ data }: NodeProps<Node<TopologyNode["data"]>>) {
  const t = useTranslation();
  const { entry, resource, coreCount } = data;
  return <div className="h-[150px] w-[260px] overflow-hidden rounded-xl border border-theme bg-theme-overlay-strong p-3 text-theme-primary">
    {(entry || coreCount != null) && <Handle type="target" position={entry?.location === "cloud" ? Position.Left : Position.Right} isConnectable={false} />}
    <strong className="line-clamp-2 break-words">{resource?.label ?? entry?.label ?? (coreCount == null ? "Venom" : `${t("config.topology.core")} · ${coreCount}`)}</strong>
    {entry && <div className="mt-2 space-y-1 text-xs">
      <p>{resource ? t(`config.integrations.resourceKinds.${resource.kind}`) : t(`config.integrations.locations.${entry.location}`)}</p>
      <p>{t("config.integrations.configuration")}: {t(`config.integrations.configurationStates.${resource?.configuration ?? entry.configuration}`)}</p>
      {!resource && <p>{t("config.integrations.activation")}: {t(`config.integrations.activationStates.${entry.activation}`)}</p>}
      <p className={stateColor(resource?.state ?? entry.connectivity)}>{t("config.integrations.connectivity")}: {resource ? t(`config.integrations.states.${resource.state}`) : t(`config.apiMap.filters.status.${entry.connectivity}`)}</p>
      {resource?.selected && <p>{t("config.navigation.selectedDevice")}</p>}
    </div>}
    {entry || coreCount != null ? <Handle type="source" position={entry?.location === "cloud" ? Position.Right : Position.Left} isConnectable={false} /> : <><Handle id="left" type="source" position={Position.Left} isConnectable={false} /><Handle id="right" type="source" position={Position.Right} isConnectable={false} /></>}
  </div>;
}, (previous, next) => {
  const a = previous.data;
  const b = next.data;
  return a.coreCount === b.coreCount
    && a.entry?.label === b.entry?.label
    && a.entry?.location === b.entry?.location
    && a.entry?.configuration === b.entry?.configuration
    && a.entry?.activation === b.entry?.activation
    && a.entry?.connectivity === b.entry?.connectivity
    && a.resource?.label === b.resource?.label
    && a.resource?.kind === b.resource?.kind
    && a.resource?.configuration === b.resource?.configuration
    && a.resource?.state === b.resource?.state
    && a.resource?.selected === b.resource?.selected;
});
const nodeTypes = { topology: TopologyCard };

/** Display inventory ownership with shared resource pages, URL selection and a keyboard-accessible list. */
export function IntegrationTopology({ navigation }: Readonly<{ navigation: ReturnType<typeof useConfigNavigation> }>) {
  const t = useTranslation();
  const { data, failed, loading } = useIntegrationInventory();
  const [coreExpanded, setCoreExpanded] = useState(false);
  const [limits, setLimits] = useState<Record<string, number>>({});
  const entries = useMemo(() => topologyEntries(data?.integrations ?? [], navigation.visibility), [data, navigation.visibility]);
  const selected = data?.integrations?.find((entry) => entry.id === navigation.integration);
  const resource = selected?.resources?.find((item) => item.id === navigation.resource);
  const hierarchy = useMemo(() => {
    const graph = buildIntegrationTopology(entries, coreExpanded, limits);
    return { edges: graph.edges, nodes: graph.nodes.map((node) => ({ ...node, type: "topology", selected: node.data.entry?.id === navigation.integration && (node.data.resource?.id ?? null) === navigation.resource })) };
  }, [entries, coreExpanded, limits, navigation.integration, navigation.resource]);
  const select = (node: TopologyNode) => {
    if (node.data.coreCount != null) { setCoreExpanded(true); return; }
    navigation.navigate({ integration: node.data.entry?.id ?? null, resource: node.data.resource?.id ?? null });
  };
  const missing = data && ((navigation.integration && !selected) || (navigation.resource && !resource));
  const countKey = selected ? resourceCountKey(selected) : null;
  return <section className="min-w-0 space-y-4" aria-label={t("config.topology.title")} aria-busy={loading}>
    <p className="text-sm text-theme-muted">{t("config.topology.legend")}</p>
    <div className="flex flex-wrap items-center gap-3">
      <label>{t("config.integrations.visibility")} <select className="rounded border border-theme bg-theme-overlay-strong p-2" value={navigation.visibility} onChange={(event) => navigation.navigate({ visibility: event.target.value === "all" ? "all" : "environment" })}>
        <option value="environment">{t("config.integrations.environment")}</option><option value="all">{t("config.integrations.allKnown")}</option>
      </select></label>
      <Button variant="secondary" onClick={() => setCoreExpanded((value) => !value)} aria-expanded={coreExpanded}>{t("config.topology.core")} · {entries.filter(isCoreApi).length}</Button>
    </div>
    {failed && <p role="alert">{t(data ? "config.integrations.refreshFailed" : "config.apiMap.errorLoading")}</p>}
    {!data && <p>{t(loading ? "config.integrations.loading" : "config.apiMap.noResults")}</p>}
    {missing && <output className="block">{t("config.topology.missing")}</output>}
    <div className={selected ? "grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]" : "min-w-0"}>
      <div className="h-[560px] min-w-0 overflow-hidden rounded-xl border border-theme" data-testid="integration-topology-canvas" onKeyDownCapture={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const element = (event.target as HTMLElement).closest<HTMLElement>(".react-flow__node");
        const node = hierarchy.nodes.find((item) => item.id === element?.dataset.id);
        if (node) { event.preventDefault(); event.stopPropagation(); select(node); }
      }}>
        <ReactFlow key={data ? "inventory" : "pending"} nodes={hierarchy.nodes} edges={hierarchy.edges.map((edge) => ({ ...edge, selectable: false, focusable: false }))} nodeTypes={nodeTypes} onNodeClick={(_, node) => select(node)} fitView minZoom={0.15} maxZoom={1.5} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} zoomOnScroll={false} panOnScroll={false} preventScrolling={false} ariaLabelConfig={{ "controls.ariaLabel": t("config.topology.controls"), "controls.zoomIn.ariaLabel": t("config.topology.zoomIn"), "controls.zoomOut.ariaLabel": t("config.topology.zoomOut"), "controls.fitView.ariaLabel": t("config.topology.fitView"), "node.a11yDescription.default": t("config.topology.keyboard"), "node.a11yDescription.keyboardDisabled": t("config.topology.keyboard"), "handle.ariaLabel": t("config.topology.handle") }} proOptions={{ hideAttribution: true }}>
          <Background /><Controls showInteractive={false} className="[&>button]:border-theme [&>button]:bg-theme-overlay-strong [&>button]:text-theme-primary" />
        </ReactFlow>
      </div>
      {selected && <aside className="min-w-0 space-y-3 rounded-xl border border-theme p-4">
        <h3 className="break-words text-lg font-semibold">{resource?.label ?? selected.label}</h3>
        <IntegrationStatusDetails entry={selected} resource={resource} generatedAt={data?.generated_at} />
        <p>{t("config.integrations.resources")}: {countKey ? t(countKey) : selected.resource_count}</p>
        {resource?.mode && <p>{t("config.navigation.deviceMode")}: {t(`config.navigation.modes.${resource.mode}`)}</p>}
        {resource?.selected && <p>{t("config.navigation.selectedDevice")}</p>}
        <ul>{(resource ? [] : selected.capabilities ?? []).map((capability) => <li key={capability}>{t(`config.integrations.capabilities.${capability}`)}</li>)}</ul>
        <Link className="block underline" href={configHref({ tab: "integrations", query: "" }, navigation.search)}>{t("config.apiMap.title")}</Link>
        {(selected.configuration_keys ?? []).map((key) => <Link className="block break-all underline" key={key} href={configHref({ tab: "parameters", parameter: key, query: "" }, navigation.search)}>{key}</Link>)}
      </aside>}
    </div>
    <details className="rounded-xl border border-theme p-3" open>
      <summary>{t("config.topology.tree")}</summary>
      <ul className="space-y-3 pt-3">{entries.filter((entry) => coreExpanded || !isCoreApi(entry)).map((entry) => <li key={entry.id} data-testid={`topology-entry-${entry.id}`} className="min-w-0 break-words">
        <button className="text-left underline" aria-pressed={selected?.id === entry.id && !resource} onClick={() => navigation.navigate({ integration: entry.id, resource: null })}>{entry.label} · {t(`config.apiMap.filters.status.${entry.connectivity}`)}</button>
        <ul className="space-y-2 pl-4">{visibleTopologyResources(entry, limits[entry.id] ?? 4).map((item) => <li key={item.id}><button className="text-left underline" aria-pressed={selected?.id === entry.id && resource?.id === item.id} onClick={() => navigation.navigate({ integration: entry.id, resource: item.id })}>{item.label} · {t(`config.integrations.states.${item.state}`)}{item.selected ? ` · ${t("config.navigation.selectedDevice")}` : ""}</button></li>)}</ul>
        {(entry.resources?.length ?? 0) > (limits[entry.id] ?? 4) && <Button variant="ghost" onClick={() => setLimits((previous) => ({ ...previous, [entry.id]: (previous[entry.id] ?? 4) + 8 }))}>{t("config.topology.more")} ({entry.resources!.length})</Button>}
      </li>)}</ul>
    </details>
  </section>;
}
