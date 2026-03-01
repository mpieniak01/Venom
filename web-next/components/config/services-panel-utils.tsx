"use client";

import {
  Activity,
  Brain,
  Cpu,
  GraduationCap,
  Layout,
  Network,
  Plug,
  Zap,
} from "lucide-react";
import type { ServiceInfo } from "./services-panel-types";

const runtimeToServiceStatus: Record<string, ServiceInfo["status"]> = {
  online: "running",
  offline: "stopped",
  degraded: "degraded",
  unknown: "unknown",
};

export function normalizeServiceStatus(
  status: string | undefined
): ServiceInfo["status"] {
  if (!status) return "unknown";
  const normalized = status.toLowerCase();
  if (normalized in runtimeToServiceStatus) return runtimeToServiceStatus[normalized];
  if (
    normalized === "running" ||
    normalized === "stopped" ||
    normalized === "error" ||
    normalized === "degraded"
  ) {
    return normalized;
  }
  return "unknown";
}

export function mergeServiceUpdate(
  service: ServiceInfo,
  update: Partial<ServiceInfo> & { status: string }
): ServiceInfo {
  return {
    ...service,
    ...update,
    status: normalizeServiceStatus(update.status),
  };
}

export function applyServiceEventUpdate(
  services: ServiceInfo[],
  update: Partial<ServiceInfo> & { status: string; name?: string }
): ServiceInfo[] {
  if (!update.name) return services;
  const normalizedName = update.name.toLowerCase();
  return services.map((service) =>
    service.name.toLowerCase() === normalizedName
      ? mergeServiceUpdate(service, update)
      : service
  );
}

export function getStatusColor(status: string) {
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
}

export function getStatusBadge(status: string) {
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
}

export function formatUptime(seconds: number | null) {
  if (seconds === null || seconds === undefined) return "—";
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

export function getServiceIcon(serviceType: string) {
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
    case "academy":
      return <GraduationCap className="h-5 w-5" />;
    case "intent_embedding_router":
      return <Network className="h-5 w-5" />;
    default:
      return <Activity className="h-5 w-5" />;
  }
}

export function getDisplayName(
  raw: string,
  t: (key: string) => string
): string {
  const key = raw.toLowerCase().replaceAll(/\s+/g, "_");
  const translated = t(`config.services.names.${key}`);
  if (translated && translated !== `config.services.names.${key}`) {
    return translated;
  }
  return raw
    .replaceAll(/[_-]+/g, " ")
    .replaceAll(/\b\w/g, (m) => m.toUpperCase());
}

export function formatBytes(value?: number) {
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
}

export function formatStorageTimestamp(value: string | undefined, language: string) {
  if (!value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  const locale = (() => {
    if (language === "pl") return "pl-PL";
    if (language === "de") return "de-DE";
    return "en-US";
  })();
  return new Date(parsed).toLocaleString(locale);
}
