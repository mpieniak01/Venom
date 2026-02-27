"use client";

import { useCallback, useEffect, useMemo, useState, type UIEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { isNearBottom, mergeAuditEntries, nextVisibleCount } from "@/lib/audit-panel-helpers";

type AuditStreamEntry = {
  id: string;
  timestamp: string;
  source: string;
  api_channel: string;
  action: string;
  actor: string;
  status: string;
  context?: string | null;
  details?: Record<string, unknown>;
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
  details: Record<string, unknown>;
};

type OutcomeFilter = "all" | "success" | "warning" | "danger" | "neutral";

const ALL_CHANNELS = "all";
const AUDIT_STREAM_URL = "/api/v1/audit/stream";
const AUDIT_INITIAL_LIMIT = 60;
const AUDIT_FULL_LIMIT = 200;
const AUDIT_RENDER_BATCH = 60;
const API_MAP_URL = "/api/v1/system/api-map";
const API_MAP_FETCH_TIMEOUT_MS = 1500;

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
  if (
    normalized === "ok" ||
    normalized.includes("success") ||
    normalized.includes("published") ||
    normalized.includes("accepted")
  ) {
    return "success";
  }
  if (
    normalized.includes("fail") ||
    normalized.includes("error") ||
    normalized.includes("denied") ||
    normalized.includes("forbidden")
  ) {
    return "danger";
  }
  if (
    normalized.includes("warning") ||
    normalized.includes("warn") ||
    normalized.includes("queued") ||
    normalized.includes("cached") ||
    normalized.includes("manual") ||
    normalized.includes("pending") ||
    normalized.includes("partial")
  ) {
    return "warning";
  }
  return "neutral";
}

function toToneBadgeLabel(status: string): string {
  return status.toUpperCase();
}

function timestampToMs(value: string): number {
  const ms = new Date(value).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function useAuditPanelModel(t: ReturnType<typeof useTranslation>) {
  const unknownLabel = t("common.unknown");
  const noDataLabel = t("common.noData");
  const [entries, setEntries] = useState<AuditStreamEntry[]>([]);
  const [apiMapChannels, setApiMapChannels] = useState<string[]>([]);
  const [apiChannelFilter, setApiChannelFilter] = useState<string>(ALL_CHANNELS);
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(AUDIT_RENDER_BATCH);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchApiMapChannels = useCallback(async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), API_MAP_FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(API_MAP_URL, { signal: controller.signal });
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as ApiMapPayload;
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
      // API map is auxiliary metadata; ignore timeout/network errors.
    } finally {
      clearTimeout(timeout);
    }
  }, []);

  const fetchAudits = useCallback(async () => {
    setLoadError(null);
    setVisibleCount(AUDIT_RENDER_BATCH);

    try {
      const initialResponse = await fetch(`${AUDIT_STREAM_URL}?limit=${AUDIT_INITIAL_LIMIT}`);
      if (!initialResponse.ok) {
        setEntries([]);
        setLoadError(
          t("config.audit.loadErrorWithStatus", {
            message: t("config.audit.loadError"),
            status: initialResponse.status,
          }),
        );
        return;
      }
      const initialPayload = (await initialResponse.json()) as { entries?: AuditStreamEntry[] };
      const initialEntries = Array.isArray(initialPayload.entries) ? initialPayload.entries : [];
      setEntries(initialEntries);

      // Fetch older entries in background to keep first paint fast.
      fetch(`${AUDIT_STREAM_URL}?limit=${AUDIT_FULL_LIMIT}`)
        .then(async (response) => {
          if (!response.ok) return;
          const payload = (await response.json()) as { entries?: AuditStreamEntry[] };
          const fullEntries = Array.isArray(payload.entries) ? payload.entries : [];
          if (!fullEntries.length) return;
          setEntries((prev) => {
            return mergeAuditEntries(prev, fullEntries);
          });
        })
        .catch(() => undefined);
    } catch (error) {
      const message = error instanceof Error ? error.message : t("config.audit.loadError");
      setLoadError(message);
      setEntries([]);
    }
    // Do not block visible log rendering on slower API map endpoint.
    fetchApiMapChannels().catch(() => undefined);
  }, [fetchApiMapChannels, t]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchAudits();
      setLoading(false);
    };
    load().catch(() => undefined);
  }, [fetchAudits]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchAudits();
    setRefreshing(false);
  }, [fetchAudits]);

  function onRefreshClick() {
    handleRefresh().catch(() => undefined);
  }

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
            details: entry.details ?? {},
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

  useEffect(() => {
    setVisibleCount(AUDIT_RENDER_BATCH);
  }, [apiChannelFilter, outcomeFilter]);

  const visibleRows = useMemo(
    () => filteredRows.slice(0, visibleCount),
    [filteredRows, visibleCount],
  );

  const hasMoreRows = visibleRows.length < filteredRows.length;

  const onRowsScroll = useCallback(
    (event: UIEvent<HTMLDivElement>) => {
      if (!hasMoreRows) return;
      const target = event.currentTarget;
      if (!isNearBottom(target.scrollHeight, target.scrollTop, target.clientHeight)) return;
      setVisibleCount((prev) => nextVisibleCount(prev, filteredRows.length, AUDIT_RENDER_BATCH));
    },
    [filteredRows.length, hasMoreRows],
  );

  useEffect(() => {
    if (!filteredRows.length) {
      setSelectedEntryId(null);
      return;
    }
    if (selectedEntryId && filteredRows.some((row) => row.idRef === selectedEntryId)) {
      return;
    }
    setSelectedEntryId(filteredRows[0].idRef);
  }, [filteredRows, selectedEntryId]);

  const selectedRow = useMemo(
    () => filteredRows.find((row) => row.idRef === selectedEntryId) ?? null,
    [filteredRows, selectedEntryId],
  );

  const selectedAutonomyLevel = useMemo(() => {
    if (!selectedRow) return null;
    const d = selectedRow.details;
    const current = readNumber(d.current_level) ?? readNumber(d.current_autonomy_level);
    const currentName = readString(d.current_level_name) ?? readString(d.current_autonomy_level_name);
    const required = readNumber(d.required_level);
    const requiredName = readString(d.required_level_name);
    const oldLevel = readNumber(d.old_level);
    const oldName = readString(d.old_level_name);
    const newLevel = readNumber(d.new_level);
    const newName = readString(d.new_level_name);
    return {
      current,
      currentName,
      required,
      requiredName,
      oldLevel,
      oldName,
      newLevel,
      newName,
    };
  }, [selectedRow]);

  const selectedAutonomyPolicy = useMemo(() => {
    if (!selectedRow) return null;
    const d = selectedRow.details;
    const check = readString(d.autonomy_policy_check);
    const compliant =
      typeof d.autonomy_policy_compliant === "boolean"
        ? d.autonomy_policy_compliant
        : null;
    return { check, compliant };
  }, [selectedRow]);

  const hasAutonomyDetails = useMemo(() => {
    if (!selectedAutonomyLevel) return false;
    return (
      selectedAutonomyLevel.current !== null ||
      selectedAutonomyLevel.required !== null ||
      selectedAutonomyLevel.oldLevel !== null ||
      selectedAutonomyLevel.newLevel !== null
    );
  }, [selectedAutonomyLevel]);

  const hasAutonomySection = useMemo(() => {
    if (hasAutonomyDetails) return true;
    if (!selectedAutonomyPolicy) return false;
    return selectedAutonomyPolicy.check !== null || selectedAutonomyPolicy.compliant !== null;
  }, [hasAutonomyDetails, selectedAutonomyPolicy]);

  return {
    noDataLabel,
    apiChannelFilter,
    setApiChannelFilter,
    outcomeFilter,
    setOutcomeFilter,
    refresh: onRefreshClick,
    refreshing,
    loadError,
    loading,
    filteredRows,
    apiChannels,
    visibleRows,
    onRowsScroll,
    hasMoreRows,
    selectedRow,
    setSelectedEntryId,
    selectedAutonomyLevel,
    hasAutonomySection,
    selectedAutonomyPolicy,
  };
}

const SKELETON_ROW_KEYS = [
  "audit-skeleton-row-1",
  "audit-skeleton-row-2",
  "audit-skeleton-row-3",
  "audit-skeleton-row-4",
  "audit-skeleton-row-5",
  "audit-skeleton-row-6",
  "audit-skeleton-row-7",
  "audit-skeleton-row-8",
] as const;

type AuditPanelViewModel = ReturnType<typeof useAuditPanelModel>;

function AuditFiltersSection({
  t,
  model,
}: Readonly<{ t: ReturnType<typeof useTranslation>; model: AuditPanelViewModel }>) {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <label className="space-y-1">
        <span className="text-[11px] uppercase text-zinc-500">{t("config.audit.filters.source")}</span>
        <select
          value={model.apiChannelFilter}
          onChange={(event) => model.setApiChannelFilter(event.target.value)}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-2 py-1 text-xs text-zinc-100"
        >
          <option value={ALL_CHANNELS}>{t("config.audit.filters.allSources")}</option>
          {model.apiChannels.map((channel) => (
            <option key={channel} value={channel}>
              {channel}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1">
        <span className="text-[11px] uppercase text-zinc-500">{t("config.audit.filters.outcome")}</span>
        <select
          value={model.outcomeFilter}
          onChange={(event) => model.setOutcomeFilter(event.target.value as OutcomeFilter)}
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
  );
}

function AuditLoadingSkeleton() {
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
      <div
        className="space-y-2 pr-2"
        style={{
          maxHeight: "690px",
          overflowY: "scroll",
          scrollbarGutter: "stable",
          overscrollBehavior: "contain",
        }}
      >
        {SKELETON_ROW_KEYS.map((rowKey) => (
          <div
            key={rowKey}
            className="glass-panel rounded-2xl box-subtle h-8 animate-pulse"
          />
        ))}
      </div>
      <aside className="glass-panel rounded-2xl box-subtle p-4 animate-pulse">
        <div className="space-y-3">
          <div className="h-4 w-28 rounded bg-white/10" />
          <div className="h-6 w-40 rounded bg-white/10" />
          <div className="h-4 w-32 rounded bg-white/10" />
          <div className="mt-4 space-y-2">
            <div className="h-4 w-full rounded bg-white/10" />
            <div className="h-4 w-5/6 rounded bg-white/10" />
            <div className="h-4 w-4/6 rounded bg-white/10" />
          </div>
          <div className="mt-4 h-40 rounded-xl bg-white/10" />
        </div>
      </aside>
    </div>
  );
}

function AuditRows({
  t,
  model,
}: Readonly<{ t: ReturnType<typeof useTranslation>; model: AuditPanelViewModel }>) {
  return (
    <div
      className="pr-2"
      onScroll={model.onRowsScroll}
      style={{
        maxHeight: "690px",
        overflowY: "scroll",
        scrollbarGutter: "stable",
        overscrollBehavior: "contain",
      }}
    >
      <ul className="divide-y divide-white/5">
        {model.visibleRows.map((row) => {
          const isActive = model.selectedRow?.idRef === row.idRef;
          return (
            <li key={`${row.idRef}:${row.timestamp}`} className="px-1 py-1">
              <button
                type="button"
                className={`w-full rounded-md px-1 py-1 text-left transition-colors ${
                  isActive ? "bg-blue-500/10 ring-1 ring-blue-400/40" : "hover:bg-white/5"
                }`}
                onClick={() => model.setSelectedEntryId(row.idRef)}
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="w-[19ch] shrink-0 text-zinc-500">
                    {formatFixedDateTime(row.timestamp, model.noDataLabel)}
                  </span>
                  <span className="shrink-0 font-semibold uppercase text-zinc-300">{row.action}</span>
                  <span className="shrink-0 text-zinc-500">{truncateMiddle(row.source, 16)}</span>
                  <span className="shrink-0 text-zinc-500">{truncateMiddle(row.actor, 18)}</span>
                  <span className="min-w-0 truncate text-zinc-500">{truncateMiddle(row.context, 18)}</span>
                  <span className="shrink-0 text-zinc-500">{truncateMiddle(row.idRef, 14)}</span>
                  <div className="ml-auto flex shrink-0 items-center gap-2">
                    <Badge
                      tone="neutral"
                      className="w-[10.5rem] justify-start border-blue-400/30 bg-blue-500/15 px-2 py-0.5 text-left text-[11px] text-blue-200"
                      title={row.apiChannel}
                    >
                      {truncateMiddle(row.apiChannel, 22)}
                    </Badge>
                    <Badge tone={row.outcome} className="px-2 py-0.5 text-[11px]">
                      {toToneBadgeLabel(row.status)}
                    </Badge>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
        {model.hasMoreRows ? (
          <li className="px-1 py-2 text-center text-[11px] text-zinc-500">
            {t("common.loading")}
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function AuditEntrySummary({
  t,
  row,
  noDataLabel,
}: Readonly<{
  t: ReturnType<typeof useTranslation>;
  row: AuditRow;
  noDataLabel: string;
}>) {
  return (
    <>
      <div className="rounded-2xl border border-white/10 bg-black/25 p-3">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("config.audit.details.entryTitle")}
        </p>
        <p className="font-semibold text-zinc-100">{row.action}</p>
        <p className="text-zinc-400">{formatFixedDateTime(row.timestamp, noDataLabel)}</p>
      </div>

      <div className="grid grid-cols-2 gap-2 rounded-2xl border border-white/10 bg-black/25 p-3 text-[11px]">
        <div className="text-zinc-500">{t("config.audit.details.actor")}</div>
        <div className="text-zinc-200">{row.actor}</div>
        <div className="text-zinc-500">{t("config.audit.details.source")}</div>
        <div className="text-zinc-200">{row.source}</div>
        <div className="text-zinc-500">{t("config.audit.details.apiChannel")}</div>
        <div className="text-zinc-200">{row.apiChannel}</div>
        <div className="text-zinc-500">{t("config.audit.details.status")}</div>
        <div className="text-zinc-200">{row.status}</div>
      </div>
    </>
  );
}

function AuditAutonomyDetails({
  t,
  autonomy,
  policy,
}: Readonly<{
  t: ReturnType<typeof useTranslation>;
  autonomy: NonNullable<AuditPanelViewModel["selectedAutonomyLevel"]>;
  policy: AuditPanelViewModel["selectedAutonomyPolicy"];
}>) {
  return (
    <div className="space-y-1 rounded-md border border-cyan-500/20 bg-cyan-500/5 p-2">
      <p className="text-[11px] uppercase tracking-wide text-cyan-300">
        {t("config.audit.details.autonomy.title")}
      </p>
      {autonomy.current === null ? null : (
        <p className="text-zinc-100">
          {t("config.audit.details.autonomy.current")}: {autonomy.current}
          {autonomy.currentName ? ` (${autonomy.currentName})` : ""}
        </p>
      )}
      {autonomy.required === null ? null : (
        <p className="text-zinc-100">
          {t("config.audit.details.autonomy.required")}: {autonomy.required}
          {autonomy.requiredName ? ` (${autonomy.requiredName})` : ""}
        </p>
      )}
      {autonomy.oldLevel !== null || autonomy.newLevel !== null ? (
        <p className="text-zinc-100">
          {t("config.audit.details.autonomy.change")}: {autonomy.oldLevel ?? "?"}
          {autonomy.oldName ? ` (${autonomy.oldName})` : ""}
          {" -> "}
          {autonomy.newLevel ?? "?"}
          {autonomy.newName ? ` (${autonomy.newName})` : ""}
        </p>
      ) : null}
      {policy?.check ? (
        <p className="text-zinc-100">
          {t("config.audit.details.autonomy.policy")}: {policy.check}
        </p>
      ) : null}
      {policy?.compliant === null ? null : (
        <p className="text-zinc-100">
          {t("config.audit.details.autonomy.compliance")}:{" "}
          {policy?.compliant
            ? t("config.audit.details.autonomy.yes")
            : t("config.audit.details.autonomy.no")}
        </p>
      )}
    </div>
  );
}

function AuditDetailsJson({
  t,
  details,
}: Readonly<{ t: ReturnType<typeof useTranslation>; details: Record<string, unknown> }>) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/25 p-3">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-zinc-500">
        {t("config.audit.details.json")}
      </p>
      <pre className="max-h-56 overflow-auto rounded-md border border-white/10 bg-zinc-950/70 p-2 text-[11px] text-zinc-300">
        {JSON.stringify(details, null, 2)}
      </pre>
    </div>
  );
}

function AuditDetails({
  t,
  model,
}: Readonly<{ t: ReturnType<typeof useTranslation>; model: AuditPanelViewModel }>) {
  if (!model.selectedRow) {
    return (
      <aside className="glass-panel rounded-2xl box-subtle p-4 text-xs">
        <div className="rounded-2xl border border-white/10 bg-black/25 p-4 text-zinc-400">
          {t("config.audit.details.noneSelected")}
        </div>
      </aside>
    );
  }

  const selectedRow = model.selectedRow;
  const autonomy = model.selectedAutonomyLevel;
  const policy = model.selectedAutonomyPolicy;

  return (
    <aside className="glass-panel rounded-2xl box-subtle p-4 text-xs">
      <div className="space-y-3">
        <AuditEntrySummary t={t} row={selectedRow} noDataLabel={model.noDataLabel} />
        {autonomy && model.hasAutonomySection ? (
          <AuditAutonomyDetails t={t} autonomy={autonomy} policy={policy} />
        ) : null}
        <AuditDetailsJson t={t} details={selectedRow.details ?? {}} />
      </div>
    </aside>
  );
}

function AuditBody({
  t,
  model,
}: Readonly<{ t: ReturnType<typeof useTranslation>; model: AuditPanelViewModel }>) {
  if (model.loading) {
    return <AuditLoadingSkeleton />;
  }
  if (!model.filteredRows.length) {
    return <p className="text-zinc-400">{t("config.audit.empty")}</p>;
  }
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
      <AuditRows t={t} model={model} />
      <AuditDetails t={t} model={model} />
    </div>
  );
}

export function AuditPanel() {
  const t = useTranslation();
  const model = useAuditPanelModel(t);

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
            onClick={model.refresh}
            disabled={model.refreshing}
          >
            {model.refreshing ? t("config.audit.refreshing") : t("config.audit.refresh")}
          </Button>
        </div>
      </div>

      <div className="glass-panel space-y-3 rounded-2xl border border-white/10 p-4">
        <AuditFiltersSection t={t} model={model} />
        {model.loadError ? <p className="text-xs text-amber-300">{model.loadError}</p> : null}
        <AuditBody t={t} model={model} />
      </div>
    </div>
  );
}
