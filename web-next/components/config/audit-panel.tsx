"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useTranslation } from "@/lib/i18n";

type CoreAuditEntry = {
  timestamp: string;
  action: string;
  user: string;
  provider: string | null;
  result: string;
  error_message?: string | null;
};

type ModuleAuditEntry = {
  id: string;
  actor: string;
  action: string;
  status: string;
  payload_hash: string;
  timestamp: string;
};

type UnifiedRow = {
  source: "core" | "module";
  timestamp: string;
  action: string;
  actor: string;
  context: string;
  status: string;
  outcome: "success" | "warning" | "danger" | "neutral";
  idRef: string;
};

type OutcomeFilter = "all" | "success" | "warning" | "danger" | "neutral";
type SourceFilter = "all" | "core" | "module";

function formatFixedDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "0000-00-00 00:00:00";
  }
  const yyyy = date.getFullYear().toString().padStart(4, "0");
  const mm = (date.getMonth() + 1).toString().padStart(2, "0");
  const dd = date.getDate().toString().padStart(2, "0");
  const hh = date.getHours().toString().padStart(2, "0");
  const min = date.getMinutes().toString().padStart(2, "0");
  const sec = date.getSeconds().toString().padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${min}:${sec}`;
}

function truncateMiddle(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  const keep = Math.max(4, Math.floor((maxLength - 1) / 2));
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

function resolveCoreOutcome(result: string): UnifiedRow["outcome"] {
  const normalized = result.toLowerCase();
  if (normalized === "success" || normalized === "ok") return "success";
  if (normalized === "failure" || normalized === "failed" || normalized === "error") return "danger";
  if (normalized === "unknown") return "neutral";
  return "warning";
}

function resolveModuleOutcome(status: string): UnifiedRow["outcome"] {
  const normalized = status.toLowerCase();
  if (normalized === "ok" || normalized === "published") return "success";
  if (normalized === "failed" || normalized === "error") return "danger";
  if (normalized === "manual" || normalized === "queued" || normalized === "cached") return "warning";
  return "neutral";
}

function toToneBadgeLabel(status: string): string {
  return status.toUpperCase();
}

export function AuditPanel() {
  const t = useTranslation();
  const [coreEntries, setCoreEntries] = useState<CoreAuditEntry[]>([]);
  const [moduleEntries, setModuleEntries] = useState<ModuleAuditEntry[]>([]);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [moduleError, setModuleError] = useState<string | null>(null);

  const fetchAudits = useCallback(async () => {
    setCoreError(null);
    setModuleError(null);
    try {
      const [coreResp, moduleResp] = await Promise.all([
        fetch("/api/v1/admin/audit?limit=100"),
        fetch("/api/v1/brand-studio/audit"),
      ]);

      if (coreResp.ok) {
        const payload = (await coreResp.json()) as { entries?: CoreAuditEntry[] };
        setCoreEntries(Array.isArray(payload.entries) ? payload.entries : []);
      } else {
        setCoreEntries([]);
        setCoreError(`${t("config.audit.core.loadError")} (HTTP ${coreResp.status})`);
      }

      if (moduleResp.ok) {
        const payload = (await moduleResp.json()) as { items?: ModuleAuditEntry[] };
        setModuleEntries(Array.isArray(payload.items) ? payload.items : []);
      } else if (moduleResp.status === 404 || moduleResp.status === 503) {
        setModuleEntries([]);
        setModuleError(t("config.audit.module.unavailable"));
      } else {
        setModuleEntries([]);
        setModuleError(`${t("config.audit.module.loadError")} (HTTP ${moduleResp.status})`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : t("config.audit.loadError");
      setCoreError(message);
      setModuleError(message);
    }
  }, [t]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchAudits();
      setLoading(false);
    };
    void load();
  }, [fetchAudits]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchAudits();
    setRefreshing(false);
  }, [fetchAudits]);

  const unifiedRows = useMemo<UnifiedRow[]>(() => {
    const coreRows: UnifiedRow[] = coreEntries.map((entry, index) => ({
      source: "core",
      timestamp: entry.timestamp,
      action: entry.action,
      actor: entry.user || "-",
      context: entry.provider || "-",
      status: entry.result || "unknown",
      outcome: resolveCoreOutcome(entry.result || "unknown"),
      idRef: `core-${index + 1}`,
    }));

    const moduleRows: UnifiedRow[] = moduleEntries.map((entry) => ({
      source: "module",
      timestamp: entry.timestamp,
      action: entry.action,
      actor: entry.actor || "-",
      context: entry.payload_hash || "-",
      status: entry.status || "unknown",
      outcome: resolveModuleOutcome(entry.status || "unknown"),
      idRef: entry.id || "-",
    }));

    return [...coreRows, ...moduleRows].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );
  }, [coreEntries, moduleEntries]);

  const filteredRows = useMemo(() => {
    return unifiedRows.filter((row) => {
      if (sourceFilter !== "all" && row.source !== sourceFilter) return false;
      if (outcomeFilter !== "all" && row.outcome !== outcomeFilter) return false;
      return true;
    });
  }, [outcomeFilter, sourceFilter, unifiedRows]);

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl border border-cyan-500/20 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-medium text-cyan-100">{t("config.audit.title")}</h2>
            <p className="text-sm text-zinc-400">{t("config.audit.description")}</p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
          >
            {refreshing ? t("config.audit.refreshing") : t("config.audit.refresh")}
          </Button>
        </div>
      </div>

      <div className="glass-panel space-y-3 rounded-2xl border border-white/10 p-4">
        <div className="grid gap-2 md:grid-cols-2">
          <label className="space-y-1">
            <span className="text-[11px] uppercase text-zinc-500">{t("config.audit.filters.source")}</span>
            <select
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value as SourceFilter)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-2 py-1 text-xs text-zinc-100"
            >
              <option value="all">{t("config.audit.filters.allSources")}</option>
              <option value="core">{t("config.audit.filters.coreSource")}</option>
              <option value="module">{t("config.audit.filters.moduleSource")}</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[11px] uppercase text-zinc-500">{t("config.audit.filters.outcome")}</span>
            <select
              value={outcomeFilter}
              onChange={(event) => setOutcomeFilter(event.target.value as OutcomeFilter)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-2 py-1 text-xs text-zinc-100"
            >
              <option value="all">{t("config.audit.filters.allOutcomes")}</option>
              <option value="success">{t("config.audit.filters.success")}</option>
              <option value="warning">{t("config.audit.filters.warning")}</option>
              <option value="danger">{t("config.audit.filters.error")}</option>
              <option value="neutral">{t("config.audit.filters.neutral")}</option>
            </select>
          </label>
        </div>

        {coreError ? <p className="text-xs text-amber-300">{coreError}</p> : null}
        {moduleError ? <p className="text-xs text-amber-300">{moduleError}</p> : null}
        {loading ? <p className="text-zinc-400">{t("common.loading")}</p> : null}
        {!loading && !filteredRows.length ? <p className="text-zinc-400">{t("config.audit.empty")}</p> : null}

        {!loading && filteredRows.length ? (
          <div
            className="pr-2"
            style={{
              maxHeight: "690px",
              overflowY: "scroll",
              scrollbarGutter: "stable",
              overscrollBehavior: "contain",
            }}
          >
            <ul className="divide-y divide-white/5">
              {filteredRows.map((row) => (
                <li key={`${row.source}:${row.idRef}:${row.timestamp}`} className="px-1 py-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-[19ch] shrink-0 text-zinc-500">{formatFixedDateTime(row.timestamp)}</span>
                    <span className="shrink-0 font-semibold uppercase text-zinc-300">{row.action}</span>
                    <span className="shrink-0 text-zinc-500">{truncateMiddle(row.actor, 18)}</span>
                    <span className="min-w-0 truncate text-zinc-500">{truncateMiddle(row.context, 18)}</span>
                    <span className="shrink-0 text-zinc-500">{truncateMiddle(row.idRef, 14)}</span>
                    <Badge tone={row.outcome} className="ml-auto px-2 py-0.5 text-[11px]">
                      {toToneBadgeLabel(row.status)}
                    </Badge>
                    <Badge tone="neutral" className="px-2 py-0.5 text-[10px] uppercase">
                      {row.source === "core" ? t("config.audit.source.core") : t("config.audit.source.module")}
                    </Badge>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
