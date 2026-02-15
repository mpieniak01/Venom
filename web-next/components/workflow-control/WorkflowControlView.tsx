"use client";

import { useState, useCallback } from "react";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { WorkflowHeader } from "./WorkflowHeader";
import { PropertyPanel } from "./PropertyPanel";
import { WorkflowConsole } from "./WorkflowConsole";
import { ApplyResultsModal } from "./ApplyResultsModal";
import { useWorkflowState } from "@/hooks/useWorkflowState";
import { useTranslation } from "@/lib/i18n";
import { shouldShowApplyResultsModal, generatePlanRequest } from "@/lib/workflow-control-ui-helpers";
import type { ApplyResults } from "@/types/workflow-control";
import type { Node } from "@xyflow/react";

export function WorkflowControlView() {
  const t = useTranslation();
  const {
    systemState,
    draftState,
    hasChanges,
    isLoading,
    error,
    refresh,
    updateNode,
    reset,
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
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  // When clicking Plan Changes
  const handlePlanRequest = useCallback(async () => {
    if (!systemState || !draftState) return;

    // Generate diff
    const planReq = generatePlanRequest(systemState, draftState);
    if (planReq.changes.length === 0) return;

    const planResult = await planChanges(planReq);
    if (planResult?.valid) {
      // If valid, apply immediately for this MVP flow (or show confirmation modal first)
      // For UX simplicity as per "Draft Mode" -> "Apply", we chain them if valid.
      // But usually we show a Plan Preview. Let's assume direct apply for now as per previous logic.
      const applyResult = await applyChanges(planResult.execution_ticket);
      setApplyResults(applyResult);
      setShowResultsModal(true);
      refresh();
    }
  }, [systemState, draftState, planChanges, applyChanges, refresh]);

  return (
    <div className="flex flex-col bg-background">
      <WorkflowHeader
        hasChanges={hasChanges}
        onPlanRequest={handlePlanRequest}
        onReset={reset}
        isLoading={isLoading}
      />

      <div className="flex h-[780px] overflow-hidden border-b border-white/5">
        {/* Center: Workflow Canvas */}
        <main className="flex-1 flex flex-col relative">
          <div className="flex-1 relative">
            <WorkflowCanvas
              systemState={draftState}
              onNodeClick={setSelectedNode}
              readOnly={isLoading}
            />
          </div>
        </main>

        {/* Right Panel: Property Inspector & Console */}
        <aside className="w-80 border-l bg-background/50 flex flex-col p-2 gap-2">
          <div className="flex-1 overflow-y-auto">
            <PropertyPanel
              selectedNode={selectedNode}
              onUpdateNode={updateNode}
            />
          </div>
          <WorkflowConsole
            hasChanges={hasChanges}
            onPlanRequest={handlePlanRequest}
            onReset={reset}
            status={systemState?.workflow_status || "unknown"}
            onPause={pauseWorkflow}
            onResume={resumeWorkflow}
            onCancel={cancelWorkflow}
            onRetry={retryWorkflow}
            onDryRun={dryRun}
            isLoading={isLoading}
          />
        </aside>
      </div>



      {/* Apply Results Modal */}
      {
        applyResults && shouldShowApplyResultsModal(showResultsModal, applyResults) && (
          <ApplyResultsModal
            results={applyResults}
            onClose={() => setShowResultsModal(false)}
          />
        )
      }

      {/* Error Display */}
      {
        error && (
          <div className="fixed bottom-20 right-4 bg-destructive text-destructive-foreground p-4 rounded-lg shadow-lg z-50 max-w-sm">
            <p className="font-semibold">{t("workflowControl.common.errorTitle")}</p>
            <p className="text-sm">{error}</p>
          </div>
        )
      }
    </div >
  );
}
