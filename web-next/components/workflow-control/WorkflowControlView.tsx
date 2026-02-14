"use client";

import { useState, useCallback } from "react";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { ControlPanels } from "./ControlPanels";
import { OperationControls } from "./OperationControls";
import { ApplyResultsModal } from "./ApplyResultsModal";
import { useWorkflowState } from "@/hooks/useWorkflowState";
import { useTranslation } from "@/lib/i18n";
import { shouldShowApplyResultsModal } from "@/lib/workflow-control-ui-helpers";
import type { ApplyResults, PlanRequest } from "@/types/workflow-control";

export function WorkflowControlView() {
  const t = useTranslation();
  const {
    systemState,
    isLoading,
    error,
    refresh,
    planChanges,
    applyChanges,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    retryWorkflow,
    dryRun,
  } = useWorkflowState();

  const [showResultsModal, setShowResultsModal] = useState(false);
  const [applyResults, setApplyResults] = useState<ApplyResults | null>(null);

  const handleApply = useCallback(
    async (changes: PlanRequest) => {
      const planResult = await planChanges(changes);
      if (planResult?.valid) {
        const applyResult = await applyChanges(planResult.execution_ticket);
        setApplyResults(applyResult);
        setShowResultsModal(true);
        refresh();
      }
    },
    [planChanges, applyChanges, refresh]
  );

  return (
    <div className="flex flex-col h-screen bg-background">
      <header className="border-b p-4">
        <h1 className="text-2xl font-bold">{t("workflowControl.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("workflowControl.description")}
        </p>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel: Control Panels */}
        <aside className="w-96 border-r overflow-y-auto p-4">
          <ControlPanels
            systemState={systemState}
            onApply={handleApply}
            isLoading={isLoading}
          />
        </aside>

        {/* Center: Workflow Visualization */}
        <main className="flex-1 flex flex-col">
          <div className="flex-1 relative">
            <WorkflowCanvas systemState={systemState} />
          </div>

          {/* Bottom: Operation Controls */}
          <footer className="border-t p-4">
            <OperationControls
              workflowStatus={systemState?.workflow_status}
              onPause={pauseWorkflow}
              onResume={resumeWorkflow}
              onCancel={cancelWorkflow}
              onRetry={retryWorkflow}
              onDryRun={dryRun}
              isLoading={isLoading}
            />
          </footer>
        </main>
      </div>

      {/* Apply Results Modal */}
      {applyResults && shouldShowApplyResultsModal(showResultsModal, applyResults) && (
        <ApplyResultsModal
          results={applyResults}
          onClose={() => setShowResultsModal(false)}
        />
      )}

      {/* Error Display */}
      {error && (
        <div className="fixed bottom-4 right-4 bg-destructive text-destructive-foreground p-4 rounded-lg shadow-lg">
          <p className="font-semibold">{t("workflowControl.common.errorTitle")}</p>
          <p className="text-sm">{error}</p>
        </div>
      )}
    </div>
  );
}
