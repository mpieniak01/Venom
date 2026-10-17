"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/generated/api-types";

type ApiMapResponse = components["schemas"]["ApiMapResponse"];
type Integration = components["schemas"]["IntegrationEntry"];
export type ApiConnection = components["schemas"]["ApiConnection"];

// Retained for existing API-map clients and filters.
export function shouldShowConnection(conn: ApiConnection, filters: { source: string; status: string; protocol: string }) {
  return (filters.source === "all" || conn.source_type === filters.source)
    && (filters.status === "all" || conn.status === filters.status)
    && (filters.protocol === "all" || conn.protocol === filters.protocol);
}

export function visibleIntegrations(entries: Integration[], scope: string, environmentOnly: boolean) {
  return entries.filter((entry) => (scope === "all" || entry.scope === scope)
    && (!environmentOnly || entry.scope === "internal" || entry.configuration === "configured" || (entry.configuration === "not_required" && entry.activation === "enabled")));
}

export function nextIntegrationSelection(entries: Integration[], previous: string | null) {
  return entries.some((entry) => entry.id === previous) ? previous : entries.find((entry) => entry.scope === "external" && entry.configuration === "configured")?.id ?? entries[0]?.id ?? null;
}

function stateColor(state: string) {
  if (state === "connected") return "text-[color:var(--badge-success-text)]";
  if (["unavailable", "degraded"].includes(state)) return "text-[color:var(--badge-danger-text)]";
  if (["unverified", "unconfigured", "stale"].includes(state)) return "text-[color:var(--badge-warning-text)]";
  return "text-theme-muted";
}

function publicLink(path: string | null | undefined) {
  return path && /^\/[a-zA-Z0-9][a-zA-Z0-9/_-]*$/.test(path) ? path : null;
}

export function ApiMap() {
  const t = useTranslation();
  const [data, setData] = useState<ApiMapResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [probing, setProbing] = useState(false);
  const probeRequest = useRef<AbortController | null>(null);
  const [scope, setScope] = useState("all");
  const [environmentOnly, setEnvironmentOnly] = useState(true);
  const activeRequest = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    if (activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    setLoading(true);
    try {
      const response = await fetch("/api/v1/system/api-map", { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error("api_map_unavailable");
      const result: ApiMapResponse = await response.json();
      if (!Array.isArray(result.integrations)) throw new Error("api_map_contract_unavailable");
      if (activeRequest.current !== controller) return;
      setData(result);
      setSelectedId((previous) => nextIntegrationSelection(result.integrations ?? [], previous));
      setFailed(false);
    } catch {
      if (activeRequest.current === controller) setFailed(true);
    } finally {
      clearTimeout(timeout);
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => { if (!document.hidden) void refresh(); }, 10000);
    return () => {
      clearInterval(timer);
      const request = activeRequest.current;
      activeRequest.current = null;
      request?.abort();
      probeRequest.current?.abort();
    };
  }, [refresh]);

  const checkVast = async () => {
    if (probing || loading) return;
    const controller = new AbortController();
    probeRequest.current = controller;
    setProbing(true);
    const timer = setTimeout(() => controller.abort(), 7000);
    try {
      const response = await fetch("/api/v1/system/integrations/vast/probe", { method: "POST", signal: controller.signal });
      if (!response.ok) throw new Error("probe_failed");
      await refresh();
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      clearTimeout(timer);
      probeRequest.current = null;
      setProbing(false);
    }
  };

  const entries = useMemo(() => data?.integrations ?? [], [data]);
  const filtered = useMemo(() => visibleIntegrations(entries, scope, environmentOnly), [entries, scope, environmentOnly]);
  const selected = filtered.find((entry) => entry.id === selectedId) ?? filtered[0];
  const panel = publicLink(selected?.panel_path);
  const methods = selected ? [...(data?.internal_connections ?? []), ...(data?.external_connections ?? [])]
    .find((connection) => connection.target_component === selected.label)?.methods ?? [] : [];

  return (
    <section className="space-y-4" aria-busy={loading} aria-label={t("config.apiMap.title")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-theme-muted">{t("config.integrations.description")}</p>
        <Button variant="secondary" size="sm" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw className="h-4 w-4" />{t(loading ? "config.integrations.refreshing" : "config.apiMap.refresh")}
        </Button>
      </div>
      {failed && <p role="alert" className="rounded-lg border border-amber-500/40 p-3 text-[color:var(--badge-warning-text)]">{t(data ? "config.integrations.refreshFailed" : "config.apiMap.errorLoading")}</p>}
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-sm">
          {t("config.integrations.visibility")}
          <select className="rounded-lg border border-theme bg-theme-overlay p-2" value={environmentOnly ? "environment" : "all"} onChange={(event) => setEnvironmentOnly(event.target.value === "environment")}>
            <option value="environment">{t("config.integrations.environment")}</option>
            <option value="all">{t("config.integrations.allKnown")}</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          {t("config.apiMap.filters.type.label")}
          <select className="rounded-lg border border-theme bg-theme-overlay p-2" value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="all">{t("config.apiMap.filters.type.all")}</option>
            <option value="internal">{t("config.integrations.internal")}</option>
            <option value="external">{t("config.integrations.external")}</option>
          </select>
        </label>
      </div>
      {!data && <p className="text-theme-muted">{t(loading ? "config.integrations.loading" : "config.apiMap.noResults")}</p>}
      <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_minmax(0,1.4fr)]">
        <div className="max-h-[65vh] space-y-5 overflow-y-auto pr-2">
          {(["external", "internal"] as const).map((group) => {
            const rows = filtered.filter((entry) => entry.scope === group);
            return rows.length > 0 && <div key={group} className="space-y-2">
              <h3 className="font-semibold">{t(`config.integrations.${group}`)} · {rows.length}</h3>
              {rows.map((entry) => <button key={entry.id} onClick={() => setSelectedId(entry.id)} aria-pressed={selected?.id === entry.id}
                className={cn("flex w-full items-start justify-between gap-3 rounded-xl border p-3 text-left", selected?.id === entry.id ? "border-emerald-500/50 bg-emerald-500/10" : "border-theme bg-theme-overlay")}>
                <span><span className="block font-medium">{entry.label}</span><span className="text-xs text-theme-muted">{t(`config.integrations.kinds.${entry.kind}`)}</span></span>
                <span className={cn("text-right text-xs", stateColor(entry.state ?? "unverified"))}>{t(`config.integrations.states.${entry.state}`)}</span>
              </button>)}
            </div>;
          })}
          {data && filtered.length === 0 && <p>{t("config.apiMap.noResults")}</p>}
        </div>
        {selected && <div className="min-w-0 self-start space-y-4 rounded-xl border border-theme p-4">
          <h3 className="text-lg font-semibold">{selected.label}</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-theme-muted">{t("config.integrations.configuration")}</dt><dd>{t(`config.integrations.configurationStates.${selected.configuration}`)}</dd>
            <dt className="text-theme-muted">{t("config.integrations.activation")}</dt><dd>{t(`config.integrations.activationStates.${selected.activation}`)}</dd>
            <dt className="text-theme-muted">{t("config.integrations.connectivity")}</dt><dd>{t(`config.apiMap.filters.status.${selected.connectivity}`)}</dd>
            <dt className="text-theme-muted">{t("config.integrations.location")}</dt><dd>{t(`config.integrations.locations.${selected.location}`)}</dd>
            <dt className="text-theme-muted">{t("config.integrations.evidence")}</dt><dd>{t(`config.integrations.sources.${selected.source}`)}</dd>
            <dt className="text-theme-muted">{t("config.integrations.observedAt")}</dt><dd>{selected.observed_at ? new Date(selected.observed_at).toLocaleString() : t("config.integrations.unknown")}</dd>
          </dl>
          <p className="rounded-lg bg-theme-overlay p-3 text-sm">{t(`config.integrations.reasons.${selected.reason_code}`)}</p>
          {(selected.capabilities ?? []).length > 0 && <div><h4 className="font-medium">{t("config.integrations.capabilitiesTitle")}</h4><ul className="list-disc pl-5 text-sm text-theme-muted">{(selected.capabilities ?? []).map((capability) => <li key={capability}>{t(`config.integrations.capabilities.${capability}`)}</li>)}</ul></div>}
          {(selected.configuration_keys ?? []).length > 0 && <div><h4 className="font-medium">{t("config.integrations.configurationKeys")}</h4><p className="break-words text-xs text-theme-muted">{(selected.configuration_keys ?? []).join(" · ")}</p></div>}
          <div>
            <h4 className="font-medium">{t("config.integrations.resources")}</h4>
            {selected.resource_support === "not_applicable" ? <p className="text-sm text-theme-muted">{t("config.integrations.notApplicable")}</p> : <p className="text-sm text-theme-muted">{t("config.integrations.total")}: {selected.resource_count ?? t("config.integrations.unknown")} · {t("config.integrations.active")}: {selected.active_resource_count ?? t("config.integrations.unknown")}</p>}
            {selected.resource_support !== "not_applicable" && !selected.resources_complete && <p className="text-xs text-[color:var(--badge-warning-text)]">{t("config.integrations.partialResources")}</p>}
            <ul className="mt-2 space-y-2">{(selected.resources ?? []).map((resource) => <li key={resource.id} className="rounded-lg border border-theme p-2 text-sm">
              <span className="font-medium">{resource.label}</span> · {t(`config.integrations.resourceKinds.${resource.kind}`)} · <span className={stateColor(resource.state)}>{t(`config.integrations.states.${resource.state}`)}</span>
              <p className="text-xs text-theme-muted">{resource.observed_at ? new Date(resource.observed_at).toLocaleString() : t("config.integrations.unknown")}</p>
            </li>)}</ul>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {selected.id === "core:vast" && selected.can_probe && <Button variant="secondary" size="sm" disabled={probing || loading} onClick={() => void checkVast()}>{t(probing ? "config.integrations.probing" : "config.integrations.probe")}</Button>}
            {panel && <a className="underline underline-offset-4" href={panel}>{t("config.integrations.openPanel")}</a>}
            {(selected.access ?? []).includes("cli") && <span>{t("config.integrations.cliAvailable")}</span>}
            {selected.documentation_url === "https://github.com/mpieniak01/Venom/blob/main/docs/integrations/vast.md" && <a className="underline underline-offset-4" href={selected.documentation_url} target="_blank" rel="noreferrer">{t("config.integrations.documentation")}</a>}
          </div>
          {methods.length > 0 && <details><summary className="cursor-pointer text-sm">{t("config.apiMap.methods")}</summary><ul className="mt-2 space-y-1 break-all font-mono text-xs">{methods.map((method) => <li key={method}>{method}</li>)}</ul></details>}
        </div>}
      </div>
      <p className="text-xs text-theme-muted">{t("config.integrations.safetyNote")}</p>
    </section>
  );
}
