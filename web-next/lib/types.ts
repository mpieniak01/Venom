export type TaskStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "LOST";

export interface Task {
  task_id: string;
  content: string;
  status: TaskStatus;
  created_at?: string;
  updated_at?: string;
}

export interface Metrics {
  tasks?: {
    created?: number;
    success_rate?: number;
  };
  uptime_seconds?: number;
  network?: {
    total_bytes?: number;
  };
}

export interface QueueStatus {
  active: number;
  pending: number;
  limit?: number;
}

export interface IntegrationStatus {
  name: string;
  status: "online" | "degraded" | "offline";
  details?: string;
}

export interface GraphSummary {
  nodes: number;
  edges: number;
  lastUpdated?: string;
}
