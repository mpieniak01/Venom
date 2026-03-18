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
import { buildPropertyPanelOptions } from "@/lib/workflow-control-options";
import type { ApplyResults, PlanResponse } from "@/types/workflow-control";
import type { Node } from "@xyflow/react";

export function WorkflowControlView() {
  const t = useTranslation();
  const {
    systemState,
    draftState,
    controlOptions,
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
  const [pendingPlanResult, setPendingPlanResult] = useState<PlanResponse | null>(null);
  const propertyPanelOptions = buildPropertyPanelOptions(
    controlOptions,
    systemState,
    draftState
  );

  const handleUpdateNode = useCallback(
    (nodeId: string, data: unknown) => {
      updateNode(nodeId, data);
      // Any edit to the draft invalidates the previously planned result.
      setPendingPlanResult(null);
      setSelectedNode((prev) => {
        if (prev?.id !== nodeId) return prev;
        return {
          ...prev,
          data: data as Node["data"],
        };
      });
    },
    [updateNode, setPendingPlanResult]
  );

  // Step 1: Plan — only computes diff and stores result for user review.
  const handlePlanRequest = useCallback(async () => {
    if (!systemState || !draftState) return;
    const planReq = generatePlanRequest(systemState, draftState);
    if (planReq.changes.length === 0) {
      // No changes for this draft; clear any previously pending plan.
      setPendingPlanResult(null);
      return;
    }

    const planResult = await planChanges(planReq);
    if (planResult?.valid) {
      // Store result; user must explicitly confirm to Apply.
      setPendingPlanResult(planResult);
    }
  }, [systemState, draftState, planChanges, setPendingPlanResult]);

  // Step 2: Apply — only called after explicit user confirmation.
  const handleApplyConfirmed = useCallback(async () => {
    if (!pendingPlanResult) return;
    const applyResult = await applyChanges(pendingPlanResult.execution_ticket);
    setApplyResults(applyResult);
    setShowResultsModal(true);
    setPendingPlanResult(null);
    refresh();
  }, [pendingPlanResult, applyChanges, refresh]);

  // Wrap reset so any pending plan is also cleared (reset reverts draft to server
  // state, making a previously computed plan obsolete immediately).
  const handleReset = useCallback(() => {
    reset();
    setPendingPlanResult(null);
  }, [reset]);

  return (
    <div className="flex flex-col bg-background">
      <WorkflowHeader
        hasChanges={hasChanges}
        onPlanRequest={handlePlanRequest}
        onReset={handleReset}
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
              onUpdateNode={handleUpdateNode}
              availableOptions={propertyPanelOptions}
              configFields={systemState?.config_fields}
            />
          </div>
          <WorkflowConsole
            hasChanges={hasChanges}
            onPlanRequest={handlePlanRequest}
            onReset={handleReset}
            status={systemState?.workflow_status ?? "unknown"}
            allowedOperations={systemState?.allowed_operations ?? []}
            activeRequestId={systemState?.active_request_id ?? null}
            llmRuntimeId={systemState?.llm_runtime_id ?? null}
            llmProvider={systemState?.llm_provider_name ?? null}
            llmModel={systemState?.llm_model ?? null}
            onPause={pauseWorkflow}
            onResume={resumeWorkflow}
            onCancel={cancelWorkflow}
            onRetry={retryWorkflow}
            onDryRun={dryRun}
            isLoading={isLoading}
          />
        </aside>
      </div>

      {/* Plan Confirmation Banner — shown after Plan, before Apply */}
      {pendingPlanResult && (
        <div className="fixed bottom-20 right-4 bg-slate-800 border border-blue-500/50 text-slate-100 p-4 rounded-lg shadow-lg z-50 max-w-sm">
          <p className="font-semibold text-sm mb-2">{t("workflowControl.actions.planReady")}</p>
          <p className="text-xs text-slate-400 mb-3">
            {t("workflowControl.actions.planReadyHint")}
          </p>
          <div className="flex gap-2">
            <button
              className="flex-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 rounded font-medium"
              onClick={handleApplyConfirmed}
              disabled={isLoading}
            >
              {t("workflowControl.actions.apply")}
            </button>
            <button
              className="flex-1 px-3 py-1.5 text-xs border border-white/20 hover:bg-white/10 rounded"
              onClick={() => setPendingPlanResult(null)}
            >
              {t("workflowControl.actions.discard")}
            </button>
          </div>
        </div>
      )}



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
