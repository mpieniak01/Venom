"use client";

import { useCallback, useEffect, useState } from "react";
import { Play, Square, RotateCw, Zap, Layout, Cpu, Activity, Plug, Brain } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation, useLanguage } from "@/lib/i18n";
import { VenomWebSocket } from "@/lib/ws-client";

interface ServiceInfo {
  name: string;
  service_type: string;
  status: "running" | "stopped" | "unknown" | "error" | "degraded";
  pid: number | null;
  port: number | null;
  cpu_percent: number;
  memory_mb: number;
  uptime_seconds: number | null;
  last_log: string | null;
  error_message: string | null;
  actionable: boolean;
}

interface ServiceEvent {
  type: string;
  data: Partial<ServiceInfo> & { status: string };
}

interface ActionHistory {
  timestamp: string;
  service: string;
  action: string;
  success: boolean;
  message: string;
}

interface StorageSnapshot {
  refreshed_at?: string;
  disk?: {
    total_bytes?: number;
    used_bytes?: number;
    free_bytes?: number;
  };
  disk_root?: {
    total_bytes?: number;
    used_bytes?: number;
    free_bytes?: number;
  };
  items?: Array<{
    name: string;
    path: string;
    size_bytes: number;
    kind: string;
  }>;
}

const runtimeToServiceStatus: Record<string, ServiceInfo["status"]> = {
  online: "running",
  offline: "stopped",
  degraded: "degraded",
  unknown: "unknown",
};

function normalizeServiceStatus(status: string | undefined): ServiceInfo["status"] {
  if (!status) return "unknown";
  const normalized = status.toLowerCase();
  if (normalized in runtimeToServiceStatus) return runtimeToServiceStatus[normalized];
  if (normalized === "running" || normalized === "stopped" || normalized === "error" || normalized === "degraded") {
    return normalized;
  }
  return "unknown";
}

function mergeServiceUpdate(
  service: ServiceInfo,
  update: Partial<ServiceInfo> & { status: string },
): ServiceInfo {
  return {
    ...service,
    ...update,
    status: normalizeServiceStatus(update.status),
  };
}

function applyServiceEventUpdate(
  services: ServiceInfo[],
  update: Partial<ServiceInfo> & { status: string; name?: string },
): ServiceInfo[] {
  if (!update.name) return services;
  const normalizedName = update.name.toLowerCase();
  return services.map((service) =>
    service.name.toLowerCase() === normalizedName ? mergeServiceUpdate(service, update) : service,
  );
}

export function ServicesPanel() {
  const t = useTranslation();
  const { language } = useLanguage();
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [servicesLoading, setServicesLoading] = useState(true);
  const [history, setHistory] = useState<ActionHistory[]>([]);
  const [storageSnapshot, setStorageSnapshot] = useState<StorageSnapshot | null>(null);
  const [storageLoading, setStorageLoading] = useState(false);
  const [storageError, setStorageError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(
    null
  );

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/runtime/status").catch((error) => {
        console.warn("Błąd sieci przy pobieraniu statusu usług:", error);
        setMessage({
          type: "error",
          text: t("config.services.status.apiStatusError"),
        });
        return null;
      });

      if (!response) return;

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `${t("config.services.status.apiStatusError")} (HTTP ${response.status})`;
        console.warn("Błąd pobierania statusu (HTTP):", response.status, errorText);
        setMessage({ type: "error", text: errorMessage });
        return;
      }

      const data = await response.json();
      if (data.status === "success") {
        setServices(data.services);
      } else {
        const errorMessage = data.message || t("config.services.status.apiStatusError");
        setMessage({ type: "error", text: errorMessage });
      }
    } catch (error) {
      console.warn("Błąd pobierania statusu:", error);
      setMessage({
        type: "error",
        text: t("config.services.status.apiStatusError"),
      });
    } finally {
      setServicesLoading(false);
    }
  }, [t]);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/runtime/history?limit=10").catch((error) => {
        console.warn("Błąd sieci przy pobieraniu historii akcji:", error);
        setMessage({
          type: "error",
          text: t("config.services.history.apiHistoryError"),
        });
        return null;
      });

      if (!response) return;

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `${t("config.services.history.apiHistoryError")} (HTTP ${response.status})`;
        console.error("Błąd pobierania historii (HTTP):", response.status, errorText);
        setMessage({ type: "error", text: errorMessage });
        return;
      }

      const data = await response.json();
      if (data.status === "success") {
        setHistory(data.history);
      } else {
        const errorMessage = data.message || t("config.services.history.apiHistoryError");
        setMessage({ type: "error", text: errorMessage });
      }
    } catch (error) {
      console.error("Błąd pobierania historii:", error);
      setMessage({
        type: "error",
        text: t("config.services.history.apiHistoryError"),
      });
    }
  }, [t]);

  const fetchStorageSnapshot = useCallback(async () => {
    setStorageLoading(true);
    setStorageError(null);
    try {
      const response = await fetch("/api/v1/system/storage").catch(() => {
        setStorageError(t("config.services.storage.apiError"));
        return null;
      });

      if (!response) {
        setStorageLoading(false);
        return;
      }
      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `${t("config.services.storage.apiError")} (HTTP ${response.status})`;
        setStorageError(errorMessage);
        return;
      }
      const data = (await response.json()) as { status?: string } & StorageSnapshot & {
        message?: string;
      };
      if (data.status === "success") {
        setStorageSnapshot(data);
      } else {
        setStorageError(data.message || t("config.services.storage.apiError"));
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t("config.services.storage.apiError");
      setStorageError(errorMessage);
    } finally {
      setStorageLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchStatus();
    fetchHistory();
    fetchStorageSnapshot();

    // Połącz przez WebSocket dla aktualizacji statusów w czasie rzeczywistym
    const ws = new VenomWebSocket("/ws/events", (payload: unknown) => {
      const event = payload as ServiceEvent;
      if (event.type === "SERVICE_STATUS_UPDATE" && event.data && event.data.name) {
        setServices((prevServices) =>
          applyServiceEventUpdate(
            prevServices,
            event.data as Partial<ServiceInfo> & { status: string; name?: string },
          ),
        );
      }
    });

    ws.connect();

    // Odświeżaj status co 10 sekund (jako fallback dla WS)
    const interval = setInterval(() => {
      fetchStatus();
    }, 10000);

    return () => {
      clearInterval(interval);
      ws.disconnect();
    };
  }, [fetchStatus, fetchHistory, fetchStorageSnapshot]);

  const executeAction = async (service: string, action: string) => {
    const actionKey = `${service}-${action}`;
    setActionInProgress(actionKey);
    setMessage(null);

    try {
      const response = await fetch(`/api/v1/runtime/${service}/${action}`, {
        method: "POST",
      });
      const data = await response.json();

      if (data.success) {
        setMessage({ type: "success", text: data.message });
      } else {
        setMessage({ type: "error", text: data.message });
      }

      // Odśwież status i historię
      await Promise.all([fetchStatus(), fetchHistory()]);
    } catch (error) {
      setMessage({
        type: "error",
        text: error instanceof Error ? error.message : t("config.services.status.apiStatusError"),
      });
    } finally {
      setActionInProgress(null);
    }
  };

  const applyProfile = async (profileName: string) => {
    setLoading(true);
    setMessage(null);

    try {
      const response = await fetch(`/api/v1/runtime/profile/${profileName}`, {
        method: "POST",
      });
      const data = await response.json();

      if (data.success) {
        setMessage({ type: "success", text: data.message });
      } else {
        setMessage({ type: "error", text: data.message });
      }

      // Odśwież status i historię
      await Promise.all([fetchStatus(), fetchHistory()]);
    } catch (error) {
      setMessage({
        type: "error",
        text: error instanceof Error ? error.message : t("config.services.status.apiStatusError"),
      });
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running":
        return "text-emerald-400";
      case "stopped":
        return "text-zinc-500";
      case "degraded":
        return "text-yellow-400";
      case "error":
        return "text-red-400";
      default:
        return "text-yellow-400";
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "running":
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
      case "stopped":
        return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
      case "degraded":
        return "bg-yellow-500/20 text-yellow-300 border-yellow-500/30";
      case "error":
        return "bg-red-500/20 text-red-300 border-red-500/30";
      default:
        return "bg-yellow-500/20 text-yellow-300 border-yellow-500/30";
    }
  };

  const formatUptime = (seconds: number | null) => {
    if (!seconds) return "N/A";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  const getServiceIcon = (serviceType: string) => {
    switch (serviceType) {
      case "backend":
        return <Cpu className="h-5 w-5" />;
      case "ui":
        return <Layout className="h-5 w-5" />;
      case "llm_ollama":
      case "llm_vllm":
        return <Zap className="h-5 w-5" />;
      case "mcp":
        return <Plug className="h-5 w-5" />;
      case "orchestrator":
        return <Brain className="h-5 w-5" />;
      default:
        return <Activity className="h-5 w-5" />;
    }
  };

  const getDisplayName = (raw: string) => {
    const key = raw.toLowerCase().replaceAll(/\s+/g, "_");
    const translated = t(`config.services.names.${key}`);
    if (translated && translated !== `config.services.names.${key}`) {
      return translated;
    }
    // Fallback: replacement of underscores with spaces + capitalization of the first letter
    const pretty = raw.replaceAll(/[_-]+/g, " ").replaceAll(/\b\w/g, (m) => m.toUpperCase());
    return pretty;
  };

  const formatBytes = (value?: number) => {
    if (typeof value !== "number" || Number.isNaN(value)) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let index = 0;
    let current = value;
    while (current >= 1024 && index < units.length - 1) {
      current /= 1024;
      index += 1;
    }
    const digits = current >= 100 || index === 0 ? 0 : 1;
    return `${current.toFixed(digits)} ${units[index]}`;
  };

  const formatStorageTimestamp = (value?: string) => {
    if (!value) return "—";
    const parsed = Date.parse(value);
    if (Number.isNaN(parsed)) return value;
    const locale = language === "pl" ? "pl-PL" : language === "de" ? "de-DE" : "en-US";
    return new Date(parsed).toLocaleString(locale);
  };

  return (
    <div className="space-y-6">
      {/* Message */}
      {message && (
        <div className={`alert ${message.type === "success" ? "alert--success" : "alert--error"}`}>
          {message.text}
        </div>
      )}

      {/* Profiles */}
      <div className="glass-panel rounded-2xl box-subtle p-6">
        <h2 className="mb-4 heading-h2">{t("config.services.profiles.title")}</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Button
            onClick={() => applyProfile("full")}
            disabled={loading}
            variant="primary"
            className="w-full"
          >
            <Zap className="mr-2 h-4 w-4" />
            {t("config.services.profiles.full")}
          </Button>
          <Button
            onClick={() => applyProfile("light")}
            disabled={loading}
            variant="secondary"
            className="w-full"
          >
            <Activity className="mr-2 h-4 w-4" />
            {t("config.services.profiles.light")}
          </Button>
          <Button
            onClick={() => applyProfile("llm_off")}
            disabled={loading}
            variant="secondary"
            className="w-full"
          >
            <Square className="mr-2 h-4 w-4" />
            {t("config.services.profiles.llmOff")}
          </Button>
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          {t("config.services.profiles.description")}
        </p>
      </div>

      {/* Services Grid */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {servicesLoading ? (
          [1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div
              key={i}
              className="glass-panel rounded-2xl box-subtle p-4 h-[180px] animate-pulse flex flex-col justify-between"
            >
              <div className="flex justify-between items-start">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 bg-white/10 rounded-xl" />
                  <div className="h-5 w-24 bg-white/10 rounded" />
                </div>
                <div className="h-5 w-16 bg-white/10 rounded-full" />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="h-8 bg-white/5 rounded-lg" />
                <div className="h-8 bg-white/5 rounded-lg" />
                <div className="h-8 bg-white/5 rounded-lg" />
              </div>
              <div className="h-8 w-full bg-white/5 rounded-lg" />
            </div>
          ))
        ) : (
          services.map((service) => {
            const isRunning = service.status === "running";
            const actionKey = `${service.service_type}`;

            return (
              <div
                key={`${service.service_type}-${service.name}`}
                className="glass-panel rounded-2xl box-subtle p-4"
              >
                {/* Header */}
                <div className="mb-3 flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`${getStatusColor(service.status)}`}>
                      {getServiceIcon(service.service_type)}
                    </div>
                    <h4 className="heading-h4">{getDisplayName(service.name)}</h4>
                  </div>
                  <span className={`pill-badge ${getStatusBadge(service.status)}`}>
                    {service.status}
                  </span>
                </div>

                {/* Info */}
                <div className="mb-3 grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <p className="text-zinc-500">{t("config.services.info.pid")}</p>
                    <p className="font-mono text-[11px] text-white">{service.pid || "—"}</p>
                  </div>
                  <div className="space-y-2">
                    <div>
                      <p className="text-zinc-500">{t("config.services.info.port")}</p>
                      <p className="font-mono text-[11px] text-white">{service.port || "—"}</p>
                    </div>
                    <div>
                      <p className="text-zinc-500">{t("config.services.info.ram")}</p>
                      <p className="font-mono text-[11px] text-white">
                        {isRunning ? `${service.memory_mb.toFixed(0)} MB` : "—"}
                      </p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div>
                      <p className="text-zinc-500">{t("config.services.info.uptime")}</p>
                      <p className="font-mono text-[11px] text-white">
                        {formatUptime(service.uptime_seconds)}
                      </p>
                    </div>
                    <div>
                      <p className="text-zinc-500">{t("config.services.info.cpu")}</p>
                      <p className="font-mono text-[11px] text-white">
                        {isRunning ? `${service.cpu_percent.toFixed(1)}%` : "—"}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Error */}
                {service.error_message && (
                  <div className="mb-3 rounded-lg bg-red-500/10 p-2">
                    <p className="text-[11px] text-red-400">{service.error_message}</p>
                  </div>
                )}

                {/* Actions or Info Badge */}
                {service.actionable ? (
                  <div className="flex gap-2">
                    <Button
                      onClick={() => executeAction(service.service_type, "start")}
                      disabled={
                        isRunning || actionInProgress === `${actionKey}-start` || loading
                      }
                      variant="secondary"
                      size="sm"
                      className="flex-1 h-8 border border-emerald-500/30 bg-emerald-500/10 px-2 text-xs text-emerald-200 hover:bg-emerald-500/20"
                    >
                      <Play className="mr-1 h-3 w-3" />
                      {t("config.services.actions.start")}
                    </Button>
                    <Button
                      onClick={() => executeAction(service.service_type, "stop")}
                      disabled={
                        !isRunning || actionInProgress === `${actionKey}-stop` || loading
                      }
                      variant="secondary"
                      size="sm"
                      className="flex-1 h-8 border border-red-500/30 bg-red-500/10 px-2 text-xs text-red-200 hover:bg-red-500/20"
                    >
                      <Square className="mr-1 h-3 w-3" />
                      {t("config.services.actions.stop")}
                    </Button>
                    <Button
                      onClick={() => executeAction(service.service_type, "restart")}
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
                    <p className="text-[11px] text-blue-300 text-center">
                      {t("config.services.managedByConfig")}
                    </p>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Storage */}
      <div className="glass-panel rounded-2xl box-subtle p-6">
        <h2 className="mb-4 heading-h2">{t("config.services.storage.title")}</h2>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-zinc-200">
            {storageSnapshot?.disk_root ? (
              <div className="flex flex-col gap-1">
                {(() => {
                  const total = storageSnapshot.disk_root!.total_bytes ?? 0;
                  const free = storageSnapshot.disk_root!.free_bytes ?? 0;
                  const used =
                    storageSnapshot.disk_root!.used_bytes ?? Math.max(total - free, 0);
                  return (
                    <span>
                      {t("config.services.storage.wslUsage")}:{" "}
                      <span className="font-semibold text-white">
                        {formatBytes(used)}
                      </span>
                    </span>
                  );
                })()}
                {storageSnapshot.disk ? (
                  <div className="mt-1 pt-1 border-t border-white/5 text-xs text-zinc-400">
                    {t("config.services.storage.physical")}:{" "}
                    <span className="font-semibold text-white">
                      {formatBytes(storageSnapshot.disk.total_bytes)}
                    </span>
                    <span className="mx-2 opacity-40">|</span>
                    {t("config.services.storage.used")}: <span className="text-white">{formatBytes(storageSnapshot.disk.used_bytes)}</span>
                    <span className="mx-2 opacity-40">|</span>
                    {t("config.services.storage.free")}: <span className="text-emerald-400">{formatBytes(storageSnapshot.disk.free_bytes)}</span>
                  </div>
                ) : null}
              </div>
            ) : storageSnapshot?.disk ? (
              <span className="text-sm">
                {t("config.services.storage.physical")}:{" "}
                <span className="font-semibold text-white">
                  {formatBytes(storageSnapshot.disk.total_bytes)}
                </span>
                <span className="mx-2 text-zinc-600">|</span>
                <span className="text-xs text-zinc-400">
                  {t("config.services.storage.used")}: <span className="text-white">{formatBytes(storageSnapshot.disk.used_bytes)}</span>
                  {" "}/ {t("config.services.storage.free")}: <span className="text-emerald-400">{formatBytes(storageSnapshot.disk.free_bytes)}</span>
                </span>
              </span>
            ) : (
              <span>{t("config.services.storage.noData")}</span>
            )}
          </div>
          <Button
            size="xs"
            variant="outline"
            className="rounded-full"
            onClick={fetchStorageSnapshot}
            disabled={storageLoading}
          >
            {storageLoading ? t("config.services.storage.refreshing") : t("config.services.storage.refresh")}
          </Button>
        </div>
        {storageSnapshot?.refreshed_at ? (
          <p className="mt-2 text-xs text-zinc-500">
            {t("config.services.storage.lastCheck")}: {formatStorageTimestamp(storageSnapshot.refreshed_at)}
          </p>
        ) : null}
        {storageError ? (
          <p className="mt-3 text-xs text-rose-300">{storageError}</p>
        ) : storageLoading && !storageSnapshot ? (
          <div className="mt-4 grid gap-2 md:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="flex flex-col gap-2 rounded-2xl border border-white/5 bg-white/5 px-4 py-3 animate-pulse"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-24 bg-white/10 rounded" />
                    <div className="h-3 w-16 bg-white/5 rounded" />
                  </div>
                  <div className="h-4 w-12 bg-white/10 rounded" />
                </div>
                <div className="h-3 w-3/4 bg-white/5 rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-4 grid gap-2 md:grid-cols-3">
            {(storageSnapshot?.items ?? [])
              .slice()
              .sort((a, b) => b.size_bytes - a.size_bytes)
              .map((item) => (
                <div
                  key={`${item.path}:${item.name}`}
                  className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-xs"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-white">
                        {t(`config.services.storage.items.${item.name}`) || item.name}
                      </p>
                      <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">
                        {item.kind}
                      </p>
                    </div>
                    <p className="text-sm font-semibold text-white text-right">
                      {formatBytes(item.size_bytes)}
                    </p>
                  </div>
                  <p className="min-w-0 text-[11px] text-zinc-500">{item.path}</p>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* History */}
      <div className="glass-panel rounded-2xl box-subtle p-6">
        <h2 className="mb-4 heading-h2">{t("config.services.history.title")}</h2>
        <div className="space-y-2">
          {history.length === 0 ? (
            <p className="text-sm text-zinc-500">{t("config.services.history.empty")}</p>
          ) : (
            history.map((entry, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-lg border border-white/5 bg-black/20 p-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${entry.success ? "bg-emerald-400" : "bg-red-400"
                      }`}
                  />
                  <div>
                    <p className="text-sm font-medium text-white">
                      {getDisplayName(entry.service)} → {t(`config.services.actions.${entry.action.toLowerCase()}`) || entry.action}
                    </p>
                    <p className="text-xs text-zinc-500">{entry.message}</p>
                  </div>
                </div>
                <p className="text-xs text-zinc-600">
                  {new Date(entry.timestamp).toLocaleTimeString(language === "pl" ? "pl-PL" : "en-US")}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
