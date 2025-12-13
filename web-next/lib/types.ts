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
  paused?: boolean;
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

export interface HistoryRequest {
  request_id: string;
  prompt: string;
  status: TaskStatus;
  created_at: string;
  finished_at?: string | null;
  duration_seconds?: number | null;
}

export interface ServiceStatus {
  name: string;
  status: "healthy" | "degraded" | "down" | string;
  detail?: string;
}

export interface TokenMetrics {
  total_tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_tokens?: number;
}

export interface GitStatus {
  branch?: string;
  changes?: string;
  dirty?: boolean;
  status?: string;
}

export interface ModelInfo {
  name: string;
  size_gb?: number;
  installed?: boolean;
  active?: boolean;
  source?: string;
}

export interface ModelsResponse {
  success?: boolean;
  models: ModelInfo[];
  count: number;
}

export interface CostMode {
  enabled: boolean;
  provider: string;
}

export interface AutonomyLevel {
  current_level: number;
  current_level_name: string;
  color: string;
  color_name: string;
  description: string;
  permissions: Record<string, unknown>;
  risk_level: string;
}

export interface KnowledgeGraph {
  status?: string;
  mock?: boolean;
  elements: {
    nodes: Array<{ data: Record<string, unknown> }>;
    edges: Array<{ data: Record<string, unknown> }>;
  };
  stats?: {
    nodes: number;
    edges: number;
  };
}
