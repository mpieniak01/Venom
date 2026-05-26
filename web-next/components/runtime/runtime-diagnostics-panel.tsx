"use client";

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel } from "@/components/ui/panel";
import { useTranslation } from "@/lib/i18n";

type RuntimeSummaryItem = Readonly<{
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "success" | "warning" | "danger" | "neutral";
}>;

type RuntimeComponentSnapshotItem = Readonly<{
  component_id?: string | null;
  component_type?: string | null;
  enabled?: boolean | null;
  available?: boolean | null;
  backend?: string | null;
  model_id?: string | null;
  device_target?: string | null;
  health?: string | null;
  last_error?: string | null;
}>;

type RuntimeTraceAnnotationItem = Readonly<{
  stage?: string | null;
  label?: string | null;
  status?: "active" | "no-op" | "disabled" | "unknown" | null;
  note?: string | null;
}>;

type RuntimeDiagnosticsPanelProps = Readonly<{
  title: string;
  description?: string;
  summaryItems?: RuntimeSummaryItem[];
  trace?: string[] | null;
  traceAnnotations?: RuntimeTraceAnnotationItem[] | null;
  componentSnapshot?: RuntimeComponentSnapshotItem[] | null;
  componentSnapshotCaption?: string;
  componentSnapshotVersion?: string | null;
  componentSnapshotTimestampMs?: number | null;
  liveComponentSnapshotVersion?: string | null;
  liveComponentSnapshotTimestampMs?: number | null;
  degradationReasons?: string[] | null;
  emptyStateTitle?: string;
  emptyStateDescription?: string;
  className?: string;
}>;

function formatSnapshotTimestamp(timestampMs?: number | null): string | null {
  if (typeof timestampMs !== "number" || !Number.isFinite(timestampMs) || timestampMs <= 0) {
    return null;
  }
  const date = new Date(timestampMs);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}

function toneClass(tone?: RuntimeSummaryItem["tone"]): string {
  switch (tone) {
    case "success":
      return "border-emerald-400/30 bg-emerald-500/10 text-emerald-100";
    case "warning":
      return "border-amber-400/30 bg-amber-500/10 text-amber-100";
    case "danger":
      return "border-rose-400/30 bg-rose-500/10 text-rose-100";
    case "neutral":
    default:
      return "border-white/10 bg-white/[0.04] text-zinc-100";
  }
}

function healthTone(health?: string | null): "success" | "warning" | "danger" | "neutral" {
  const normalized = String(health || "").trim().toLowerCase();
  if (normalized === "ok") return "success";
  if (normalized === "degraded") return "warning";
  if (normalized === "disabled") return "neutral";
  if (normalized === "failed" || normalized === "error") return "danger";
  return "neutral";
}

function healthLabel(t: ReturnType<typeof useTranslation>, health?: string | null): string {
  const normalized = String(health || "").trim().toLowerCase();
  if (normalized === "ok") return t("runtime.profile.componentHealth.ok");
  if (normalized === "degraded") return t("runtime.profile.componentHealth.degraded");
  if (normalized === "disabled") return t("runtime.profile.componentHealth.disabled");
  if (normalized === "failed" || normalized === "error") return t("runtime.profile.componentHealth.error");
  return t("runtime.diagnostics.unknown");
}

function traceStatusTone(
  status?: RuntimeTraceAnnotationItem["status"],
): "success" | "warning" | "danger" | "neutral" {
  if (status === "active") return "success";
  if (status === "no-op") return "neutral";
  if (status === "disabled") return "warning";
  return "neutral";
}

export function RuntimeDiagnosticsPanel({
  title,
  description,
  summaryItems,
  trace,
  traceAnnotations,
  componentSnapshot,
  componentSnapshotCaption,
  componentSnapshotVersion,
  componentSnapshotTimestampMs,
  liveComponentSnapshotVersion,
  liveComponentSnapshotTimestampMs,
  degradationReasons,
  emptyStateTitle,
  emptyStateDescription,
  className,
}: RuntimeDiagnosticsPanelProps) {
  const t = useTranslation();
  const resolvedEmptyStateTitle = emptyStateTitle ?? t("runtime.diagnostics.emptyStateTitle");
  const resolvedEmptyStateDescription =
    emptyStateDescription ?? t("runtime.diagnostics.emptyStateDescription");
  const hasSummary = Boolean(summaryItems && summaryItems.length > 0);
  const hasTrace = Boolean(trace && trace.length > 0);
  const hasTraceAnnotations = Boolean(traceAnnotations && traceAnnotations.length > 0);
  const hasComponents = Boolean(componentSnapshot && componentSnapshot.length > 0);
  const snapshotTimestampLabel = formatSnapshotTimestamp(componentSnapshotTimestampMs);
  const liveSnapshotTimestampLabel = formatSnapshotTimestamp(liveComponentSnapshotTimestampMs);
  const hasSnapshotParity = Boolean(componentSnapshotVersion && liveComponentSnapshotVersion);
  const snapshotParityMatches = hasSnapshotParity
    && String(componentSnapshotVersion) === String(liveComponentSnapshotVersion);
  const hasDegradations = Boolean(degradationReasons && degradationReasons.length > 0);
  const hasAny = hasSummary || hasTrace || hasTraceAnnotations || hasComponents || hasDegradations;

  return (
    <Panel
      title={title}
      description={description}
      className={className}
    >
      {hasAny ? (
        <div className="space-y-4 text-sm">
          {hasSummary && (
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {summaryItems?.map((item) => (
                <div
                  key={item.label}
                  className={`rounded-2xl border px-4 py-3 ${toneClass(item.tone)}`}
                >
                  <p className="text-[11px] uppercase tracking-[0.25em] text-zinc-400">
                    {item.label}
                  </p>
                  <div className="mt-1.5 text-sm font-semibold text-white">
                    {item.value}
                  </div>
                  {item.hint && (
                    <p className="mt-1 text-[11px] text-zinc-400">{item.hint}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {hasTrace && (
            <div className="rounded-2xl box-muted px-4 py-3">
              <p className="text-caption">{t("runtime.diagnostics.executionTrace")}</p>
              <p className="mt-1 font-mono text-[11px] text-zinc-300">
                {trace?.join(" -> ")}
              </p>
            </div>
          )}

          {hasTraceAnnotations && (
            <div className="rounded-2xl box-muted px-4 py-3">
              <p className="text-caption">{t("runtime.diagnostics.executionTrace")}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {traceAnnotations?.map((item) => {
                  const tone = traceStatusTone(item.status);
                  return (
                    <Badge key={`${item.stage ?? item.label ?? "trace"}-${item.status ?? "unknown"}`} tone={tone}>
                      {item.label ?? item.stage ?? t("runtime.diagnostics.unknown")}
                      {item.status ? ` · ${item.status}` : ""}
                    </Badge>
                  );
                })}
              </div>
              {traceAnnotations?.some((item) => item.note) && (
                <p className="mt-2 text-[11px] text-zinc-400">
                  {Array.from(
                    new Set(traceAnnotations?.map((item) => item.note).filter(Boolean)),
                  ).join(" · ")}
                </p>
              )}
            </div>
          )}

          {hasComponents && (
            <div className="space-y-2">
              <p className="text-caption">{t("runtime.diagnostics.runtimeComponents")}</p>
              {componentSnapshotCaption && (
                <p className="text-[11px] text-zinc-500">{componentSnapshotCaption}</p>
              )}
              {(componentSnapshotVersion || snapshotTimestampLabel) && (
                <p className="text-[11px] text-zinc-500">
                  {componentSnapshotVersion ? `${t("runtime.diagnostics.snapshotVersion")} ${componentSnapshotVersion}` : ""}
                  {componentSnapshotVersion && snapshotTimestampLabel ? " · " : ""}
                  {snapshotTimestampLabel ? `${t("runtime.diagnostics.snapshotCapturedAt")} ${snapshotTimestampLabel}` : ""}
                </p>
              )}
              {(liveComponentSnapshotVersion || liveSnapshotTimestampLabel) && (
                <p className="text-[11px] text-zinc-500">
                  {liveComponentSnapshotVersion
                    ? `${t("runtime.diagnostics.snapshotLiveVersion")} ${liveComponentSnapshotVersion}`
                    : ""}
                  {liveComponentSnapshotVersion && liveSnapshotTimestampLabel ? " · " : ""}
                  {liveSnapshotTimestampLabel
                    ? `${t("runtime.diagnostics.snapshotCapturedAt")} ${liveSnapshotTimestampLabel}`
                    : ""}
                </p>
              )}
              {hasSnapshotParity && (
                <Badge tone={snapshotParityMatches ? "success" : "warning"}>
                  {snapshotParityMatches
                    ? t("runtime.diagnostics.snapshotParityMatch")
                    : t("runtime.diagnostics.snapshotParityMismatch")}
                </Badge>
              )}
              <div className="grid gap-2 xl:grid-cols-2">
                {componentSnapshot?.map((component) => {
                  const componentHealth = healthTone(component.health);
                  return (
                    <div
                      key={component.component_id || `${component.backend || "component"}-${component.model_id || "unknown"}`}
                      className="rounded-2xl box-muted px-4 py-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-white">
                            {component.component_id || t("runtime.diagnostics.runtimeComponent")}
                          </p>
                          <p className="text-[11px] text-zinc-500">
                            {component.component_type ?? t("runtime.diagnostics.runtimeComponent")}
                            {component.model_id ? ` · ${component.model_id}` : ""}
                          </p>
                        </div>
                        <Badge tone={componentHealth}>
                          {healthLabel(t, component.health)}
                        </Badge>
                      </div>
                      <div className="mt-2 grid gap-1 text-[11px] text-zinc-400">
                        <p>
                          {t("runtime.diagnostics.backend")}:{" "}
                          <span className="text-zinc-200">{component.backend ?? "—"}</span>
                          {" · "}{t("runtime.diagnostics.device")}:{" "}
                          <span className="text-zinc-200">{component.device_target ?? "—"}</span>
                        </p>
                        <p>
                          {t("runtime.diagnostics.enabled")}:{" "}
                          <span className="text-zinc-200">
                            {component.enabled ? t("runtime.diagnostics.yes") : t("runtime.diagnostics.no")}
                          </span>
                          {" · "}{t("runtime.diagnostics.available")}:{" "}
                          <span className="text-zinc-200">
                            {component.available ? t("runtime.diagnostics.yes") : t("runtime.diagnostics.no")}
                          </span>
                        </p>
                        {component.last_error && (
                          <p className="text-amber-200">{component.last_error}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {hasDegradations && (
            <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 px-4 py-3">
              <p className="text-caption text-amber-100">{t("runtime.diagnostics.degradations")}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {degradationReasons?.map((reason) => (
                  <Badge key={reason} tone="warning">
                    {reason}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <EmptyState
          title={resolvedEmptyStateTitle}
          description={resolvedEmptyStateDescription}
        />
      )}
    </Panel>
  );
}

export type {
  RuntimeSummaryItem,
  RuntimeComponentSnapshotItem,
  RuntimeDiagnosticsPanelProps,
  RuntimeTraceAnnotationItem,
};
