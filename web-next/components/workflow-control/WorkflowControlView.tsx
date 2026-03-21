"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { buildWorkflowGraph } from "@/lib/workflow-canvas-helpers";
import {
  buildControlDomainCards,
  buildExecutionStepGroupState,
  type ControlDomainId,
  type WorkflowControlSelection,
} from "@/lib/workflow-control-screen";
import {
  buildWorkflowSelectionSummary,
  buildDraftCompatibilityReport,
  buildWorkflowDraftVisualState,
  generatePlanRequest,
  shouldShowApplyResultsModal,
} from "@/lib/workflow-control-ui-helpers";
import { buildPropertyPanelOptions } from "@/lib/workflow-control-options";
import type { ApplyResults, PlanResponse } from "@/types/workflow-control";
import { useWorkflowState } from "@/hooks/useWorkflowState";

import { ApplyResultsModal } from "./ApplyResultsModal";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { WorkflowExecutionTimeline } from "./WorkflowExecutionTimeline";
import { WorkflowHeader } from "./WorkflowHeader";
import { WorkflowInspectorPanel } from "./WorkflowInspectorPanel";
import { WorkflowTargetPanel } from "./WorkflowTargetPanel";

function sectionTitleForDomain(
  id: ControlDomainId,
  t: (path: string) => string,
): string {
  if (id === "config") {
    return t("workflowControl.labels.systemConfiguration");
  }
  if (id === "decision") return t("workflowControl.sections.decision");
  if (id === "intent") return t("workflowControl.sections.intent");
  if (id === "kernel") return t("workflowControl.sections.kernel");
  if (id === "provider") return t("workflowControl.sections.provider");
  return t("workflowControl.sections.embedding");
}

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
    runtimeServiceAction,
    executionStepAction,
  } = useWorkflowState();

  const [showResultsModal, setShowResultsModal] = useState(false);
  const [applyResults, setApplyResults] = useState<ApplyResults | null>(null);
  const [pendingPlanResult, setPendingPlanResult] = useState<PlanResponse | null>(null);
  const [selection, setSelection] = useState<WorkflowControlSelection | null>(null);
  const [expandedExecutionGroups, setExpandedExecutionGroups] = useState<Set<string>>(new Set());
  const [isTimelineOpen, setIsTimelineOpen] = useState(false);
  const hasTimelineSelection =
    selection?.kind === "execution-step" || selection?.kind === "runtime-service";
  const isTimelineExpanded = isTimelineOpen || hasTimelineSelection;

  const propertyPanelOptions = buildPropertyPanelOptions(
    controlOptions,
    systemState,
    draftState
  );
  const compatibilityReport = useMemo(
    () => buildDraftCompatibilityReport(controlOptions, systemState, draftState),
    [controlOptions, systemState, draftState],
  );
  const controlDomainCards = useMemo(
    () => buildControlDomainCards(systemState, draftState),
    [systemState, draftState]
  );
  const executionStepGroupState = useMemo(
    () => buildExecutionStepGroupState(systemState?.execution_steps),
    [systemState?.execution_steps],
  );
  const graphPreview = useMemo(
    () => buildWorkflowGraph(systemState, { expandedGroupKeys: expandedExecutionGroups }),
    [systemState, expandedExecutionGroups],
  );
  const showGraphRelationsWarning =
    ((systemState?.execution_steps?.length ?? 0) > 0 ||
      (systemState?.runtime_services?.length ?? 0) > 0) &&
    graphPreview.edges.length === 0;
  const draftVisualState = useMemo(() => {
    const changedDomainCount = controlDomainCards.filter((card) => card.changed).length;
    return buildWorkflowDraftVisualState(
      changedDomainCount,
      compatibilityReport.issues.length,
      Boolean(pendingPlanResult),
    );
  }, [controlDomainCards, compatibilityReport.issues.length, pendingPlanResult]);
  const selectionSummary = useMemo(
    () => buildWorkflowSelectionSummary(selection, systemState),
    [selection, systemState],
  );

  const handleUpdateNode = useCallback(
    (nodeId: string, data: unknown) => {
      updateNode(nodeId, data);
      setPendingPlanResult(null);
    },
    [updateNode]
  );

  const handlePlanRequest = useCallback(async () => {
    if (!systemState || !draftState) return;
    const planReq = generatePlanRequest(systemState, draftState);
    if (planReq.changes.length === 0) {
      setPendingPlanResult(null);
      return;
    }

    const planResult = await planChanges(planReq);
    if (planResult?.valid) {
      setPendingPlanResult(planResult);
    }
  }, [systemState, draftState, planChanges]);

  const handleApplyConfirmed = useCallback(async () => {
    if (!pendingPlanResult) return;
    const applyResult = await applyChanges(pendingPlanResult.execution_ticket);
    setApplyResults(applyResult);
    setShowResultsModal(true);
    setPendingPlanResult(null);
    refresh();
  }, [pendingPlanResult, applyChanges, refresh]);

  const handleReset = useCallback(() => {
    reset();
    setPendingPlanResult(null);
    setSelection(null);
    setExpandedExecutionGroups(new Set());
    setIsTimelineOpen(false);
  }, [reset]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isEditableTarget =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (isEditableTarget) {
        return;
      }

      if (event.key === "Escape") {
        if (selection || isTimelineOpen) {
          event.preventDefault();
          setSelection(null);
          setIsTimelineOpen(false);
        }
        return;
      }

      if (event.altKey && event.key.toLowerCase() === "t" && !hasTimelineSelection) {
        event.preventDefault();
        setIsTimelineOpen((current) => !current);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selection, isTimelineOpen, hasTimelineSelection]);

  const handleSelectDomain = useCallback((id: ControlDomainId) => {
    setSelection({ kind: "control-domain", id });
  }, []);

  const toggleExecutionGroup = useCallback((groupKey: string) => {
    setExpandedExecutionGroups((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) {
        next.delete(groupKey);
      } else {
        next.add(groupKey);
      }
      return next;
    });
  }, []);

  const handleCanvasNodeClick = useCallback(
    (node: { id: string; type?: string; data?: Record<string, unknown> }) => {
      const data = node.data ?? {};
      if (node.type === "control_domain" && typeof data.domainId === "string") {
        setSelection({ kind: "control-domain", id: data.domainId as ControlDomainId });
        return;
      }
      if (node.type === "runtime_service" && typeof data.serviceId === "string") {
        setSelection({ kind: "runtime-service", serviceId: data.serviceId });
        return;
      }
      if (node.type === "execution_step" && typeof data.stepId === "string") {
        const groupKey = typeof data.groupKey === "string" ? data.groupKey : undefined;
        setSelection({ kind: "execution-step", stepId: data.stepId, groupKey });
        return;
      }
      if (node.id.startsWith("control-domain:")) {
        setSelection({
          kind: "control-domain",
          id: node.id.replace("control-domain:", "") as ControlDomainId,
        });
      }
    },
    [],
  );

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(14,116,144,0.18),transparent_35%),linear-gradient(180deg,#020617_0%,#020817_45%,#030712_100%)] text-slate-100">
      <WorkflowHeader
        hasChanges={hasChanges}
        hasPendingPlan={Boolean(pendingPlanResult)}
        changedDomainCount={draftVisualState.changedDomainCount}
        compatibilityIssues={compatibilityReport.issues.map((issue) => issue.message)}
        onPlanRequest={handlePlanRequest}
        onApplyRequest={handleApplyConfirmed}
        onDiscardPlan={() => setPendingPlanResult(null)}
        onReset={handleReset}
        isLoading={isLoading}
        activeRequestId={systemState?.active_request_id ?? null}
        activeTaskStatus={systemState?.active_task_status ?? null}
        workflowStatus={systemState?.workflow_status ?? null}
        llmRuntimeId={systemState?.llm_runtime_id ?? null}
        llmProvider={systemState?.llm_provider_name ?? null}
        llmModel={systemState?.llm_model ?? null}
      />

      <div className="space-y-5 px-6 py-6">
        <section className="rounded-[28px] border border-white/10 bg-slate-950/80 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
                {t("workflowControl.labels.executionFlow")}
              </div>
              <h2 className="mt-2 text-xl font-semibold text-slate-100">
                {t("workflowControl.labels.executionGraph")}
              </h2>
            </div>
            <Badge tone="neutral">
              {(systemState?.execution_steps ?? []).length}
            </Badge>
          </div>
          <p className="mt-2 text-sm text-slate-400">
            {t("workflowControl.messages.executionGraphHint")}
          </p>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-slate-900/60 px-3 py-2">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <Badge tone="neutral">
                {t("workflowControl.labels.selection")}
              </Badge>
              {selectionSummary ? (
                <>
                  <Badge tone="neutral">
                    {selectionSummary.kind === "control-domain"
                      ? t("workflowControl.labels.controlDomains")
                      : selectionSummary.kind === "runtime-service"
                        ? t("workflowControl.labels.runtimeServices")
                        : t("workflowControl.labels.executionSteps")}
                  </Badge>
                  <span className="truncate text-sm text-slate-200" title={selectionSummary.value}>
                    {selectionSummary.value}
                  </span>
                </>
              ) : (
                <span className="text-sm text-slate-500">
                  {t("workflowControl.messages.noSelection")}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">{t("workflowControl.messages.selectionHotkeysHint")}</span>
              <Button
                size="xs"
                variant="ghost"
                onClick={() => setSelection(null)}
                disabled={!selection}
              >
                {t("workflowControl.actions.clearSelection")}
              </Button>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge tone="neutral">
              {t("workflowControl.labels.graphNodes")}: {graphPreview.nodes.length}
            </Badge>
            <Badge tone="neutral">
              {t("workflowControl.labels.graphEdges")}: {graphPreview.edges.length}
            </Badge>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <div className="rounded-xl border border-cyan-400/25 bg-cyan-500/10 px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-300">
                {t("workflowControl.canvas.control_domain")}
              </div>
              <div className="mt-1 text-xs text-slate-300">
                {t("workflowControl.messages.graphLaneControlHint")}
              </div>
            </div>
            <div className="rounded-xl border border-violet-400/25 bg-violet-500/10 px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-violet-300">
                {t("workflowControl.canvas.runtime_service")}
              </div>
              <div className="mt-1 text-xs text-slate-300">
                {t("workflowControl.messages.graphLaneRuntimeHint")}
              </div>
            </div>
            <div className="rounded-xl border border-emerald-400/25 bg-emerald-500/10 px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-300">
                {t("workflowControl.canvas.execution_step")}
              </div>
              <div className="mt-1 text-xs text-slate-300">
                {t("workflowControl.messages.graphLaneExecutionHint")}
              </div>
            </div>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <div className="rounded-xl border border-cyan-400/20 bg-slate-900/70 px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="relative inline-flex w-10 items-center">
                  <span className="h-0 w-8 border-t-2 border-dashed border-cyan-300/90" />
                  <span className="absolute right-0 h-1.5 w-1.5 rounded-full bg-cyan-300" />
                </span>
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">
                  {t("workflowControl.labels.domainStepRelation")}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-300">
                {t("workflowControl.messages.graphRelationDomainHint")}
              </div>
            </div>
            <div className="rounded-xl border border-violet-400/20 bg-slate-900/70 px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="relative inline-flex w-10 items-center">
                  <span className="h-0 w-8 border-t-2 border-violet-300/90" />
                  <span className="absolute right-0 h-1.5 w-1.5 rounded-full bg-violet-300" />
                </span>
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-200">
                  {t("workflowControl.labels.runtimeStepRelation")}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-300">
                {t("workflowControl.messages.graphRelationRuntimeHint")}
              </div>
            </div>
            <div className="rounded-xl border border-emerald-400/20 bg-slate-900/70 px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="relative inline-flex w-10 items-center">
                  <span className="h-0 w-8 border-t-2 border-emerald-300/90" />
                  <span className="absolute right-0 h-1.5 w-1.5 rounded-full bg-emerald-300" />
                </span>
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-200">
                  {t("workflowControl.labels.stepSequenceRelation")}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-300">
                {t("workflowControl.messages.graphRelationSequenceHint")}
              </div>
            </div>
          </div>
          {showGraphRelationsWarning ? (
            <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              {t("workflowControl.messages.graphRelationsMissing")}
            </div>
          ) : null}
          <div className="mt-4 h-[720px] overflow-hidden rounded-2xl border border-white/10 bg-slate-950/70">
            <WorkflowCanvas
              systemState={systemState}
              onNodeClick={handleCanvasNodeClick}
              selectedControlDomainId={
                selection?.kind === "control-domain" ? selection.id : null
              }
              selectedRuntimeServiceId={
                selection?.kind === "runtime-service" ? selection.serviceId : null
              }
              selectedExecutionStepId={
                selection?.kind === "execution-step" ? selection.stepId : null
              }
              expandedGroupKeys={expandedExecutionGroups}
              onToggleExecutionGroup={toggleExecutionGroup}
              readOnly
            />
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
          <aside className="space-y-4">
            <section className="rounded-[28px] border border-white/10 bg-slate-950/80 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
                {t("workflowControl.labels.controlSurface")}
              </div>
              <h2 className="mt-2 text-xl font-semibold text-slate-100">
                {t("workflowControl.labels.controlDomains")}
              </h2>
              <p className="mt-2 text-sm text-slate-400">
                {t("workflowControl.messages.controlSurfaceHint")}
              </p>

              <div className="mt-5 space-y-2">
                {controlDomainCards.map((card) => {
                  const isSelected =
                    selection?.kind === "control-domain" && selection.id === card.id;
                  const hasConflict = (compatibilityReport.issuesByDomain[card.id] ?? []).length > 0;
                  const isChanged = card.changed;
                  return (
                    <button
                      key={card.id}
                      type="button"
                      onClick={() => handleSelectDomain(card.id)}
                      className={[
                        "w-full rounded-2xl border px-4 py-3 text-left transition",
                        isSelected
                          ? "border-cyan-400/50 bg-cyan-500/10 shadow-[0_0_30px_rgba(34,211,238,0.12)]"
                          : hasConflict
                            ? "border-amber-400/30 bg-amber-500/10 hover:border-amber-300/40"
                            : isChanged
                              ? "border-sky-400/20 bg-sky-500/10 hover:border-sky-300/30"
                          : "border-white/10 bg-slate-900/80 hover:border-white/20 hover:bg-slate-900",
                      ].join(" ")}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-slate-100">
                            {sectionTitleForDomain(card.id, t)}
                          </div>
                          <div className="mt-1 text-xs uppercase tracking-[0.22em] text-slate-500">
                            {card.source ?? t("workflowControl.common.unknown")}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-2">
                          {card.changed ? (
                            <Badge tone="warning">{t("workflowControl.status.draft")}</Badge>
                          ) : null}
                          {card.restartRequired ? (
                            <Badge tone="danger">{t("workflowControl.labels.restartImpact")}</Badge>
                          ) : null}
                          {hasConflict ? (
                            <Badge tone="warning">
                              {t("workflowControl.labels.compatibilityConflict")}
                            </Badge>
                          ) : null}
                        </div>
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-3">
                        <div className="text-sm text-slate-300">{card.value}</div>
                        {card.affectedServices.length > 0 ? (
                          <div className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-slate-500">
                            {card.affectedServices.length} svc
                          </div>
                        ) : null}
                      </div>
                      {hasConflict ? (
                        <div className="mt-2 rounded-xl border border-amber-400/15 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                          {(compatibilityReport.issuesByDomain[card.id] ?? [])[0]?.message}
                        </div>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </section>
          </aside>

          <main className="space-y-5">
            <WorkflowTargetPanel
              status={systemState?.workflow_status ?? "unknown"}
              allowedOperations={systemState?.allowed_operations ?? []}
              onPause={pauseWorkflow}
              onResume={resumeWorkflow}
              onCancel={cancelWorkflow}
              onRetry={retryWorkflow}
              onDryRun={dryRun}
              isLoading={isLoading}
            />

            <section
              data-testid="workflow-drilldown-timeline"
              className="rounded-[28px] border border-white/10 bg-slate-950/80 p-3 shadow-[0_18px_60px_rgba(2,6,23,0.45)]"
            >
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-slate-900/60 px-4 py-3 text-left"
                onClick={() => {
                  if (hasTimelineSelection) return;
                  setIsTimelineOpen((current) => !current);
                }}
              >
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-400">
                    {t("workflowControl.actions.details")}
                  </div>
                  <div className="mt-1 text-sm font-semibold text-slate-100">
                    {t("workflowControl.labels.executionSteps")}
                  </div>
                </div>
                <Badge tone="neutral">
                  {isTimelineExpanded
                    ? hasTimelineSelection
                      ? t("workflowControl.labels.expanded")
                      : t("workflowControl.actions.collapse")
                    : t("workflowControl.actions.expand")}
                </Badge>
              </button>
              {isTimelineExpanded ? (
                <div className="mt-3">
                  <WorkflowExecutionTimeline
                    executionSteps={systemState?.execution_steps ?? []}
                    runtimeServices={systemState?.runtime_services ?? []}
                    stepToGroupKey={executionStepGroupState.stepToGroupKey}
                    groupSizes={executionStepGroupState.groupSizes}
                    groupToStepIds={executionStepGroupState.groupToStepIds}
                    expandedGroupKeys={expandedExecutionGroups}
                    selection={selection}
                    onSelectStep={(stepId) =>
                      setSelection({
                        kind: "execution-step",
                        stepId,
                        groupKey: executionStepGroupState.stepToGroupKey.get(stepId),
                      })
                    }
                    onSelectService={(serviceId) =>
                      setSelection({ kind: "runtime-service", serviceId })
                    }
                    onToggleExecutionGroup={toggleExecutionGroup}
                  />
                </div>
              ) : null}
            </section>
          </main>

          <aside className="min-h-[420px]">
            <WorkflowInspectorPanel
              selection={selection}
              systemState={systemState}
              draftState={draftState}
              propertyPanelOptions={propertyPanelOptions}
              onUpdateNode={handleUpdateNode}
              onRuntimeServiceAction={runtimeServiceAction}
              onExecutionStepAction={executionStepAction}
              onSelectRuntimeService={(serviceId) =>
                setSelection({ kind: "runtime-service", serviceId })
              }
              onSelectControlDomain={handleSelectDomain}
              expandedGroupKeys={expandedExecutionGroups}
              groupSizes={executionStepGroupState.groupSizes}
              groupToStepIds={executionStepGroupState.groupToStepIds}
              onSelectExecutionStep={(stepId, groupKey) =>
                setSelection({ kind: "execution-step", stepId, groupKey })
              }
              onToggleExecutionGroup={toggleExecutionGroup}
              isLoading={isLoading}
            />
          </aside>
        </div>
      </div>

      {applyResults && shouldShowApplyResultsModal(showResultsModal, applyResults) && (
        <ApplyResultsModal
          results={applyResults}
          onClose={() => setShowResultsModal(false)}
        />
      )}

      {error && (
        <div className="fixed bottom-5 right-5 max-w-sm rounded-2xl border border-red-500/40 bg-red-950/90 p-4 text-red-100 shadow-2xl">
          <p className="font-semibold">{t("workflowControl.common.errorTitle")}</p>
          <p className="mt-1 text-sm">{error}</p>
        </div>
      )}
    </div>
  );
}
