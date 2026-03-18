
import type {
  ApplyResults,
  ConfigurationChange,
  PlanRequest,
  SystemState,
} from "@/types/workflow-control";

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

      if (JSON.stringify(originalValue) !== JSON.stringify(draftValue)) {
        changes.push({
          resource_type: "config",
          resource_id: key,
          action: "update",
          current_value: originalValue ?? null,
          new_value: draftValue ?? null,
          metadata: {
            entity_id: draftField?.entity_id ?? originalField?.entity_id,
            field: draftField?.field ?? originalField?.field,
          },
        });
      }
    }

  return { changes, dry_run: false, force: false };
}
