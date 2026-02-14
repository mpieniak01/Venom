// Workflow Control Plane Types

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
  current_value?: string;
  new_value: string;
}

export interface PlanRequest {
  changes: ConfigurationChange[];
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
