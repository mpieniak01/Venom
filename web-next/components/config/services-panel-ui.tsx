"use client";

import { Activity, Play, RotateCw, Square, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  ActionHistory,
  ServiceInfo,
  StorageSnapshot,
} from "./services-panel-types";
import {
  formatBytes,
  formatStorageTimestamp,
  formatUptime,
  getDisplayName,
  getServiceIcon,
  getStatusBadge,
  getStatusColor,
} from "./services-panel-utils";

type TranslateFn = (key: string) => string;

export function ServicesProfilesCard(input: Readonly<{
  t: TranslateFn;
  loading: boolean;
  applyProfile: (profileName: string) => Promise<void>;
}>) {
  const { t, loading, applyProfile } = input;
  return (
    <div className="glass-panel rounded-2xl box-subtle p-6">
      <h2 className="mb-4 heading-h2">{t("config.services.profiles.title")}</h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Button onClick={() => void applyProfile("full")} disabled={loading} variant="primary" className="w-full">
          <Zap className="mr-2 h-4 w-4" />
          {t("config.services.profiles.full")}
        </Button>
        <Button onClick={() => void applyProfile("light")} disabled={loading} variant="secondary" className="w-full">
          <Activity className="mr-2 h-4 w-4" />
          {t("config.services.profiles.light")}
        </Button>
        <Button onClick={() => void applyProfile("llm_off")} disabled={loading} variant="secondary" className="w-full">
          <Square className="mr-2 h-4 w-4" />
          {t("config.services.profiles.llmOff")}
        </Button>
      </div>
      <p className="mt-3 text-xs text-theme-muted">{t("config.services.profiles.description")}</p>
    </div>
  );
}

function ServiceCardSkeleton() {
  return (
    <div className="glass-panel rounded-2xl box-subtle p-4 h-[180px] animate-pulse flex flex-col justify-between">
      <div className="flex justify-between items-start">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 bg-white/10 rounded-xl" />
          <div className="h-5 w-24 bg-white/10 rounded" />
        </div>
        <div className="h-5 w-16 bg-white/10 rounded-full" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="h-8 bg-theme-overlay rounded-lg" />
        <div className="h-8 bg-theme-overlay rounded-lg" />
        <div className="h-8 bg-theme-overlay rounded-lg" />
      </div>
      <div className="h-8 w-full bg-theme-overlay rounded-lg" />
    </div>
  );
}

function ServiceCard(input: Readonly<{
  t: TranslateFn;
  service: ServiceInfo;
  actionInProgress: string | null;
  loading: boolean;
  executeAction: (service: string, action: string) => Promise<void>;
}>) {
  const { t, service, actionInProgress, loading, executeAction } = input;
  const isRunning = service.status === "running";
  const actionKey = `${service.service_type}`;

  return (
    <div key={`${service.service_type}-${service.name}`} className="glass-panel rounded-2xl box-subtle p-4">
      <div className="mb-3 flex items-start justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className={`${getStatusColor(service.status)}`}>{getServiceIcon(service.service_type)}</div>
          <div className="flex min-w-0 items-center gap-2">
            <h4 className="heading-h4 truncate">{getDisplayName(service.name, t)}</h4>
            <span
              className="shrink-0 whitespace-nowrap text-[11px] font-mono text-emerald-400"
              aria-label={`${t("config.services.info.version")}: ${
                service.runtime_version || t("config.services.info.versionUnknown")
              }`}
            >
              V {service.runtime_version || t("config.services.info.versionUnknown")}
            </span>
          </div>
        </div>
        <span className={`pill-badge ${getStatusBadge(service.status)}`}>{service.status}</span>
      </div>

      <div className="mb-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-theme-muted">{t("config.services.info.pid")}</p>
          <p className="font-mono text-[11px] text-theme-primary">{service.pid || "—"}</p>
        </div>
        <div className="space-y-2">
          <div>
            <p className="text-theme-muted">{t("config.services.info.port")}</p>
            <p className="font-mono text-[11px] text-theme-primary">{service.port || "—"}</p>
          </div>
          <div>
            <p className="text-theme-muted">{t("config.services.info.ram")}</p>
            <p className="font-mono text-[11px] text-theme-primary">
              {isRunning ? `${service.memory_mb.toFixed(0)} MB` : "—"}
            </p>
          </div>
        </div>
        <div className="space-y-2">
          <div>
            <p className="text-theme-muted">{t("config.services.info.uptime")}</p>
            <p className="font-mono text-[11px] text-theme-primary">{formatUptime(service.uptime_seconds)}</p>
          </div>
          <div>
            <p className="text-theme-muted">{t("config.services.info.cpu")}</p>
            <p className="font-mono text-[11px] text-theme-primary">
              {isRunning ? `${service.cpu_percent.toFixed(1)}%` : "—"}
            </p>
          </div>
        </div>
      </div>

      {service.error_message ? (
        <div className="mb-3 rounded-lg bg-red-500/10 p-2">
          <p className="text-[11px] text-red-400">{service.error_message}</p>
        </div>
      ) : null}

      {service.actionable ? (
        <div className="flex gap-2">
          <Button
            onClick={() => void executeAction(service.service_type, "start")}
            disabled={isRunning || actionInProgress === `${actionKey}-start` || loading}
            variant="secondary"
            size="sm"
            className="flex-1 h-8 border border-emerald-500/30 bg-emerald-500/10 px-2 text-xs text-emerald-200 hover:bg-emerald-500/20"
          >
            <Play className="mr-1 h-3 w-3" />
            {t("config.services.actions.start")}
          </Button>
          <Button
            onClick={() => void executeAction(service.service_type, "stop")}
            disabled={!isRunning || actionInProgress === `${actionKey}-stop` || loading}
            variant="secondary"
            size="sm"
            className="flex-1 h-8 border border-red-500/30 bg-red-500/10 px-2 text-xs text-red-200 hover:bg-red-500/20"
          >
            <Square className="mr-1 h-3 w-3" />
            {t("config.services.actions.stop")}
          </Button>
          <Button
            onClick={() => void executeAction(service.service_type, "restart")}
            disabled={actionInProgress === `${actionKey}-restart` || loading}
            variant="secondary"
            size="sm"
            className="flex-1 h-8 border border-yellow-500/30 bg-yellow-500/10 px-2 text-xs text-yellow-200 hover:bg-yellow-500/20"
          >
            <RotateCw className="mr-1 h-3 w-3" />
            {t("config.services.actions.restart")}
          </Button>
        </div>
      ) : (
        <div className="rounded-lg bg-blue-500/10 p-2 border border-blue-500/30">
          <p className="text-[11px] text-blue-300 text-center">{t("config.services.managedByConfig")}</p>
        </div>
      )}
    </div>
  );
}

export function ServicesGrid(input: Readonly<{
  t: TranslateFn;
  servicesLoading: boolean;
  services: ServiceInfo[];
  actionInProgress: string | null;
  loading: boolean;
  executeAction: (service: string, action: string) => Promise<void>;
}>) {
  const { t, servicesLoading, services, actionInProgress, loading, executeAction } =
    input;
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {servicesLoading
        ? [1, 2, 3, 4, 5, 6, 7, 8].map((i) => <ServiceCardSkeleton key={i} />)
        : services.map((service) => (
            <ServiceCard
              key={`${service.service_type}-${service.name}`}
              t={t}
              service={service}
              actionInProgress={actionInProgress}
              loading={loading}
              executeAction={executeAction}
            />
          ))}
    </div>
  );
}

export function ServicesStorageCard(input: Readonly<{
  t: TranslateFn;
  language: string;
  storageSnapshot: StorageSnapshot | null;
  storageLoading: boolean;
  storageError: string | null;
  onRefreshStorage: () => Promise<void>;
}>) {
  const { t, language, storageSnapshot, storageLoading, storageError, onRefreshStorage } =
    input;
  const storageItems = storageSnapshot?.items ?? [];
  const totalBytes = storageSnapshot?.disk_root?.used_bytes ?? 0;
  const itemsToRender = storageItems.filter((item) => item.name !== "project_root");
  let storageSummary = <span>{t("config.services.storage.noData")}</span>;
  if (storageSnapshot?.disk_root) {
    storageSummary = (
      <div className="flex flex-col gap-1">
        <span>
          {t("config.services.storage.wslUsage")}:{" "}
          <span className="font-semibold text-theme-primary">
            {formatBytes(
              storageSnapshot.disk_root.used_bytes ??
                Math.max(
                  (storageSnapshot.disk_root.total_bytes ?? 0) -
                    (storageSnapshot.disk_root.free_bytes ?? 0),
                  0
                )
            )}
          </span>
        </span>
      </div>
    );
  } else if (storageSnapshot?.disk) {
    storageSummary = (
      <span className="text-sm">
        {t("config.services.storage.physical")}:{" "}
        <span className="font-semibold text-theme-primary">
          {formatBytes(storageSnapshot.disk.total_bytes)}
        </span>
      </span>
    );
  }

  return (
    <div className="glass-panel rounded-2xl box-subtle p-6">
      <h2 className="mb-4 heading-h2">{t("config.services.storage.title")}</h2>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-theme-secondary">{storageSummary}</div>
        <Button
          size="xs"
          variant="outline"
          className="rounded-full"
          onClick={() => {
            onRefreshStorage().catch(() => undefined);
          }}
          disabled={storageLoading}
        >
          {storageLoading
            ? t("config.services.storage.refreshing")
            : t("config.services.storage.refresh")}
        </Button>
      </div>
      {storageSnapshot?.refreshed_at ? (
        <p className="mt-2 text-xs text-theme-muted">
          {t("config.services.storage.lastCheck")}:{" "}
          {formatStorageTimestamp(storageSnapshot.refreshed_at, language)}
        </p>
      ) : null}
      {itemsToRender.length > 0 ? (
        <div className="mt-4 overflow-hidden rounded-xl border border-theme bg-gradient-to-br from-emerald-500/5 via-cyan-500/5 to-transparent">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 bg-theme-overlay-strong px-3 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-theme-muted">
              {t("config.services.storage.breakdown")}
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-theme-muted">
              {t("config.services.storage.used")}
            </span>
          </div>
          <div className="max-h-64 space-y-1 overflow-auto p-1">
            {itemsToRender.map((item) => {
              const translatedName = t(`config.services.storage.items.${item.name}`);
              const itemLabel =
                translatedName === `config.services.storage.items.${item.name}`
                  ? item.name
                  : translatedName;
              const percent =
                totalBytes > 0 ? Math.min((item.size_bytes / totalBytes) * 100, 100) : 0;
              return (
                <div
                  key={`${item.name}-${item.path}`}
                  className="rounded-md bg-theme-overlay/25 px-3 py-2 transition-colors hover:bg-theme-overlay-strong/40"
                >
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                    <div className="flex min-w-0 items-center gap-2" title={`${itemLabel} • ${item.path}`}>
                      <p className="eyebrow truncate text-theme-secondary">{itemLabel}</p>
                      <span className="font-mono text-[11px] text-cyan-300">{percent.toFixed(1)}%</span>
                    </div>
                    <p className="text-right font-mono text-xs text-theme-secondary">{formatBytes(item.size_bytes)}</p>
                  </div>
                  <div className="mt-1.5 h-1.5 w-full rounded-full bg-cyan-500/15">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-emerald-400 to-teal-400 shadow-[0_0_12px_rgba(45,212,191,0.45)] transition-[width] duration-700 ease-out"
                      style={{ width: `${percent.toFixed(1)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      {storageError ? <p className="mt-3 text-xs text-rose-300">{storageError}</p> : null}
    </div>
  );
}

export function ServicesHistoryCard(input: Readonly<{
  t: TranslateFn;
  language: string;
  history: ActionHistory[];
}>) {
  const { t, language, history } = input;
  return (
    <div className="glass-panel rounded-2xl box-subtle p-6">
      <h2 className="mb-4 heading-h2">{t("config.services.history.title")}</h2>
      <div className="space-y-2">
        {history.length === 0 ? (
          <p className="text-sm text-theme-muted">{t("config.services.history.empty")}</p>
        ) : (
          history.map((entry) => (
            <div
              key={`${entry.timestamp}-${entry.service}-${entry.action}-${entry.message}`}
              className="flex items-center justify-between rounded-lg border border-theme bg-theme-overlay-strong p-3"
            >
              <div className="flex items-center gap-3">
                <span className={`inline-block h-2 w-2 rounded-full ${entry.success ? "bg-emerald-400" : "bg-red-400"}`} />
                <div>
                  <p className="text-sm font-medium text-theme-primary">
                    {getDisplayName(entry.service, t)} →{" "}
                    {t(`config.services.actions.${entry.action.toLowerCase()}`) || entry.action}
                  </p>
                  <p className="text-xs text-theme-muted">{entry.message}</p>
                </div>
              </div>
              <p className="text-xs text-theme-muted">
                {new Date(entry.timestamp).toLocaleTimeString(language === "pl" ? "pl-PL" : "en-US")}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
