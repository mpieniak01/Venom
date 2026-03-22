import { ArrowRight, GitBranch, Layers3, Link2, Server } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useTranslation } from "@/lib/i18n";
import {
  buildExecutionStepLanes,
  buildRuntimeServiceTracks,
  getSeverityTone,
  getStatusTone,
  type WorkflowControlSelection,
} from "@/lib/workflow-control-screen";
import type {
  OperatorExecutionStep,
  OperatorRuntimeService,
} from "@/types/workflow-control";

interface WorkflowExecutionTimelineProps {
  executionSteps: OperatorExecutionStep[];
  runtimeServices: OperatorRuntimeService[];
  stepToGroupKey: Map<string, string>;
  groupSizes: Map<string, number>;
  groupToStepIds: Map<string, string[]>;
  expandedGroupKeys: Set<string>;
  selection: WorkflowControlSelection | null;
  onSelectStep: (stepId: string) => void;
  onSelectService: (serviceId: string) => void;
  onToggleExecutionGroup: (groupKey: string) => void;
}

function truncateDetails(details: string | null | undefined): string {
  if (!details) return "";
  if (details.length <= 120) return details;
  return `${details.slice(0, 117)}...`;
}

interface ExecutionStepCardProps {
  step: OperatorExecutionStep;
  selection: WorkflowControlSelection | null;
  stepToGroupKey: Map<string, string>;
  groupSizes: Map<string, number>;
  expandedGroupKeys: Set<string>;
  stepIndexMap: Map<string, number>;
  onSelectStep: (stepId: string) => void;
  onToggleExecutionGroup: (groupKey: string) => void;
  t: (path: string) => string;
}

function ExecutionStepCard({
  step,
  selection,
  stepToGroupKey,
  groupSizes,
  expandedGroupKeys,
  stepIndexMap,
  onSelectStep,
  onToggleExecutionGroup,
  t,
}: Readonly<ExecutionStepCardProps>) {
  const isSelected =
    selection?.kind === "execution-step" &&
    selection.stepId === step.id;
  const groupKey = stepToGroupKey.get(step.id);
  const groupSize = groupKey ? (groupSizes.get(groupKey) ?? 1) : 1;
  const isGroupExpanded = groupKey ? expandedGroupKeys.has(groupKey) : false;
  const canToggleGroup = Boolean(groupKey && groupSize > 1);
  const stepIndex = stepIndexMap.get(step.id) ?? 0;
  const dependsOnIndex = step.depends_on_step_id
    ? stepIndexMap.get(step.depends_on_step_id)
    : null;

  return (
    <div
      className={[
        "relative w-full rounded-2xl border px-4 py-3 transition",
        isSelected
          ? "border-cyan-400/50 bg-cyan-500/10 shadow-[0_0_30px_rgba(34,211,238,0.12)]"
          : "border-white/10 bg-slate-950/70 hover:border-white/20 hover:bg-slate-950",
      ].join(" ")}
    >
      <button
        type="button"
        className="group flex w-full items-start gap-4 text-left"
        onClick={() => onSelectStep(step.id)}
      >
        <div className="flex min-w-[44px] items-center justify-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-slate-950 text-sm font-semibold text-slate-200">
            {stepIndex}
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Layers3 className="h-4 w-4 text-cyan-400" />
                <span className="truncate text-sm font-semibold text-slate-100">
                  {step.component}
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-500" />
                <span className="truncate text-sm text-slate-300">
                  {step.action}
                </span>
              </div>
              <div className="mt-1 truncate text-xs text-slate-400">
                {truncateDetails(step.details)}
              </div>
            </div>
            <div
              className={[
                "flex shrink-0 items-center gap-2",
                canToggleGroup ? "pr-24" : "",
              ].join(" ")}
            >
              {step.timestamp ? (
                <span className="text-[11px] text-slate-500">
                  {new Date(step.timestamp).toLocaleString()}
                </span>
              ) : null}
              <Badge tone={getStatusTone(step.status)}>{step.status}</Badge>
              {step.severity ? (
                <Badge tone={getSeverityTone(step.severity)}>
                  {step.severity}
                </Badge>
              ) : null}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500">
            {dependsOnIndex ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-1">
                <GitBranch className="h-3.5 w-3.5" />
                {t("workflowControl.labels.upstreamStep")} #{dependsOnIndex}
              </span>
            ) : null}
            {step.related_service_id ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-1">
                <Server className="h-3.5 w-3.5" />
                {step.related_service_id}
              </span>
            ) : null}
            {(step.related_config_keys ?? []).slice(0, 2).map((configKey) => (
              <span
                key={configKey}
                className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-1"
              >
                {configKey}
              </span>
            ))}
            {groupKey && groupSize > 1 ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-cyan-400/20 bg-cyan-500/10 px-2 py-1 text-cyan-100">
                {groupSize} {t("workflowControl.labels.branches")}
                {isGroupExpanded
                  ? ` (${t("workflowControl.labels.expanded")})`
                  : ""}
              </span>
            ) : null}
            <span className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-1">
              <Link2 className="h-3.5 w-3.5" />
              {step.id}
            </span>
          </div>
        </div>
      </button>
      {canToggleGroup && groupKey ? (
        <button
          type="button"
          className="absolute right-4 top-3 rounded-full border border-white/10 px-2 py-1 text-[11px] text-slate-300 hover:border-cyan-400/30 hover:text-cyan-100"
          onClick={() => onToggleExecutionGroup(groupKey)}
        >
          {isGroupExpanded
            ? t("workflowControl.actions.collapse")
            : t("workflowControl.actions.expand")}
        </button>
      ) : null}
    </div>
  );
}

export function WorkflowExecutionTimeline({
  executionSteps,
  runtimeServices,
  stepToGroupKey,
  groupSizes,
  groupToStepIds,
  expandedGroupKeys,
  selection,
  onSelectStep,
  onSelectService,
  onToggleExecutionGroup,
}: Readonly<WorkflowExecutionTimelineProps>) {
  const t = useTranslation();
  const runtimeTracks = buildRuntimeServiceTracks(runtimeServices);
  const executionLanes = buildExecutionStepLanes(executionSteps);
  const stepIndexMap = new Map(executionSteps.map((step, index) => [step.id, index + 1]));
  const selectedStep =
    selection?.kind === "execution-step"
      ? executionSteps.find((step) => step.id === selection.stepId) ?? null
      : null;
  const selectedGroupKey =
    selection?.kind === "execution-step"
      ? selection.groupKey ?? stepToGroupKey.get(selection.stepId)
      : undefined;
  const selectedGroupMembers = selectedGroupKey ? (groupToStepIds.get(selectedGroupKey) ?? []) : [];

  return (
    <div className="flex flex-col gap-5">
      <section className="rounded-[28px] border border-white/10 bg-slate-950/80 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
              {t("workflowControl.labels.workflowTarget")}
            </div>
            <h2 className="mt-2 text-xl font-semibold text-slate-100">
              {t("workflowControl.labels.runtimeServices")}
            </h2>
          </div>
          <Badge tone="neutral">{runtimeServices.length}</Badge>
        </div>

        <div className="mt-4 space-y-3">
          {runtimeTracks.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-slate-500">
              {t("workflowControl.messages.noRuntimeServices")}
            </div>
          ) : (
            runtimeTracks.map((track) => (
              <div
                key={track.depth}
                className="rounded-2xl border border-white/10 bg-slate-900/50 p-3"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-500/10 text-[11px] font-semibold text-cyan-200">
                    {track.depth + 1}
                  </div>
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-400">
                      {t("workflowControl.labels.runtimeTrack")} {track.depth + 1}
                    </div>
                    <div className="text-xs text-slate-500">
                      {t("workflowControl.messages.runtimeTrackHint")}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-3">
                  {track.services.map((service) => {
                    const isSelected =
                      selection?.kind === "runtime-service" &&
                      selection.serviceId === service.id;
                    return (
                      <button
                        key={service.id}
                        type="button"
                        className={[
                          "min-w-[200px] flex-1 rounded-2xl border px-4 py-3 text-left transition",
                          isSelected
                            ? "border-cyan-400/50 bg-cyan-500/10 shadow-[0_0_30px_rgba(34,211,238,0.12)]"
                            : "border-white/10 bg-slate-950/70 hover:border-white/20 hover:bg-slate-950",
                        ].join(" ")}
                        onClick={() => onSelectService(service.id)}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-semibold text-slate-100">
                              {service.name}
                            </div>
                            <div className="mt-1 text-[11px] uppercase tracking-[0.24em] text-slate-500">
                              {service.kind ?? t("workflowControl.common.unknown")}
                            </div>
                          </div>
                          <Badge tone={getStatusTone(service.status)}>
                            {service.status ?? "unknown"}
                          </Badge>
                        </div>

                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-400">
                          {service.port ? (
                            <span className="rounded-full border border-white/10 px-2 py-1">
                              port:{service.port}
                            </span>
                          ) : null}
                          {service.pid ? (
                            <span className="rounded-full border border-white/10 px-2 py-1">
                              pid:{service.pid}
                            </span>
                          ) : null}
                        </div>

                        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                          {(service.dependencies ?? []).length > 0 ? (
                            (service.dependencies ?? []).map((dependency) => (
                              <span
                                key={dependency}
                                className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-1 text-slate-300"
                              >
                                <GitBranch className="h-3 w-3 text-cyan-300" />
                                {dependency}
                              </span>
                            ))
                          ) : (
                            <span className="rounded-full border border-dashed border-white/10 px-2 py-1 text-slate-500">
                              {t("workflowControl.messages.noRuntimeDependencies")}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="rounded-[28px] border border-white/10 bg-slate-950/80 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
              {t("workflowControl.labels.executionFlow")}
            </div>
            <h2 className="mt-2 text-xl font-semibold text-slate-100">
              {t("workflowControl.labels.executionSteps")}
            </h2>
          </div>
          <Badge tone="neutral">{executionSteps.length}</Badge>
        </div>

        <div className="mt-5 space-y-4">
          {selectedStep ? (
            <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
              <span className="font-semibold">{t("workflowControl.labels.activeVariant")}:</span>{" "}
              {selectedStep.component}:{selectedStep.action}
              {selectedGroupMembers.length > 1 ? ` (${selectedGroupMembers.length} ${t("workflowControl.labels.branches")})` : ""}
            </div>
          ) : null}
          {executionLanes.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-slate-500">
              {t("workflowControl.messages.noExecutionSteps")}
            </div>
          ) : (
            executionLanes.map((lane) => (
              <div
                key={lane.stage}
                className="grid gap-3 rounded-2xl border border-white/10 bg-slate-900/50 p-3 lg:grid-cols-[150px_minmax(0,1fr)]"
              >
                <div className="rounded-2xl border border-cyan-400/20 bg-slate-950/70 px-4 py-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-400">
                    {t("workflowControl.labels.executionLane")}
                  </div>
                  <div className="mt-2 text-sm font-semibold text-slate-100">
                    {lane.stage}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {lane.steps.length} {t("workflowControl.labels.stepsCount")}
                  </div>
                </div>

                <div className="space-y-2">
                  {lane.steps.map((step) => (
                    <ExecutionStepCard
                      key={step.id}
                      step={step}
                      selection={selection}
                      stepToGroupKey={stepToGroupKey}
                      groupSizes={groupSizes}
                      expandedGroupKeys={expandedGroupKeys}
                      stepIndexMap={stepIndexMap}
                      onSelectStep={onSelectStep}
                      onToggleExecutionGroup={onToggleExecutionGroup}
                      t={t}
                    />
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
