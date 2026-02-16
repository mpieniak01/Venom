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

export type SystemState = Partial<Omit<ApiSystemState, "runtime" | "provider">> & {
  runtime?: RuntimeState;
  provider?: ProviderState;
};

export type WorkflowStatus = ApiSchemas["WorkflowStatus"];

export type AppliedChange = ApiSchemas["AppliedChange"];

export type ApplyResults = ApiSchemas["ControlApplyResponse"];

export type ConfigurationChange = ApiSchemas["ResourceChange"];

export type PlanRequest = ApiSchemas["ControlPlanRequest"];

export type WorkflowControlSourceCatalog = ApiSchemas["ControlOptionsCatalog"];

export type WorkflowControlOptions = ApiSchemas["ControlOptionsResponse"] & {
  active: {
    provider_source: SourceType;
    embedding_source: SourceType;
  };
};

export type PlanResponse = ApiSchemas["ControlPlanResponse"];

export type WorkflowOperationRequest = ApiSchemas["WorkflowOperationRequest"];
