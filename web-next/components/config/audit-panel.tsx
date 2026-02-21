"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";

type AuditStreamEntry = {
  id: string;
  timestamp: string;
  source: string;
  api_channel: string;
  action: string;
  actor: string;
  status: string;
  context?: string | null;
};

type AuditRow = {
  source: string;
  apiChannel: string;
  timestamp: string;
  action: string;
  actor: string;
  context: string;
  status: string;
  outcome: "success" | "warning" | "danger" | "neutral";
  idRef: string;
};

type OutcomeFilter = "all" | "success" | "warning" | "danger" | "neutral";

const ALL_CHANNELS = "all";
const AUDIT_STREAM_URL = "/api/v1/audit/stream?limit=200";
const API_MAP_URL = "/api/v1/system/api-map";

type ApiMapConnection = {
  target_component?: string;
};

type ApiMapPayload = {
  internal_connections?: ApiMapConnection[];
  external_connections?: ApiMapConnection[];
};

function formatFixedDateTime(value: string, fallback: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return fallback;
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
  if (maxLength <= 0) return "";
  if (value.length <= maxLength) return value;
  if (maxLength <= 3) return value.slice(0, maxLength);
  if (maxLength < 9) return `${value.slice(0, maxLength - 3)}...`;
  const head = Math.floor((maxLength - 3) / 2);
  const tail = maxLength - 3 - head;
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function resolveOutcome(status: string): AuditRow["outcome"] {
  const normalized = status.toLowerCase();
  if (["success", "ok", "published", "accepted"].includes(normalized)) return "success";
  if (["failed", "failure", "error", "denied", "forbidden"].includes(normalized)) return "danger";
  if (["queued", "cached", "manual", "pending", "partial"].includes(normalized)) return "warning";
  return "neutral";
}

function toToneBadgeLabel(status: string): string {
  return status.toUpperCase();
}

function timestampToMs(value: string): number {
  const ms = new Date(value).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

export function AuditPanel() {
  const t = useTranslation();
  const unknownLabel = t("common.unknown");
  const noDataLabel = t("common.noData");
  const [entries, setEntries] = useState<AuditStreamEntry[]>([]);
  const [apiMapChannels, setApiMapChannels] = useState<string[]>([]);
  const [apiChannelFilter, setApiChannelFilter] = useState<string>(ALL_CHANNELS);
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchAudits = useCallback(async () => {
    setLoadError(null);
    const [auditResponse, apiMapResponse] = await Promise.allSettled([
      fetch(AUDIT_STREAM_URL),
      fetch(API_MAP_URL),
    ]);

    if (apiMapResponse.status === "fulfilled" && apiMapResponse.value.ok) {
      try {
        const payload = (await apiMapResponse.value.json()) as ApiMapPayload;
        const channels = new Set<string>();
        payload.internal_connections?.forEach((connection) => {
          const name = (connection.target_component || "").trim();
          if (name) channels.add(name);
        });
        payload.external_connections?.forEach((connection) => {
          const name = (connection.target_component || "").trim();
          if (name) channels.add(name);
        });
        setApiMapChannels(Array.from(channels).sort((a, b) => a.localeCompare(b)));
      } catch {
        setApiMapChannels([]);
      }
    } else {
      setApiMapChannels([]);
    }

    try {
      if (auditResponse.status !== "fulfilled") {
        throw new Error(t("config.audit.loadError"));
      }
      const response = auditResponse.value;
      if (!response.ok) {
        setEntries([]);
        setLoadError(
          t("config.audit.loadErrorWithStatus", {
            message: t("config.audit.loadError"),
            status: response.status,
          }),
        );
        return;
      }
      const payload = (await response.json()) as { entries?: AuditStreamEntry[] };
      setEntries(Array.isArray(payload.entries) ? payload.entries : []);
    } catch (error) {
      const message = error instanceof Error ? error.message : t("config.audit.loadError");
      setLoadError(message);
      setEntries([]);
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

  const rows = useMemo<AuditRow[]>(
    () =>
      entries
        .map((entry) => {
          const statusRaw = (entry.status || "").trim() || "unknown";
          return {
            source: (entry.source || "").trim() || unknownLabel,
            apiChannel: (entry.api_channel || "").trim() || unknownLabel,
            timestamp: entry.timestamp,
            action: (entry.action || "").trim() || unknownLabel,
            actor: (entry.actor || "").trim() || noDataLabel,
            context: (entry.context || "").trim() || noDataLabel,
            status: statusRaw,
            outcome: resolveOutcome(statusRaw),
            idRef: (entry.id || "").trim() || noDataLabel,
          };
        })
        .sort((a, b) => timestampToMs(b.timestamp) - timestampToMs(a.timestamp)),
    [entries, noDataLabel, unknownLabel],
  );

  const apiChannels = useMemo(() => {
    const channels = new Set<string>();
    apiMapChannels.forEach((channel) => channels.add(channel));
    rows.forEach((row) => {
      const channel = (row.apiChannel || "").trim();
      if (channel) channels.add(channel);
    });
    return Array.from(channels).sort((a, b) => a.localeCompare(b));
  }, [apiMapChannels, rows]);

  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        if (apiChannelFilter !== ALL_CHANNELS && row.apiChannel !== apiChannelFilter) return false;
        if (outcomeFilter !== "all" && row.outcome !== outcomeFilter) return false;
        return true;
      }),
    [apiChannelFilter, outcomeFilter, rows],
  );

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
              value={apiChannelFilter}
              onChange={(event) => setApiChannelFilter(event.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-2 py-1 text-xs text-zinc-100"
            >
              <option value={ALL_CHANNELS}>{t("config.audit.filters.allSources")}</option>
              {apiChannels.map((channel) => (
                <option key={channel} value={channel}>
                  {channel}
                </option>
              ))}
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

        {loadError ? <p className="text-xs text-amber-300">{loadError}</p> : null}
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
                <li key={`${row.idRef}:${row.timestamp}`} className="px-1 py-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-[19ch] shrink-0 text-zinc-500">
                      {formatFixedDateTime(row.timestamp, noDataLabel)}
                    </span>
                    <span className="shrink-0 font-semibold uppercase text-zinc-300">{row.action}</span>
                    <span className="shrink-0 text-zinc-500">{truncateMiddle(row.source, 16)}</span>
                    <span className="shrink-0 text-zinc-500">{truncateMiddle(row.actor, 18)}</span>
                    <span className="min-w-0 truncate text-zinc-500">{truncateMiddle(row.context, 18)}</span>
                    <span className="shrink-0 text-zinc-500">{truncateMiddle(row.idRef, 14)}</span>
                    <div className="ml-auto flex shrink-0 items-center gap-2">
                      <Badge
                        tone="neutral"
                        className="w-[10.5rem] justify-start px-2 py-0.5 text-left text-[11px]"
                        title={row.apiChannel}
                      >
                        {truncateMiddle(row.apiChannel, 22)}
                      </Badge>
                      <Badge tone={row.outcome} className="px-2 py-0.5 text-[11px]">
                        {toToneBadgeLabel(row.status)}
                      </Badge>
                    </div>
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
