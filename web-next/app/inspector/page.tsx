"use client";

import { useTranslation } from "@/lib/i18n";
import { useInspectorState } from "./use-inspector-state";
import { InspectorHeaderStats } from "@/components/inspector/inspector-header-stats";
import { InspectorSidebar } from "@/components/inspector/inspector-sidebar";
import { InspectorWorkspace } from "@/components/inspector/inspector-workspace";

export default function InspectorPage() {
  const t = useTranslation();
  const state = useInspectorState(t);

  return (
    <div className="space-y-6 pb-10">
      <InspectorHeaderStats
        t={t}
        inspectorStats={state.inspectorStats}
        taskBreakdown={state.taskBreakdown}
        latencyCards={state.latencyCards}
      />

      <div className={`grid gap-6 ${state.flowFullscreen ? "grid-cols-1" : "xl:grid-cols-[360px_minmax(0,1fr)]"}`}>
        <InspectorSidebar
          t={t}
          hidden={state.flowFullscreen}
          history={state.history}
          selectedId={state.selectedId}
          onSelect={(requestId) => {
            void state.handleHistorySelect(requestId);
          }}
          onRefresh={state.handleHistoryRefresh}
          refreshPending={state.historyRefreshPending}
          activeTasks={state.inspectorStats.activeTasks}
          taskBreakdown={state.taskBreakdown}
        />

        <InspectorWorkspace
          t={t}
          selectedId={state.selectedId}
          detailError={state.detailError}
          flowFullscreen={state.flowFullscreen}
          setFlowFullscreen={(next) => state.setFlowFullscreen(next)}
          svgRef={state.svgRef}
          fitViewRef={state.fitViewRef}
          diagramLoading={state.diagramLoading}
          mermaidError={state.mermaidError}
          reloadMermaid={() => state.setMermaidReloadKey(state.mermaidReloadKey + 1)}
          retrySelect={() => {
            if (!state.selectedId) return;
            void state.handleHistorySelect(state.selectedId, true);
          }}
          steps={state.steps}
          stepFilter={state.stepFilter}
          setStepFilter={state.setStepFilter}
          contractOnly={state.contractOnly}
          setContractOnly={state.setContractOnly}
          copyMessage={state.copyMessage}
          onCopy={state.handleCopySteps}
          filteredSteps={state.filteredSteps}
          focusedIndex={state.focusedIndex}
          setFocusedIndex={state.setFocusedIndex}
          liveSelectedStatus={state.liveSelectedStatus}
          streamConnected={Boolean(state.streamForSelected?.connected)}
          selectedRequest={state.selectedRequest}
          inspectorFailed={state.inspectorStats.failed}
          focusedStep={state.focusedStep}
        />
      </div>
    </div>
  );
}
