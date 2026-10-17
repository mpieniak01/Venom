"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { configHref, type useConfigNavigation } from "@/lib/config-navigation";
import { useIntegrationInventory } from "@/lib/integration-inventory";
import { Globe, Network, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import type { components } from "@/lib/generated/api-types";

import { IntegrationStatusDetails } from "./integration-status-details";
import { ConnectionFilterControls, IntegrationCard, IntegrationConnectionDetails, integrationConnections, matchesConnectionFilters, shouldShowConnection, stateColor, type ConnectionFilters } from "./integration-connections";
export { shouldShowConnection } from "./integration-connections";

type Integration = components["schemas"]["IntegrationEntry"];
export type ApiConnection = components["schemas"]["ApiConnection"];

/** Apply scope and environment visibility without inferring health from configuration. */
export function visibleIntegrations(entries: Integration[], scope: string, environmentOnly: boolean) {
  return entries.filter((entry) => (scope === "all" || entry.scope === scope)
    && (!environmentOnly || entry.scope === "internal" || entry.configuration === "configured" || (entry.configuration === "not_required" && entry.activation === "enabled")));
}

/** Keep a valid selection or choose a configured external integration before falling back. */
export function nextIntegrationSelection(entries: Integration[], previous: string | null) {
  return entries.some((entry) => entry.id === previous) ? previous : entries.find((entry) => entry.scope === "external" && entry.configuration === "configured")?.id ?? entries[0]?.id ?? null;
}

/** Translate capability evidence while distinguishing an empty list from unknown evidence. */
function capabilityLabels(capabilities: string[], t: ReturnType<typeof useTranslation>) {
  if (!capabilities.length) return t("config.navigation.noCapabilities");
  return capabilities.map((capability) => t(`config.integrations.capabilities.${capability}`)).join(" · ");
}

/** Allow only application-local panel paths with no query strings or external origins. */
function publicLink(path: string | null | undefined) {
  return path && /^\/[a-zA-Z0-9][a-zA-Z0-9/_-]*$/.test(path) ? path : null;
}

/** Browse shared inventory and existing integration details with optional URL navigation. */
export function ApiMap({ navigation }: Readonly<{ navigation?: ReturnType<typeof useConfigNavigation> }> = {}) {
  const t = useTranslation();
  const { data, loading, failed: inventoryFailed, refresh } = useIntegrationInventory();
  const [localSelectedId, setLocalSelectedId] = useState<string | null>(null);
  const [probeFailed, setProbeFailed] = useState(false);
  const [probing, setProbing] = useState(false);
  const probeRequest = useRef<AbortController | null>(null);
  const [localScope, setLocalScope] = useState("all");
  const [localEnvironmentOnly, setLocalEnvironmentOnly] = useState(true);
  const [localQuery, setLocalQuery] = useState("");
  const [localFilters, setLocalFilters] = useState<ConnectionFilters>({ source: "all", status: "all", protocol: "all" });
  const filters: ConnectionFilters = navigation ?? localFilters;
  const setFilter = (field: keyof ConnectionFilters, value: string) => navigation ? navigation.navigate({ [field]: value }) : setLocalFilters((previous) => ({ ...previous, [field]: value }));
  const selectedId = navigation ? navigation.integration : localSelectedId;
  const scope = navigation?.scope ?? localScope;
  const environmentOnly = navigation ? navigation.visibility === "environment" : localEnvironmentOnly;
  const query = navigation?.query ?? localQuery;
  const setSelectedId = (integration: string) => navigation ? navigation.navigate({ integration, resource: null }) : setLocalSelectedId(integration);
  const setScope = (value: string) => navigation ? navigation.navigate({ scope: value as "all" | "internal" | "external" }) : setLocalScope(value);
  const setEnvironmentOnly = (value: boolean) => navigation ? navigation.navigate({ visibility: value ? "environment" : "all" }) : setLocalEnvironmentOnly(value);
  const setQuery = (value: string) => navigation ? navigation.navigate({ query: value }, true) : setLocalQuery(value);
  const failed = inventoryFailed || probeFailed;
  useEffect(() => () => probeRequest.current?.abort(), []);

  const checkVast = async () => {
    if (probing || loading) return;
    const controller = new AbortController();
    probeRequest.current = controller;
    setProbing(true);
    const timer = setTimeout(() => controller.abort(), 7000);
    try {
      const response = await fetch("/api/v1/system/integrations/vast/probe", { method: "POST", signal: controller.signal });
      if (!response.ok) throw new Error("probe_failed");
      setProbeFailed(false);
      await refresh();
    } catch {
      if (!controller.signal.aborted) setProbeFailed(true);
    } finally {
      clearTimeout(timer);
      probeRequest.current = null;
      setProbing(false);
    }
  };

  const connections = useMemo(() => [...(data?.internal_connections ?? []), ...(data?.external_connections ?? [])], [data]);
  const entries = useMemo(() => data?.integrations ?? [], [data]);
  const filtered = useMemo(() => visibleIntegrations(entries, scope, environmentOnly).filter((entry) =>
    [entry.label, entry.id, ...(entry.configuration_keys ?? []), ...integrationConnections(entry, connections).map((connection) => connection.description ?? "")].join(" ").toLowerCase().includes(query.toLowerCase().trim()) && matchesConnectionFilters(entry, connections, filters)), [entries, scope, environmentOnly, query, connections, filters]);
  const effectiveId = selectedId ?? nextIntegrationSelection(filtered, null);
  const selected = entries.find((entry) => entry.id === effectiveId);
  const selectionMissing = Boolean(data && selectedId && !selected);
  const selectionFiltered = Boolean(selected && !filtered.some((entry) => entry.id === selected.id));
  const declaredPanel = publicLink(selected?.panel_path);
  const panel = declaredPanel === "/config" ? configHref({ tab: "parameters", parameter: selected?.configuration_keys?.[0] ?? null, query: "" }, navigation?.search) : declaredPanel;
  const selectedConnections = selected ? integrationConnections(selected, connections).filter((connection) => shouldShowConnection(connection, filters)) : [];

  return (
    <section className="space-y-4" aria-busy={loading} aria-label={t("config.apiMap.title")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-theme-muted">{t("config.integrations.description")}</p>
        <Button variant="secondary" size="sm" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw className="h-4 w-4" />{t(loading ? "config.integrations.refreshing" : "config.apiMap.refresh")}
        </Button>
      </div>
      {failed && <p role="alert" className="rounded-lg border border-amber-500/40 p-3 text-[color:var(--badge-warning-text)]">{t(data ? "config.integrations.refreshFailed" : "config.apiMap.errorLoading")}</p>}
      <div className="grid grid-cols-2 items-end gap-3 xl:grid-cols-[minmax(180px,1.3fr)_repeat(5,minmax(100px,1fr))]">
        <label className="col-span-2 flex min-w-0 flex-col gap-1 text-xs text-theme-muted xl:col-span-1">
          {t("config.navigation.searchIntegrations")}
          <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" maxLength={120} className="h-9 min-w-0 rounded-lg border border-theme bg-theme-overlay-strong px-2 text-sm text-theme-primary" />
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-theme-muted">
          {t("config.integrations.visibility")}
          <select className="h-9 min-w-0 rounded-lg border border-theme bg-theme-overlay-strong px-2 text-sm text-theme-primary" value={environmentOnly ? "environment" : "all"} onChange={(event) => setEnvironmentOnly(event.target.value === "environment")}>
            <option value="environment">{t("config.integrations.environment")}</option>
            <option value="all">{t("config.integrations.allKnown")}</option>
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-theme-muted">
          {t("config.apiMap.filters.type.label")}
          <select className="h-9 min-w-0 rounded-lg border border-theme bg-theme-overlay-strong px-2 text-sm text-theme-primary" value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="all">{t("config.apiMap.filters.type.all")}</option>
            <option value="internal">{t("config.integrations.internal")}</option>
            <option value="external">{t("config.integrations.external")}</option>
          </select>
        </label>
        <ConnectionFilterControls filters={filters} onChange={setFilter} />
      </div>
      {selectionMissing && <output className="text-sm text-theme-muted">{t("config.navigation.missingIntegration")}</output>}
      {selectionFiltered && <output className="text-sm text-theme-muted">{t("config.navigation.filteredIntegration")}</output>}
      {!data && <p className="text-theme-muted">{t(loading ? "config.integrations.loading" : "config.apiMap.noResults")}</p>}
      <div className="grid gap-4 lg:grid-cols-[minmax(300px,1fr)_minmax(0,1.15fr)]">
        <div className="max-h-[70vh] min-w-0 space-y-5 overflow-y-auto pr-2">
          {(["internal", "external"] as const).map((group) => {
            const rows = filtered.filter((entry) => entry.scope === group);
            return rows.length > 0 && <div key={group} className="space-y-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-theme-secondary">{group === "internal" ? <Network aria-hidden="true" className="h-4 w-4 text-emerald-400" /> : <Globe aria-hidden="true" className="h-4 w-4 text-blue-400" />}{t(`config.integrations.${group}`)} · {rows.length}</h3>
              {rows.map((entry) => <IntegrationCard key={entry.id} entry={entry} connections={connections} filters={filters} selected={selected?.id === entry.id} onClick={() => setSelectedId(entry.id)} />)}
            </div>;
          })}
          {data && filtered.length === 0 && <p>{t("config.apiMap.noResults")}</p>}
        </div>
        {selected && <div className="glass-panel min-w-0 self-start space-y-5 rounded-2xl border border-theme p-5 lg:p-6">
          <h3 className="heading-h2 text-xl font-semibold">{selected.label}</h3>
          <IntegrationStatusDetails entry={selected} generatedAt={data?.generated_at} />
          {(selected.capabilities ?? []).length > 0 && <div><h4 className="font-medium">{t("config.integrations.capabilitiesTitle")}</h4><ul className="list-disc pl-5 text-sm text-theme-muted">{(selected.capabilities ?? []).map((capability) => <li key={capability}>{t(`config.integrations.capabilities.${capability}`)}</li>)}</ul></div>}
          {(selected.configuration_keys ?? []).length > 0 && <div><h4 className="font-medium">{t("config.integrations.configurationKeys")}</h4><p className="break-words text-xs text-theme-muted">{(selected.configuration_keys ?? []).map((key) => <Link className="mr-3 inline-block underline underline-offset-4" key={key} href={configHref({ tab: "parameters", parameter: key, query: "" }, navigation?.search)}>{key}</Link>)}</p></div>}
          <div>
            <h4 className="font-medium">{t("config.integrations.resources")}</h4>
            {selected.resource_support === "not_applicable" ? <p className="text-sm text-theme-muted">{t("config.integrations.notApplicable")}</p> : <p className="text-sm text-theme-muted">{t("config.integrations.total")}: {selected.resource_count ?? t("config.integrations.unknown")} · {t("config.integrations.active")}: {selected.active_resource_count ?? t("config.integrations.unknown")}</p>}
            {selected.resource_support !== "not_applicable" && !selected.resources_complete && <p className="text-xs text-[color:var(--badge-warning-text)]">{t("config.integrations.partialResources")}</p>}
            <ul className="mt-2 space-y-2">{(selected.resources ?? []).map((resource) => <li key={resource.id} className="rounded-lg border border-theme p-2 text-sm">
              <span className="font-medium">{resource.label}</span> · {t(`config.integrations.resourceKinds.${resource.kind}`)} · <span className={stateColor(resource.state)}>{t(`config.integrations.states.${resource.state}`)}</span>
              <p className="text-xs text-theme-muted">{resource.observed_at ? new Date(resource.observed_at).toLocaleString() : t("config.integrations.unknown")}</p>
              {resource.mode && <p className="text-xs">{t("config.navigation.deviceMode")}: {t(`config.navigation.modes.${resource.mode}`)}{resource.selected ? ` · ${t("config.navigation.selectedDevice")}` : ""}</p>}
              {resource.kind === "robot" && <div className="mt-2 space-y-1 text-xs text-theme-muted">
                <p>{t("config.integrations.configuration")}: {t(`config.integrations.configurationStates.${resource.configuration}`)}</p>
                <p>{t("config.integrations.evidence")}: {t(`config.integrations.sources.${resource.source}`)}</p>
                <p>{t(`config.integrations.reasons.${resource.reason_code}`)}</p>
                {(["supported", "reported", "available"] as const).map((kind) => {
                  const capabilities = resource[`${kind}_capabilities`];
                  return <p key={kind}>{t(`config.navigation.${kind}Capabilities`)}: {capabilities == null ? t("config.integrations.unknown") : capabilityLabels(capabilities, t)}</p>;
                })}
              </div>}
            </li>)}</ul>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {selected.id === "core:vast" && selected.can_probe && <Button variant="secondary" size="sm" disabled={probing || loading} onClick={() => void checkVast()}>{t(probing ? "config.integrations.probing" : "config.integrations.probe")}</Button>}
            {panel && <a className="underline underline-offset-4" href={panel}>{t("config.integrations.openPanel")}</a>}
            {(selected.access ?? []).includes("cli") && <span>{t("config.integrations.cliAvailable")}</span>}
            {selected.documentation_url === "https://github.com/mpieniak01/Venom/blob/main/docs/integrations/vast.md" && <a className="underline underline-offset-4" href={selected.documentation_url} target="_blank" rel="noreferrer">{t("config.integrations.documentation")}</a>}
          </div>
          <IntegrationConnectionDetails connections={selectedConnections} />
        </div>}
      </div>
      <p className="text-xs text-theme-muted">{t("config.integrations.safetyNote")}</p>
    </section>
  );
}
