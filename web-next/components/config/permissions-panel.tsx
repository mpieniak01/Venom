"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";

type AuditEntry = {
  id: string;
  timestamp: string;
  action: string;
  actor: string;
  status: string;
  details?: Record<string, unknown>;
};

type AutonomyCurrent = {
  current_level: number;
  current_level_name: string;
  color: string;
  color_name: string;
  description: string;
  permissions: Record<string, unknown>;
  risk_level: string;
};

type AutonomyLevel = {
  id: number;
  name: string;
  description: string;
  color: string;
  color_name: string;
  permissions: Record<string, unknown>;
  risk_level: string;
  examples?: string[];
};

type AutonomyLevelsResponse = {
  status: string;
  levels: AutonomyLevel[];
  count: number;
};

type AutonomySetResponse = {
  status: string;
  message: string;
  level: number;
  level_name: string;
  color: string;
  permissions: Record<string, unknown>;
};

type PolicyReasonStat = {
  reason_code: string;
  count: number;
  share_rate: number;
};

type PolicyObservability = {
  blocked_count?: number;
  block_rate?: number;
  deny_rate?: number;
  top_reason_codes?: PolicyReasonStat[];
  false_positive_triage?: {
    candidate_count?: number;
    candidate_rate?: number;
    top_candidate_reasons?: PolicyReasonStat[];
    note?: string;
  };
};

type MetricsPayload = {
  policy?: PolicyObservability;
};

const AUTONOMY_URL = "/api/v1/system/autonomy";
const AUTONOMY_LEVELS_URL = "/api/v1/system/autonomy/levels";
const AUDIT_STREAM_URL = "/api/v1/audit/stream?limit=200";
const SYSTEM_METRICS_URL = "/api/v1/metrics/system";

function prettyBool(value: unknown, t: ReturnType<typeof useTranslation>): string {
  if (value === true) return t("config.permissions.values.enabled");
  if (value === false) return t("config.permissions.values.disabled");
  if (typeof value === "string") return value;
  return t("common.noData");
}

function formatDate(value: string, fallback: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleString();
}

export function PermissionsPanel() {
  const t = useTranslation();
  const [current, setCurrent] = useState<AutonomyCurrent | null>(null);
  const [levels, setLevels] = useState<AutonomyLevel[]>([]);
  const [events, setEvents] = useState<AuditEntry[]>([]);
  const [observability, setObservability] = useState<PolicyObservability | null>(null);
  const [targetLevel, setTargetLevel] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const analysisLevel = useMemo(() => {
    return levels.find((level) => level.name === "CONNECTED") ?? levels.find((level) => level.id === 10) ?? null;
  }, [levels]);

  const fetchAll = useCallback(async () => {
    setError(null);
    setMessage(null);

    const [currentRes, levelsRes, auditRes, metricsRes] = await Promise.all([
      fetch(AUTONOMY_URL),
      fetch(AUTONOMY_LEVELS_URL),
      fetch(AUDIT_STREAM_URL),
      fetch(SYSTEM_METRICS_URL),
    ]);

    if (!currentRes.ok) {
      throw new Error(`${t("config.permissions.errors.load")} (HTTP ${currentRes.status})`);
    }
    if (!levelsRes.ok) {
      throw new Error(`${t("config.permissions.errors.load")} (HTTP ${levelsRes.status})`);
    }

    const currentPayload = (await currentRes.json()) as AutonomyCurrent;
    const levelsPayload = (await levelsRes.json()) as AutonomyLevelsResponse;

    setCurrent(currentPayload);
    setLevels(Array.isArray(levelsPayload.levels) ? levelsPayload.levels : []);
    setTargetLevel(currentPayload.current_level);

    if (metricsRes.ok) {
      const metricsPayload = (await metricsRes.json()) as MetricsPayload;
      setObservability(metricsPayload.policy ?? null);
    } else {
      setObservability(null);
    }

    if (auditRes.ok) {
      const auditPayload = (await auditRes.json()) as { entries?: AuditEntry[] };
      const auditEntries = Array.isArray(auditPayload.entries) ? auditPayload.entries : [];
      const permissionEvents = auditEntries
        .filter((entry) => (entry.action || "").startsWith("autonomy."))
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, 25);
      setEvents(permissionEvents);
    } else {
      setEvents([]);
    }
  }, [t]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        await fetchAll();
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : t("config.permissions.errors.load"));
      } finally {
        setLoading(false);
      }
    }

    load().catch(() => undefined);
  }, [fetchAll, t]);

  const applyLevel = useCallback(async (level: number) => {
    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(AUTONOMY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
      const payload = (await response.json()) as Partial<AutonomySetResponse> & { detail?: string };

      if (!response.ok) {
        throw new Error(payload.detail || payload.message || t("config.permissions.errors.update"));
      }

      setMessage(payload.message || t("config.permissions.messages.updated"));
      await fetchAll();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : t("config.permissions.errors.update"));
    } finally {
      setSaving(false);
    }
  }, [fetchAll, t]);

  if (loading) {
    return <div className="text-sm text-theme-muted">{t("common.loading")}</div>;
  }

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl border border-cyan-500/20 p-4">
        <h2 className="text-lg font-medium text-cyan-100">{t("config.permissions.title")}</h2>
        <p className="text-sm text-theme-muted">{t("config.permissions.description")}</p>

        {message ? (
          <div className="mt-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
            {message}
          </div>
        ) : null}
        {error ? (
          <div className="mt-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}
      </div>

      {current ? (
        <div className="glass-panel rounded-2xl border border-theme p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-theme bg-theme-overlay-strong p-3">
              <div className="text-xs text-theme-muted">{t("config.permissions.currentLevel")}</div>
              <div className="mt-1 flex items-center gap-2">
                <Badge tone="neutral">{current.current_level_name}</Badge>
                <span className="text-xs text-theme-muted">L{current.current_level}</span>
              </div>
              <p className="mt-2 text-sm text-theme-secondary">{current.description}</p>
            </div>

            <div className="rounded-2xl border border-theme bg-theme-overlay-strong p-3">
              <label htmlFor="permissions-level-select" className="text-xs text-theme-muted">
                {t("config.permissions.setLevel")}
              </label>
              <select
                id="permissions-level-select"
                className="mt-2 w-full rounded-lg border border-zinc-700 bg-theme-overlay-strong px-3 py-2 text-sm text-theme-primary"
                value={targetLevel ?? ""}
                onChange={(event) => setTargetLevel(Number(event.target.value))}
              >
                {levels.map((level) => (
                  <option key={level.id} value={level.id}>
                    {`L${level.id} - ${level.name}`}
                  </option>
                ))}
              </select>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  className="shadow-[0_0_20px_rgba(34,211,238,0.15)]"
                  onClick={() => {
                    if (typeof targetLevel === "number") {
                      applyLevel(targetLevel).catch(() => undefined);
                    }
                  }}
                  disabled={saving || typeof targetLevel !== "number"}
                >
                  {saving ? t("config.permissions.actions.saving") : t("config.permissions.actions.apply")}
                </Button>

                <Button
                  size="sm"
                  variant="outline"
                  disabled={saving || !analysisLevel}
                  onClick={() => {
                    if (analysisLevel) {
                      applyLevel(analysisLevel.id).catch(() => undefined);
                    }
                  }}
                >
                  {t("config.permissions.actions.grantAnalysis")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="glass-panel rounded-2xl border border-theme p-4">
        <h4 className="text-sm font-semibold text-theme-primary">{t("config.permissions.levelsTitle")}</h4>
        <div className="mt-3 overflow-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-theme text-left text-xs uppercase tracking-wide text-theme-muted">
                <th className="py-2 pr-3">{t("config.permissions.columns.level")}</th>
                <th className="py-2 pr-3">{t("config.permissions.columns.risk")}</th>
                <th className="py-2 pr-3">{t("config.permissions.columns.network")}</th>
                <th className="py-2 pr-3">{t("config.permissions.columns.paidApi")}</th>
                <th className="py-2 pr-3">{t("config.permissions.columns.filesystem")}</th>
                <th className="py-2 pr-3">{t("config.permissions.columns.shell")}</th>
                <th className="py-2">{t("config.permissions.columns.desktop")}</th>
              </tr>
            </thead>
            <tbody>
              {levels.map((level) => (
                <tr key={level.id} className="border-b border-white/10 text-theme-secondary">
                  <td className="py-2 pr-3">
                    <div className="font-medium text-theme-primary">{`L${level.id} - ${level.name}`}</div>
                    <div className="text-xs text-theme-muted">{level.description}</div>
                  </td>
                  <td className="py-2 pr-3">{level.risk_level}</td>
                  <td className="py-2 pr-3">{prettyBool(level.permissions.network_enabled, t)}</td>
                  <td className="py-2 pr-3">{prettyBool(level.permissions.paid_api_enabled, t)}</td>
                  <td className="py-2 pr-3">{prettyBool(level.permissions.filesystem_mode, t)}</td>
                  <td className="py-2 pr-3">{prettyBool(level.permissions.shell_enabled, t)}</td>
                  <td className="py-2">{prettyBool(level.permissions.desktop_input_enabled, t)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="glass-panel rounded-2xl border border-theme p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-theme-primary">{t("config.permissions.observability.title")}</h4>
            <p className="mt-1 text-sm text-theme-muted">{t("config.permissions.observability.description")}</p>
          </div>
          <Badge tone={(observability?.deny_rate ?? 0) > 0 ? "warning" : "success"}>
            {`${t("config.permissions.observability.labels.denyRate")}: ${(observability?.deny_rate ?? 0).toFixed(2)}%`}
          </Badge>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-theme bg-theme-overlay-strong p-3">
            <div className="text-xs uppercase tracking-wide text-theme-muted">{t("config.permissions.observability.labels.blocked")}</div>
            <div className="mt-2 text-2xl font-semibold text-theme-primary">{observability?.blocked_count ?? 0}</div>
          </div>
          <div className="rounded-2xl border border-theme bg-theme-overlay-strong p-3">
            <div className="text-xs uppercase tracking-wide text-theme-muted">{t("config.permissions.observability.labels.reviewQueue")}</div>
            <div className="mt-2 text-2xl font-semibold text-theme-primary">{observability?.false_positive_triage?.candidate_count ?? 0}</div>
            <div className="mt-1 text-xs text-theme-muted">
              {`${(observability?.false_positive_triage?.candidate_rate ?? 0).toFixed(2)}% ${t("config.permissions.observability.labels.ofBlocks")}`}
            </div>
          </div>
          <div className="rounded-2xl border border-theme bg-theme-overlay-strong p-3">
            <div className="text-xs uppercase tracking-wide text-theme-muted">{t("config.permissions.observability.labels.primaryReason")}</div>
            <div className="mt-2 text-sm font-semibold text-theme-primary">
              {observability?.top_reason_codes?.[0]?.reason_code ?? t("common.noData")}
            </div>
            <div className="mt-1 text-xs text-theme-muted">
              {observability?.top_reason_codes?.[0]
                ? `${observability.top_reason_codes[0].count} • ${observability.top_reason_codes[0].share_rate.toFixed(2)}%`
                : t("common.noData")}
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-theme bg-theme-overlay-strong p-3">
            <div className="mb-3 text-sm font-semibold text-theme-primary">{t("config.permissions.observability.topReasonsTitle")}</div>
            {!observability?.top_reason_codes?.length ? (
              <p className="text-sm text-theme-muted">{t("config.permissions.observability.empty")}</p>
            ) : (
              <div className="space-y-2">
                {observability.top_reason_codes.map((item) => (
                  <div key={item.reason_code} className="flex items-center justify-between rounded-xl border border-white/10 px-3 py-2">
                    <div>
                      <div className="text-sm font-medium text-theme-primary">{item.reason_code}</div>
                      <div className="text-xs text-theme-muted">{`${item.count} ${t("config.permissions.observability.labels.blocks")}`}</div>
                    </div>
                    <Badge tone="neutral">{`${item.share_rate.toFixed(2)}%`}</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-theme bg-theme-overlay-strong p-3">
            <div className="mb-3 text-sm font-semibold text-theme-primary">{t("config.permissions.observability.triageTitle")}</div>
            <p className="mb-3 text-xs text-theme-muted">
              {observability?.false_positive_triage?.note || t("config.permissions.observability.triageFallback")}
            </p>
            {!observability?.false_positive_triage?.top_candidate_reasons?.length ? (
              <p className="text-sm text-theme-muted">{t("config.permissions.observability.empty")}</p>
            ) : (
              <div className="space-y-2">
                {observability.false_positive_triage.top_candidate_reasons.map((item) => (
                  <div key={item.reason_code} className="flex items-center justify-between rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-3 py-2">
                    <div>
                      <div className="text-sm font-medium text-theme-primary">{item.reason_code}</div>
                      <div className="text-xs text-theme-muted">{`${item.count} ${t("config.permissions.observability.labels.reviewCandidates")}`}</div>
                    </div>
                    <Badge tone="warning">{`${item.share_rate.toFixed(2)}%`}</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="glass-panel rounded-2xl border border-theme p-4">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold text-theme-primary">{t("config.permissions.eventsTitle")}</h4>
          <Button variant="outline" size="sm" onClick={() => fetchAll().catch(() => undefined)}>
            {t("config.permissions.actions.refresh")}
          </Button>
        </div>

        {events.length === 0 ? (
          <p className="text-sm text-theme-muted">{t("config.permissions.emptyEvents")}</p>
        ) : (
          <div className="space-y-2 max-h-56 overflow-auto pr-1">
            {events.map((event) => (
              <div key={event.id} className="rounded-md border border-theme bg-theme-overlay-strong p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-mono text-xs text-theme-muted">{event.action}</div>
                  <Badge tone={event.status === "success" ? "success" : "neutral"}>{event.status}</Badge>
                </div>
                <div className="mt-1 text-xs text-theme-muted">
                  {formatDate(event.timestamp, t("common.unknown"))} • {event.actor || t("common.unknown")}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
