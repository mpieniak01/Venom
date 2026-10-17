"use client";

import { ArrowRight, CheckCircle2, CircleHelp, Cloud, Code, Lock, Network, Server, Shield, TriangleAlert, XCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/generated/api-types";

type Integration = components["schemas"]["IntegrationEntry"];
export type ApiConnection = components["schemas"]["ApiConnection"];
export type ConnectionFilters = { source: string; status: string; protocol: string };

export function shouldShowConnection(connection: ApiConnection, filters: ConnectionFilters) {
  return (filters.source === "all" || connection.source_type === filters.source)
    && (filters.status === "all" || connection.status === filters.status)
    && (filters.protocol === "all" || connection.protocol === filters.protocol);
}

export function integrationConnections(entry: Integration, connections: ApiConnection[]) {
  return connections.filter((connection) => connection.target_component === entry.label);
}

export function matchesConnectionFilters(entry: Integration, connections: ApiConnection[], filters: ConnectionFilters) {
  const linked = integrationConnections(entry, connections);
  if (linked.length) return linked.some((connection) => shouldShowConnection(connection, filters));
  return filters.protocol === "all"
    && (filters.source === "all" || entry.location === filters.source)
    && (filters.status === "all" || entry.connectivity === filters.status);
}

export function stateColor(state: string) {
  if (["connected", "ok"].includes(state)) return "text-[color:var(--badge-success-text)]";
  if (["unavailable", "degraded", "offline", "down"].includes(state)) return "text-[color:var(--badge-danger-text)]";
  if (["unverified", "unconfigured", "stale"].includes(state)) return "text-[color:var(--badge-warning-text)]";
  return "text-theme-muted";
}

function StatusIcon({ status }: Readonly<{ status: string }>) {
  const Icon = { ok: CheckCircle2, connected: CheckCircle2, down: XCircle, unavailable: XCircle, degraded: TriangleAlert }[status] ?? CircleHelp;
  return <Icon aria-hidden="true" className={cn("h-4 w-4 shrink-0", stateColor(status))} />;
}

export function IntegrationCard({ entry, connections, selected, onClick }: Readonly<{ entry: Integration; connections: ApiConnection[]; selected: boolean; onClick: () => void }>) {
  const t = useTranslation();
  const connection = integrationConnections(entry, connections)[0];
  const Icon = entry.location === "cloud" ? Cloud : Server;
  return <button onClick={onClick} aria-pressed={selected}
    className={cn("w-full rounded-xl border p-4 text-left transition-colors hover:bg-theme-overlay", selected ? "border-emerald-500/50 bg-emerald-500/10 ring-1 ring-emerald-500/20" : "border-theme bg-theme-overlay")}>
    <span className="flex items-start gap-3">
      <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border", selected ? "border-emerald-500/30 bg-emerald-500/20" : "border-theme bg-theme-overlay-strong")}><Icon aria-hidden="true" className="h-4 w-4" /></span>
      <span className="min-w-0 flex-1 space-y-1">
        <span className="flex flex-wrap items-center gap-2 font-medium">{entry.label}{connection?.is_critical && <Shield aria-label={t("config.apiMap.legend.critical")} className="h-3.5 w-3.5 text-red-400" />}</span>
        <span className="block text-xs text-theme-muted">{connection?.description ?? t(`config.integrations.kinds.${entry.kind}`)}</span>
        <span className="flex flex-wrap gap-2 text-[11px] text-theme-muted"><span>{t(`config.integrations.locations.${entry.location}`)}</span>{connection && <span>{t(`config.apiMap.filters.protocol.${connection.protocol}`)}</span>}</span>
      </span>
      <span className="flex max-w-[40%] items-center gap-1.5 text-right text-xs"><StatusIcon status={entry.state} /><span className={stateColor(entry.state)}>{t(`config.integrations.states.${entry.state}`)}</span></span>
    </span>
  </button>;
}

export function IntegrationConnectionDetails({ connections }: Readonly<{ connections: ApiConnection[] }>) {
  const t = useTranslation();
  return <>{connections.map((connection) => <section key={[connection.source_component, connection.target_component, connection.protocol, connection.direction].join(":")} className="space-y-4 border-t border-theme pt-4">
    {connection.description && <p className="text-sm text-theme-muted">{connection.description}</p>}
    <p className="flex flex-wrap items-center gap-2 text-sm"><Network aria-hidden="true" className="h-4 w-4" />{connection.source_component}<ArrowRight aria-hidden="true" className="h-4 w-4" />{connection.target_component}</p>
    <dl className="grid grid-cols-2 gap-4 text-sm">
      <div><dt className="text-xs text-theme-muted">{t("config.apiMap.connection.protocol")}</dt><dd className="mt-1 font-mono">{t(`config.apiMap.filters.protocol.${connection.protocol}`)}</dd></div>
      <div><dt className="text-xs text-theme-muted">{t("config.apiMap.connection.auth")}</dt><dd className="mt-1 flex items-center gap-1"><Lock aria-hidden="true" className="h-3 w-3" />{t(`config.apiMap.auth.${connection.auth_type}`)}</dd></div>
      <div><dt className="text-xs text-theme-muted">{t("config.apiMap.connection.source")}</dt><dd className="mt-1">{t(`config.apiMap.filters.source.${connection.source_type}`)}</dd></div>
      <div><dt className="text-xs text-theme-muted">{t("config.integrations.direction")}</dt><dd className="mt-1">{t(`config.apiMap.legend.${connection.direction}`)}</dd></div>
    </dl>
    {connection.is_critical && <p className="flex items-center gap-1 text-xs text-red-400"><Shield aria-hidden="true" className="h-3 w-3" />{t("config.apiMap.legend.critical")}</p>}
    <div className="space-y-2"><h4 className="flex items-center gap-2 font-medium"><Code aria-hidden="true" className="h-4 w-4" />{t("config.apiMap.methods")}</h4>
      {(connection.methods ?? []).length ? <ul className="space-y-2">{(connection.methods ?? []).map((method) => <li key={method} className="break-all rounded-lg border border-theme bg-theme-overlay-strong px-3 py-2 font-mono text-xs">{method}</li>)}</ul> : <p className="text-sm text-theme-muted">{t("config.apiMap.no_methods")}</p>}
    </div>
  </section>)}</>;
}

export function ConnectionFilterControls({ filters, onChange }: Readonly<{ filters: ConnectionFilters; onChange: (field: keyof ConnectionFilters, value: string) => void }>) {
  const t = useTranslation();
  const options = { source: ["all", "local", "cloud", "hybrid"], status: ["all", "ok", "degraded", "down", "unknown"], protocol: ["all", "http", "https", "ws", "sse", "tcp"] };
  return <>{(["source", "status", "protocol"] as const).map((field) => <label key={field} className="flex min-w-0 flex-col gap-1 text-xs text-theme-muted">
    {t(`config.apiMap.filters.${field}.label`)}
    <select value={filters[field]} onChange={(event) => onChange(field, event.target.value)} className="h-9 rounded-lg border border-theme bg-theme-overlay-strong px-2 text-sm text-theme-primary">
      {options[field].map((value) => <option key={value} value={value}>{t(`config.apiMap.filters.${field}.${value}`)}</option>)}
    </select>
  </label>)}</>;
}
