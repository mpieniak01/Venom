import type { components } from "@/lib/generated/api-types";

type ApiSchemas = components["schemas"];
type ApiSystemState = ApiSchemas["SystemState"];

type SourceType = "local" | "cloud";

type RuntimeService = string | { name?: string; id?: string; [key: string]: unknown };

type RuntimeState = ApiSystemState["runtime"] & {
  services?: RuntimeService[];
};

type ProviderState = {
  active?: string;
  sourceType?: SourceType | string;
  [key: string]: unknown;
};

export type OperatorGraphNode = {
  id: string;
  type: string;
  label?: string;
  data?: Record<string, unknown>;
  position?: { x?: number; y?: number };
};

export type OperatorGraphEdge = {
  id: string;
  source: string;
  target: string;
  animated?: boolean;
  label?: string;
};

export type OperatorConfigField = {
  entity_id: string;
  field: string;
  key: string;
  value?: unknown;
  effective_value?: unknown;
  source?: string;
  editable?: boolean;
  restart_required?: boolean;
  affected_services?: string[];
  options?: string[];
};

export type OperatorRuntimeService = {
  id: string;
  name: string;
  kind?: string;
  status?: string;
  pid?: number | null;
  port?: number | null;
  cpu_percent?: number;
  memory_mb?: number;
  uptime_seconds?: number | null;
  runtime_version?: string | null;
  actionable?: boolean;
  allowed_actions?: string[];
  dependencies?: string[];
};

export type OperatorExecutionStep = {
  id: string;
  component: string;
  action: string;
  status: string;
  timestamp?: string;
  details?: string | null;
};

export type SystemState = Partial<Omit<ApiSystemState, "runtime" | "provider">> & {
  runtime?: RuntimeState;
  provider?: ProviderState;
  config_fields?: OperatorConfigField[];
  runtime_services?: OperatorRuntimeService[];
  execution_steps?: OperatorExecutionStep[];
  graph?: {
    nodes?: OperatorGraphNode[];
    edges?: OperatorGraphEdge[];
  };
};

export type WorkflowStatus = ApiSchemas["WorkflowStatus"];

export type AppliedChange = ApiSchemas["AppliedChange"];

export type ApplyResults = ApiSchemas["ControlApplyResponse"];

export type ConfigurationChange = ApiSchemas["ResourceChange"];

export type PlanRequest = ApiSchemas["ControlPlanRequest"];

export type WorkflowControlSourceCatalog = ApiSchemas["ControlOptionsCatalog"];

export type WorkflowControlOptions = ApiSchemas["ControlOptionsResponse"] & {
  decision_strategies?: string[];
  intent_modes?: string[];
  kernels?: string[];
  active: {
    provider_source: SourceType;
    embedding_source: SourceType;
  };
};

export type PlanResponse = ApiSchemas["ControlPlanResponse"];

export type WorkflowOperationRequest = ApiSchemas["WorkflowOperationRequest"];

export type WorkflowControlStatePayload = {
  system_state?: SystemState;
  workflow_target?: {
    request_id?: string | null;
    task_status?: string | null;
    workflow_status?: string;
    runtime_id?: string | null;
    provider?: string | null;
    model?: string | null;
    allowed_operations?: string[];
  };
  config_fields?: OperatorConfigField[];
  runtime_services?: OperatorRuntimeService[];
  execution_steps?: OperatorExecutionStep[];
  graph?: {
    nodes?: OperatorGraphNode[];
    edges?: OperatorGraphEdge[];
  };
};
