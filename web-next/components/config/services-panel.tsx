"use client";

import { useCallback, useEffect, useState } from "react";
import { Play, Square, RotateCw, Zap, Layout, Cpu, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ServiceInfo {
  name: string;
  service_type: string;
  status: "running" | "stopped" | "unknown" | "error";
  pid: number | null;
  port: number | null;
  cpu_percent: number;
  memory_mb: number;
  uptime_seconds: number | null;
  last_log: string | null;
  error_message: string | null;
  actionable: boolean;
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
  items?: Array<{
    name: string;
    path: string;
    size_bytes: number;
    kind: string;
  }>;
}

export function ServicesPanel() {
  const [services, setServices] = useState<ServiceInfo[]>([]);
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
      const response = await fetch("/api/v1/runtime/status");

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `Nie udało się pobrać statusu usług (HTTP ${response.status})`;
        console.error("Błąd pobierania statusu (HTTP):", response.status, errorText);
        setMessage({ type: "error", text: errorMessage });
        return;
      }

      const data = await response.json();
      if (data.status === "success") {
        setServices(data.services);
      } else {
        const errorMessage = data.message || "Nie udało się pobrać statusu usług";
        setMessage({ type: "error", text: errorMessage });
      }
    } catch (error) {
      // TODO: Replace with proper error reporting service
      console.error("Błąd pobierania statusu:", error);
      setMessage({
        type: "error",
        text: "Wystąpił błąd podczas pobierania statusu usług",
      });
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/runtime/history?limit=10");

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `Nie udało się pobrać historii akcji (HTTP ${response.status})`;
        console.error("Błąd pobierania historii (HTTP):", response.status, errorText);
        setMessage({ type: "error", text: errorMessage });
        return;
      }

      const data = await response.json();
      if (data.status === "success") {
        setHistory(data.history);
      } else {
        const errorMessage = data.message || "Nie udało się pobrać historii akcji";
        setMessage({ type: "error", text: errorMessage });
      }
    } catch (error) {
      // TODO: Replace with proper error reporting service
      console.error("Błąd pobierania historii:", error);
      setMessage({
        type: "error",
        text: "Wystąpił błąd podczas pobierania historii akcji",
      });
    }
  }, []);

  const fetchStorageSnapshot = useCallback(async () => {
    setStorageLoading(true);
    setStorageError(null);
    try {
      const response = await fetch("/api/v1/system/storage");
      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `Nie udało się pobrać danych storage (HTTP ${response.status})`;
        setStorageError(errorMessage);
        return;
      }
      const data = (await response.json()) as { status?: string } & StorageSnapshot & {
        message?: string;
      };
      if (data.status === "success") {
        setStorageSnapshot(data);
      } else {
        setStorageError(data.message || "Nie udało się pobrać danych storage.");
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Błąd pobierania danych storage.";
      setStorageError(errorMessage);
    } finally {
      setStorageLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchHistory();
    fetchStorageSnapshot();

    // Odświeżaj status co 5 sekund
    const interval = setInterval(() => {
      fetchStatus();
    }, 5000);

    return () => clearInterval(interval);
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
        text: error instanceof Error ? error.message : "Błąd komunikacji z API",
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
        text: error instanceof Error ? error.message : "Błąd komunikacji z API",
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
      default:
        return <Activity className="h-5 w-5" />;
    }
  };

  const getDisplayName = (raw: string) => {
    const name = raw.toLowerCase();
    if (name === "backend") return "Backend API";
    if (name === "ui") return "Next.js UI";
    if (name === "llm_ollama") return "Ollama";
    if (name === "llm_vllm") return "vLLM";
    if (name === "background_tasks") return "Background Tasks";
    if (name === "local llm") return "Local LLM";
    // Fallback: zamiana podkreśleń na spacje + kapitalizacja pierwszej litery
    const pretty = raw.replace(/[_-]+/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
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
    return new Date(parsed).toLocaleString("pl-PL");
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
        <h2 className="mb-4 heading-h2">Profile szybkie</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Button
            onClick={() => applyProfile("full")}
            disabled={loading}
            variant="primary"
            className="w-full"
          >
            <Zap className="mr-2 h-4 w-4" />
            Full Stack
          </Button>
          <Button
            onClick={() => applyProfile("light")}
            disabled={loading}
            variant="secondary"
            className="w-full"
          >
            <Activity className="mr-2 h-4 w-4" />
            Light (bez LLM)
          </Button>
          <Button
            onClick={() => applyProfile("llm_off")}
            disabled={loading}
            variant="secondary"
            className="w-full"
          >
            <Square className="mr-2 h-4 w-4" />
            LLM OFF
          </Button>
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          Profile szybko ustawiają zestaw usług: Full uruchamia wszystko, Light tylko backend i UI,
          LLM OFF wyłącza modele językowe.
        </p>
      </div>

      {/* Services Grid */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {services.map((service) => {
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
                  <p className="text-zinc-500">PID</p>
                  <p className="font-mono text-[11px] text-white">{service.pid || "—"}</p>
                </div>
                <div className="space-y-2">
                  <div>
                    <p className="text-zinc-500">Port</p>
                    <p className="font-mono text-[11px] text-white">{service.port || "—"}</p>
                  </div>
                  <div>
                    <p className="text-zinc-500">RAM</p>
                    <p className="font-mono text-[11px] text-white">
                      {isRunning ? `${service.memory_mb.toFixed(0)} MB` : "—"}
                    </p>
                  </div>
                </div>
                <div className="space-y-2">
                  <div>
                    <p className="text-zinc-500">Uptime</p>
                    <p className="font-mono text-[11px] text-white">
                      {formatUptime(service.uptime_seconds)}
                    </p>
                  </div>
                  <div>
                    <p className="text-zinc-500">CPU</p>
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
                    Start
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
                    Stop
                  </Button>
                  <Button
                    onClick={() => executeAction(service.service_type, "restart")}
                    disabled={actionInProgress === `${actionKey}-restart` || loading}
                    variant="secondary"
                    size="sm"
                    className="flex-1 h-8 border border-yellow-500/30 bg-yellow-500/10 px-2 text-xs text-yellow-200 hover:bg-yellow-500/20"
                  >
                    <RotateCw className="mr-1 h-3 w-3" />
                    Restart
                  </Button>
                </div>
              ) : (
                <div className="rounded-lg bg-blue-500/10 p-2 border border-blue-500/30">
                  <p className="text-[11px] text-blue-300 text-center">
                    Kontrolowane przez konfigurację
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Storage */}
      <div className="glass-panel rounded-2xl box-subtle p-6">
        <h2 className="mb-4 heading-h2">Koszty dysku</h2>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-zinc-200">
            {storageSnapshot?.disk ? (
              <span>
                Użycie:{" "}
                <span className="font-semibold text-white">
                  {formatBytes(storageSnapshot.disk.used_bytes)} /{" "}
                  {formatBytes(storageSnapshot.disk.total_bytes)}
                </span>{" "}
                (wolne: {formatBytes(storageSnapshot.disk.free_bytes)})
              </span>
            ) : (
              <span>Brak danych o dysku.</span>
            )}
          </div>
          <Button
            size="xs"
            variant="outline"
            className="rounded-full"
            onClick={fetchStorageSnapshot}
            disabled={storageLoading}
          >
            {storageLoading ? "Odświeżam..." : "Odśwież"}
          </Button>
        </div>
        {storageSnapshot?.refreshed_at ? (
          <p className="mt-2 text-xs text-zinc-500">
            Ostatnie sprawdzenie: {formatStorageTimestamp(storageSnapshot.refreshed_at)}
          </p>
        ) : null}
        {storageError ? (
          <p className="mt-3 text-xs text-rose-300">{storageError}</p>
        ) : (
          <div className="mt-4 grid gap-2 md:grid-cols-3">
            {(storageSnapshot?.items ?? [])
              .slice()
              .sort((a, b) => b.size_bytes - a.size_bytes)
              .map((item) => (
                <div
                  key={item.path}
                  className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-xs"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-white">{item.name}</p>
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
        <h2 className="mb-4 heading-h2">Historia akcji</h2>
        <div className="space-y-2">
          {history.length === 0 ? (
            <p className="text-sm text-zinc-500">Brak historii</p>
          ) : (
            history.map((entry, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-lg border border-white/5 bg-black/20 p-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      entry.success ? "bg-emerald-400" : "bg-red-400"
                    }`}
                  />
                  <div>
                    <p className="text-sm font-medium text-white">
                      {entry.service} → {entry.action}
                    </p>
                    <p className="text-xs text-zinc-500">{entry.message}</p>
                  </div>
                </div>
                <p className="text-xs text-zinc-600">
                  {new Date(entry.timestamp).toLocaleTimeString("pl-PL")}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
