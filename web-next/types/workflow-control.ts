export interface SystemState {
  kernel?: string;
  decision_strategy?: string;
  intent_mode?: string;
  runtime?: {
    services?: string[];
  };
  provider?: {
    active?: string;
  };
  embedding_model?: string;
  workflow_status?: string;
}

export type WorkflowStatus = "idle" | "running" | "paused" | "completed" | "failed" | "cancelled";

export interface AppliedChange {
  resource_type: string;
  resource_id: string;
  message: string;
}

export interface ApplyResults {
  apply_mode: "hot_swap" | "restart_required" | "rejected";
  applied_changes?: AppliedChange[];
  pending_restart?: string[];
  failed_changes?: string[];
  rollback_available?: boolean;
  message?: string;
}

export interface ConfigurationChange {
  resource_type: string;
  resource_id: string;
  action: string;
  current_value?: unknown;
  new_value: unknown;
}

export interface PlanRequest {
  changes: ConfigurationChange[];
}

export interface WorkflowControlSourceCatalog {
  local: string[];
  cloud: string[];
}

export interface WorkflowControlOptions {
  provider_sources: string[];
  embedding_sources: string[];
  providers: WorkflowControlSourceCatalog;
  embeddings: WorkflowControlSourceCatalog;
  active: {
    provider_source: "local" | "cloud";
    embedding_source: "local" | "cloud";
  };
}

export interface PlanResponse {
  execution_ticket: string;
  valid: boolean;
  compatibility_report?: unknown;
  planned_changes?: unknown[];
  hot_swap_changes?: unknown[];
  restart_required_services?: string[];
}

export interface WorkflowOperationRequest {
  workflow_id: string;
  operation: string;
  metadata?: Record<string, unknown>;
}
