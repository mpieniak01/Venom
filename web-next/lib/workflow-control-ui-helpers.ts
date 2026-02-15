
import type { ApplyResults, PlanRequest, SystemState, ConfigurationChange } from "@/types/workflow-control";

export function shouldShowApplyResultsModal(
  showResultsModal: boolean,
  applyResults: ApplyResults | null
): boolean {
  return showResultsModal && Boolean(applyResults);
}

export function getWorkflowStatusMeta(workflowStatus?: string) {
  const normalized = workflowStatus || "idle";
  return {
    statusKey: normalized,
    canPause: normalized === "running",
    canResume: normalized === "paused",
    canCancel: ["running", "paused"].includes(normalized),
    canRetry: ["failed", "cancelled"].includes(normalized),
    colorClass:
      normalized === "running"
        ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-100"
        : normalized === "paused"
          ? "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-100"
          : normalized === "failed"
            ? "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-100"
            : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100",
  };
}

// Compare two SystemState objects and generate ConfigurationChange list
export function generatePlanRequest(original: SystemState, draft: SystemState): PlanRequest {
  const changes: ConfigurationChange[] = [];

  // Helper to compare and push change
  const compareAndPush = (
    type: string,
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

  if (original && draft) {
    compareAndPush("decision_strategy", "decision", original.decision_strategy, draft.decision_strategy);
    compareAndPush("intent_mode", "decision", original.intent_mode, draft.intent_mode);
    compareAndPush("kernel", "kernel", original.kernel, draft.kernel);

    // Deep compare for objects (simplified json stringify for MVP)
    compareAndPush("runtime", "runtime", original.runtime, draft.runtime);
    compareAndPush("provider", "provider", original.provider, draft.provider);
    compareAndPush("embedding_model", "embedding", original.embedding_model, draft.embedding_model);
  }

  return { changes };
}
