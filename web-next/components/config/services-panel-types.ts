"use client";

export interface ServiceInfo {
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
  runtime_version?: string | null;
  actionable: boolean;
}

export interface ServiceEvent {
  type: string;
  data: Partial<ServiceInfo> & { status: string };
}

export interface ActionHistory {
  timestamp: string;
  service: string;
  action: string;
  success: boolean;
  message: string;
}

export interface StorageSnapshot {
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
