import type { ApplyResults } from "@/types/workflow-control";

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
