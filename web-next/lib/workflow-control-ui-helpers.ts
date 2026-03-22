import type {
  ApplyResults,
  ConfigurationChange,
  OperatorExecutionStep,
  OperatorRuntimeService,
  PlanRequest,
  SystemState,
  WorkflowControlOptions,
} from "@/types/workflow-control";
import type { ControlDomainId, WorkflowControlSelection } from "@/lib/workflow-control-screen";
import {
  buildPropertyPanelOptions,
  getCompatibleEmbeddings,
  getCompatibleIntentModes,
  getCompatibleKernels,
  getCompatibleProviders,
} from "@/lib/workflow-control-options";

type DraftCompatibilityIssue = {
  code:
    | "kernel_runtime_mismatch"
    | "intent_requires_embedding"
    | "provider_embedding_mismatch";
  domains: ControlDomainId[];
  message: string;
};

export type DraftCompatibilityReport = {
  issues: DraftCompatibilityIssue[];
  issuesByDomain: Partial<Record<ControlDomainId, DraftCompatibilityIssue[]>>;
};

export type WorkflowDraftVisualState = {
  changedDomainCount: number;
  hasConflicts: boolean;
  isPlanReady: boolean;
};

export type WorkflowSelectionSummary = {
  kind: WorkflowControlSelection["kind"];
  label: string;
  value: string;
  id: string;
};

function findRuntimeServiceById(
  services: OperatorRuntimeService[] | undefined,
  serviceId: string,
): OperatorRuntimeService | null {
  return (services ?? []).find((service) => service.id === serviceId) ?? null;
}

function findExecutionStepById(
  steps: OperatorExecutionStep[] | undefined,
  stepId: string,
): OperatorExecutionStep | null {
  return (steps ?? []).find((step) => step.id === stepId) ?? null;
}

export function buildWorkflowSelectionSummary(
  selection: WorkflowControlSelection | null,
  systemState: SystemState | null,
): WorkflowSelectionSummary | null {
  if (!selection) return null;

  if (selection.kind === "control-domain") {
    return {
      kind: "control-domain",
      label: "control-domain",
      value: selection.id,
      id: selection.id,
    };
  }

  if (selection.kind === "runtime-service") {
    const service = findRuntimeServiceById(systemState?.runtime_services, selection.serviceId);
    return {
      kind: "runtime-service",
      label: "runtime-service",
      value: service?.name ?? selection.serviceId,
      id: selection.serviceId,
    };
  }

  const step = findExecutionStepById(systemState?.execution_steps, selection.stepId);
  const stepSummaryLabel =
    step?.component && step?.action
      ? `${step.component}:${step.action}`
      : selection.stepId;
  return {
    kind: "execution-step",
    label: "execution-step",
    value: stepSummaryLabel,
    id: selection.stepId,
  };
}

export function shouldShowApplyResultsModal(
  showResultsModal: boolean,
  applyResults: ApplyResults | null
): boolean {
  return showResultsModal && Boolean(applyResults);
}

export function getWorkflowStatusMeta(workflowStatus: string = "idle") {
  const colorClasses: Record<string, string> = {
    running: "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-100",
    paused: "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-100",
    failed: "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-100",
  };
  const colorClass =
    colorClasses[workflowStatus] ?? "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100";

  return {
    statusKey: workflowStatus,
    canPause: workflowStatus === "running",
    canResume: workflowStatus === "paused",
    canCancel: ["running", "paused"].includes(workflowStatus),
    canRetry: ["failed", "cancelled"].includes(workflowStatus),
    colorClass,
  };
}

function findConfigValue(state: SystemState, key: string): string | null {
  const field = (state.config_fields ?? []).find((entry) => entry.key === key);
  const value = field?.value ?? field?.effective_value;
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function resolveProviderSource(
  draftState: SystemState,
  systemState: SystemState | null,
): "local" | "cloud" {
  const providerSource =
    draftState.provider?.sourceType ??
    draftState.provider_source ??
    systemState?.provider?.sourceType ??
    systemState?.provider_source ??
    "local";
  return providerSource === "cloud" ? "cloud" : "local";
}

function resolveEmbeddingSource(
  draftState: SystemState,
  systemState: SystemState | null,
): "local" | "cloud" {
  const embeddingSource =
    draftState.embedding_source ?? systemState?.embedding_source ?? "local";
  return embeddingSource === "cloud" ? "cloud" : "local";
}

function maybeBuildKernelRuntimeIssue({
  options,
  kernel,
  runtime,
}: {
  options: ReturnType<typeof buildPropertyPanelOptions>;
  kernel: string | null;
  runtime: string | null;
}): DraftCompatibilityIssue | null {
  if (!kernel || !runtime) {
    return null;
  }
  const compatibleKernels = getCompatibleKernels(options, runtime);
  if (compatibleKernels.includes(kernel)) {
    return null;
  }
  return {
    code: "kernel_runtime_mismatch",
    domains: ["kernel"],
    message: `Kernel '${kernel}' is not compatible with runtime '${runtime}'.`,
  };
}

function maybeBuildIntentIssue({
  options,
  intentMode,
  hasEmbedding,
}: {
  options: ReturnType<typeof buildPropertyPanelOptions>;
  intentMode: string | null;
  hasEmbedding: boolean;
}): DraftCompatibilityIssue | null {
  if (!intentMode) {
    return null;
  }
  const compatibleIntentModes = getCompatibleIntentModes(options, hasEmbedding);
  if (compatibleIntentModes.includes(intentMode)) {
    return null;
  }
  return {
    code: "intent_requires_embedding",
    domains: ["intent", "embedding"],
    message: `Intent mode '${intentMode}' requires an embedding model.`,
  };
}

function maybeBuildProviderEmbeddingIssue({
  options,
  provider,
  embedding,
  providerSource,
  embeddingSource,
}: {
  options: ReturnType<typeof buildPropertyPanelOptions>;
  provider: string | null;
  embedding: string | null;
  providerSource: "local" | "cloud";
  embeddingSource: "local" | "cloud";
}): DraftCompatibilityIssue | null {
  if (!provider || !embedding) {
    return null;
  }
  const compatibleProviders = getCompatibleProviders(
    options,
    providerSource,
    embedding,
  );
  const compatibleEmbeddings = getCompatibleEmbeddings(
    options,
    embeddingSource,
    provider,
  );
  if (
    compatibleProviders.includes(provider) &&
    compatibleEmbeddings.includes(embedding)
  ) {
    return null;
  }
  return {
    code: "provider_embedding_mismatch",
    domains: ["provider", "embedding"],
    message: `Provider '${provider}' is not compatible with embedding '${embedding}'.`,
  };
}

function groupIssuesByDomain(
  issues: DraftCompatibilityIssue[],
): DraftCompatibilityReport["issuesByDomain"] {
  const issuesByDomain: DraftCompatibilityReport["issuesByDomain"] = {};
  issues.forEach((issue) => {
    issue.domains.forEach((domain) => {
      issuesByDomain[domain] = [...(issuesByDomain[domain] ?? []), issue];
    });
  });
  return issuesByDomain;
}

export function buildDraftCompatibilityReport(
  controlOptions: WorkflowControlOptions | null,
  systemState: SystemState | null,
  draftState: SystemState | null,
): DraftCompatibilityReport {
  if (!draftState) {
    return { issues: [], issuesByDomain: {} };
  }

  const options = buildPropertyPanelOptions(controlOptions, systemState, draftState);
  const issues: DraftCompatibilityIssue[] = [];
  const kernel = draftState.kernel ?? null;
  const runtime = findConfigValue(draftState, "WORKFLOW_RUNTIME");
  const intentMode = draftState.intent_mode ?? null;
  const provider = draftState.provider?.active ?? null;
  const providerSource = resolveProviderSource(draftState, systemState);
  const embedding = draftState.embedding_model ?? null;
  const embeddingSource = resolveEmbeddingSource(draftState, systemState);

  const kernelIssue = maybeBuildKernelRuntimeIssue({
    options,
    kernel,
    runtime,
  });
  if (kernelIssue) {
    issues.push(kernelIssue);
  }

  const intentIssue = maybeBuildIntentIssue({
    options,
    intentMode,
    hasEmbedding: Boolean(embedding),
  });
  if (intentIssue) {
    issues.push(intentIssue);
  }

  const providerEmbeddingIssue = maybeBuildProviderEmbeddingIssue({
    options,
    provider,
    embedding,
    providerSource,
    embeddingSource,
  });
  if (providerEmbeddingIssue) {
    issues.push(providerEmbeddingIssue);
  }

  return { issues, issuesByDomain: groupIssuesByDomain(issues) };
}

export function buildWorkflowDraftVisualState(
  changedDomainCount: number,
  compatibilityIssueCount: number,
  hasPendingPlan: boolean,
): WorkflowDraftVisualState {
  return {
    changedDomainCount,
    hasConflicts: compatibilityIssueCount > 0,
    isPlanReady: hasPendingPlan && compatibilityIssueCount === 0,
  };
}

// Compare two SystemState objects and generate ConfigurationChange list
export function generatePlanRequest(original: SystemState, draft: SystemState): PlanRequest {
  const changes: ConfigurationChange[] = [];
  const providerActive = (provider: SystemState["provider"]): string | undefined =>
    provider?.active;

  // Helper to compare and push change
  const compareAndPush = (
    type: ConfigurationChange["resource_type"],
    id: string,
    originalVal: unknown,
    draftVal: unknown
  ) => {
    if (JSON.stringify(originalVal) !== JSON.stringify(draftVal)) {
      changes.push({
        resource_type: type,
        resource_id: id,
        action: "update",
        current_value: originalVal,
        new_value: draftVal
      });
    }
  };

  compareAndPush("decision_strategy", "decision", original.decision_strategy, draft.decision_strategy);
  compareAndPush("intent_mode", "intent", original.intent_mode, draft.intent_mode);
  compareAndPush("kernel", "kernel", original.kernel, draft.kernel);

  // Exclude runtime — it contains telemetry fields (uptime_seconds, status) that
  // change on every poll and must not be treated as user-driven config changes.
  compareAndPush(
    "provider",
    "provider",
    providerActive(original.provider),
    providerActive(draft.provider)
  );
  compareAndPush("embedding_model", "embedding", original.embedding_model, draft.embedding_model);

    const originalConfigFields = original.config_fields ?? [];
    const draftConfigFields = draft.config_fields ?? [];
    const originalByKey = new Map(originalConfigFields.map((field) => [field.key, field]));
    const draftByKey = new Map(draftConfigFields.map((field) => [field.key, field]));
    const allConfigKeys = new Set([...originalByKey.keys(), ...draftByKey.keys()]);

    for (const key of allConfigKeys) {
      const originalField = originalByKey.get(key);
      const draftField = draftByKey.get(key);
      const originalValue = originalField?.value;
      const draftValue = draftField?.value;
      const entityId = draftField?.entity_id ?? originalField?.entity_id;
      const field = draftField?.field ?? originalField?.field;

      if (JSON.stringify(originalValue) !== JSON.stringify(draftValue)) {
        changes.push({
          resource_type: "config",
          resource_id: key,
          entity_id: entityId,
          field,
          action: "update",
          current_value: originalValue ?? null,
          new_value: draftValue ?? null,
          metadata: {
            entity_id: entityId,
            field,
          },
        });
      }
    }

  return { changes, dry_run: false, force: false };
}
