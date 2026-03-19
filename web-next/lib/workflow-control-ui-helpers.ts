import type {
  ApplyResults,
  ConfigurationChange,
  PlanRequest,
  SystemState,
  WorkflowControlOptions,
} from "@/types/workflow-control";
import type { ControlDomainId } from "@/lib/workflow-control-screen";
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
  const providerSource =
    draftState.provider?.sourceType ??
    draftState.provider_source ??
    systemState?.provider?.sourceType ??
    systemState?.provider_source ??
    "local";
  const embedding = draftState.embedding_model ?? null;
  const embeddingSource =
    draftState.embedding_source ?? systemState?.embedding_source ?? "local";

  if (kernel && runtime) {
    const compatibleKernels = getCompatibleKernels(options, runtime);
    if (!compatibleKernels.includes(kernel)) {
      issues.push({
        code: "kernel_runtime_mismatch",
        domains: ["kernel"],
        message: `Kernel '${kernel}' is not compatible with runtime '${runtime}'.`,
      });
    }
  }

  if (intentMode) {
    const compatibleIntentModes = getCompatibleIntentModes(options, Boolean(embedding));
    if (!compatibleIntentModes.includes(intentMode)) {
      issues.push({
        code: "intent_requires_embedding",
        domains: ["intent", "embedding"],
        message: `Intent mode '${intentMode}' requires an embedding model.`,
      });
    }
  }

  if (provider && embedding) {
    const compatibleProviders = getCompatibleProviders(
      options,
      providerSource === "cloud" ? "cloud" : "local",
      embedding,
    );
    const compatibleEmbeddings = getCompatibleEmbeddings(
      options,
      embeddingSource === "cloud" ? "cloud" : "local",
      provider,
    );
    if (
      !compatibleProviders.includes(provider) ||
      !compatibleEmbeddings.includes(embedding)
    ) {
      issues.push({
        code: "provider_embedding_mismatch",
        domains: ["provider", "embedding"],
        message: `Provider '${provider}' is not compatible with embedding '${embedding}'.`,
      });
    }
  }

  const issuesByDomain: DraftCompatibilityReport["issuesByDomain"] = {};
  issues.forEach((issue) => {
    issue.domains.forEach((domain) => {
      issuesByDomain[domain] = [...(issuesByDomain[domain] ?? []), issue];
    });
  });

  return { issues, issuesByDomain };
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
