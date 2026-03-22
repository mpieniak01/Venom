import { Clock3, Cpu, Database, Play, RefreshCw, Server, Square, Waypoints } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import {
  buildSelectionNode,
  findExecutionStep,
  findRuntimeService,
  getSeverityTone,
  getStatusTone,
  mapConfigKeyToControlDomain,
  type ControlDomainId,
  type WorkflowControlSelection,
} from "@/lib/workflow-control-screen";
import type { PropertyPanelOptions } from "@/lib/workflow-control-options";
import type {
  OperatorExecutionStep,
  OperatorRuntimeService,
  SystemState,
} from "@/types/workflow-control";

import { PropertyPanel } from "./PropertyPanel";

type RuntimeServiceAction = "start" | "stop" | "restart";
type ExecutionStepAction = "retry_from_step" | "replay_step" | "skip_step";

interface WorkflowInspectorPanelProps {
  selection: WorkflowControlSelection | null;
  systemState: SystemState | null;
  draftState: SystemState | null;
  propertyPanelOptions: PropertyPanelOptions;
  onUpdateNode: (nodeId: string, data: unknown) => void;
  onRuntimeServiceAction: (
    serviceId: string,
    action: RuntimeServiceAction,
  ) => Promise<boolean>;
  onExecutionStepAction: (
    stepId: string,
    action: ExecutionStepAction,
  ) => Promise<boolean>;
  onSelectRuntimeService: (serviceId: string) => void;
  onSelectControlDomain: (domainId: ControlDomainId) => void;
  expandedGroupKeys: Set<string>;
  groupSizes: Map<string, number>;
  groupToStepIds: Map<string, string[]>;
  onSelectExecutionStep: (stepId: string, groupKey?: string) => void;
  onToggleExecutionGroup: (groupKey: string) => void;
  isLoading?: boolean;
}

function DetailRow({
  label,
  value,
}: Readonly<{
  label: string;
  value: string | number | null | undefined;
}>) {
  if (value == null || value === "") return null;
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/5 py-2 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="max-w-[60%] text-right font-mono text-slate-200">{value}</span>
    </div>
  );
}

function InspectorUnavailable({
  message,
}: Readonly<{ message: string }>) {
  return (
    <div className="rounded-[28px] border border-white/10 bg-slate-950/90 p-6 text-sm text-slate-400">
      {message}
    </div>
  );
}

function RuntimeServiceInspector({
  service,
  onRuntimeServiceAction,
  isLoading,
  t,
}: Readonly<{
  service: OperatorRuntimeService;
  onRuntimeServiceAction: (
    serviceId: string,
    action: RuntimeServiceAction,
  ) => Promise<boolean>;
  isLoading?: boolean;
  t: (path: string) => string;
}>) {
  const dependencies = service.dependencies ?? [];
  const allowedActions = service.allowed_actions ?? [];

  return (
    <div className="rounded-[28px] border border-white/10 bg-slate-950/90 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
            {t("workflowControl.panels.propertyInspector")}
          </div>
          <div className="mt-2 flex items-center gap-3">
            <Server className="h-5 w-5 text-cyan-400" />
            <h3 className="text-lg font-semibold text-slate-100">{service.name}</h3>
          </div>
        </div>
        <Badge tone={getStatusTone(service.status)}>{service.status}</Badge>
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 bg-slate-900/80 p-4">
        <DetailRow label={t("workflowControl.labels.serviceKind")} value={service.kind} />
        <DetailRow label="PID" value={service.pid} />
        <DetailRow label="Port" value={service.port} />
        <DetailRow label="CPU %" value={service.cpu_percent} />
        <DetailRow label="Memory MB" value={service.memory_mb} />
        <DetailRow
          label={t("workflowControl.labels.runtimeVersion")}
          value={service.runtime_version}
        />
      </div>

      <div className="mt-4">
        <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
          {t("workflowControl.labels.serviceDependencies")}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {dependencies.length > 0 ? (
            dependencies.map((dependency) => (
              <span
                key={dependency}
                className="rounded-full border border-white/10 px-2 py-1 text-xs text-slate-300"
              >
                {dependency}
              </span>
            ))
          ) : (
            <span className="text-sm text-slate-500">{t("workflowControl.common.na")}</span>
          )}
        </div>
      </div>

      <div className="mt-5">
        <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
          {t("workflowControl.labels.allowedActions")}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onRuntimeServiceAction(service.id, "start")}
            disabled={isLoading || !allowedActions.includes("start")}
          >
            <Play className="h-3.5 w-3.5" />
            start
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={() => onRuntimeServiceAction(service.id, "stop")}
            disabled={isLoading || !allowedActions.includes("stop")}
          >
            <Square className="h-3.5 w-3.5" />
            stop
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onRuntimeServiceAction(service.id, "restart")}
            disabled={isLoading || !allowedActions.includes("restart")}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            restart
          </Button>
        </div>
      </div>
    </div>
  );
}

function ExecutionStepGroupSection({
  step,
  groupKey,
  groupSize,
  isGroupExpanded,
  groupSteps,
  onToggleExecutionGroup,
  onSelectExecutionStep,
  t,
}: Readonly<{
  step: OperatorExecutionStep;
  groupKey?: string;
  groupSize: number;
  isGroupExpanded: boolean;
  groupSteps: OperatorExecutionStep[];
  onToggleExecutionGroup: (groupKey: string) => void;
  onSelectExecutionStep: (stepId: string, groupKey?: string) => void;
  t: (path: string) => string;
}>) {
  if (!groupKey || groupSize <= 1) {
    return null;
  }
  return (
    <div className="mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-cyan-100">
          {groupSize} {t("workflowControl.labels.branches")}
        </div>
        <Button
          size="xs"
          variant="ghost"
          onClick={() => onToggleExecutionGroup(groupKey)}
        >
          {isGroupExpanded
            ? t("workflowControl.actions.collapse")
            : t("workflowControl.actions.expand")}
        </Button>
      </div>
      {groupSteps.length > 1 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {groupSteps.map((variantStep) => (
            <Button
              key={variantStep.id}
              size="xs"
              variant={variantStep.id === step.id ? "secondary" : "ghost"}
              onClick={() => onSelectExecutionStep(variantStep.id, groupKey)}
            >
              {variantStep.action}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ExecutionStepRelationsSection({
  step,
  onSelectRuntimeService,
  onSelectControlDomain,
  t,
}: Readonly<{
  step: OperatorExecutionStep;
  onSelectRuntimeService: (serviceId: string) => void;
  onSelectControlDomain: (domainId: ControlDomainId) => void;
  t: (path: string) => string;
}>) {
  const hasRelatedConfig = (step.related_config_keys ?? []).length > 0;
  if (!step.related_service_id && !hasRelatedConfig) {
    return null;
  }

  return (
    <div className="mt-5 space-y-4">
      {step.related_service_id ? (
        <div>
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
            {t("workflowControl.labels.relatedService")}
          </div>
          <div className="mt-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onSelectRuntimeService(step.related_service_id!)}
            >
              <Server className="h-3.5 w-3.5" />
              {step.related_service_id}
            </Button>
          </div>
        </div>
      ) : null}

      {hasRelatedConfig ? (
        <div>
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
            {t("workflowControl.labels.relatedConfig")}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(step.related_config_keys ?? []).map((configKey) => {
              const domainId = mapConfigKeyToControlDomain(configKey);
              return (
                <Button
                  key={configKey}
                  size="sm"
                  variant="ghost"
                  onClick={() => onSelectControlDomain(domainId ?? "config")}
                >
                  {configKey}
                </Button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ExecutionStepActionsSection({
  step,
  isLoading,
  onExecutionStepAction,
  t,
}: Readonly<{
  step: OperatorExecutionStep;
  isLoading?: boolean;
  onExecutionStepAction: (
    stepId: string,
    action: ExecutionStepAction,
  ) => Promise<boolean>;
  t: (path: string) => string;
}>) {
  const allowedActions = step.allowed_actions ?? [];
  if (allowedActions.length === 0) {
    return null;
  }
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
        {t("workflowControl.labels.allowedActions")}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onExecutionStepAction(step.id, "retry_from_step")}
          disabled={isLoading || !allowedActions.includes("retry_from_step")}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          {t("workflowControl.actions.retryFromStep")}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onExecutionStepAction(step.id, "replay_step")}
          disabled={isLoading || !allowedActions.includes("replay_step")}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          {t("workflowControl.actions.replayStep")}
        </Button>
        <Button
          size="sm"
          variant="danger"
          onClick={() => onExecutionStepAction(step.id, "skip_step")}
          disabled={isLoading || !allowedActions.includes("skip_step")}
        >
          <Square className="h-3.5 w-3.5" />
          {t("workflowControl.actions.skipStep")}
        </Button>
      </div>
    </div>
  );
}

function ExecutionStepInspector({
  step,
  groupKey,
  groupSizes,
  groupToStepIds,
  expandedGroupKeys,
  executionSteps,
  onToggleExecutionGroup,
  onSelectExecutionStep,
  onSelectRuntimeService,
  onSelectControlDomain,
  onExecutionStepAction,
  isLoading,
  t,
}: Readonly<{
  step: OperatorExecutionStep;
  groupKey?: string;
  groupSizes: Map<string, number>;
  groupToStepIds: Map<string, string[]>;
  expandedGroupKeys: Set<string>;
  executionSteps: OperatorExecutionStep[];
  onToggleExecutionGroup: (groupKey: string) => void;
  onSelectExecutionStep: (stepId: string, groupKey?: string) => void;
  onSelectRuntimeService: (serviceId: string) => void;
  onSelectControlDomain: (domainId: ControlDomainId) => void;
  onExecutionStepAction: (
    stepId: string,
    action: "retry_from_step" | "replay_step" | "skip_step",
  ) => Promise<boolean>;
  isLoading?: boolean;
  t: (path: string) => string;
}>) {
  const groupSize = groupKey ? (groupSizes.get(groupKey) ?? 1) : 1;
  const isGroupExpanded = groupKey ? expandedGroupKeys.has(groupKey) : false;
  const groupStepIds = groupKey ? (groupToStepIds.get(groupKey) ?? []) : [];
  const groupSteps = groupStepIds
    .map((stepId) => findExecutionStep(executionSteps, stepId))
    .filter((groupStep): groupStep is OperatorExecutionStep => Boolean(groupStep));

  return (
    <div className="rounded-[28px] border border-white/10 bg-slate-950/90 p-5 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
            {t("workflowControl.labels.executionFlow")}
          </div>
          <div className="mt-2 flex items-center gap-3">
            <Waypoints className="h-5 w-5 text-cyan-400" />
            <h3 className="text-lg font-semibold text-slate-100">
              {step.component}:{step.action}
            </h3>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {step.severity ? (
            <Badge tone={getSeverityTone(step.severity)}>{step.severity}</Badge>
          ) : null}
          <Badge tone={getStatusTone(step.status)}>{step.status}</Badge>
        </div>
      </div>

      <ExecutionStepGroupSection
        step={step}
        groupKey={groupKey}
        groupSize={groupSize}
        isGroupExpanded={isGroupExpanded}
        groupSteps={groupSteps}
        onToggleExecutionGroup={onToggleExecutionGroup}
        onSelectExecutionStep={onSelectExecutionStep}
        t={t}
      />

      <div className="mt-4 rounded-2xl border border-white/10 bg-slate-900/80 p-4">
        <DetailRow label="ID" value={step.id} />
        <DetailRow label={t("workflowControl.labels.stage")} value={step.stage} />
        <DetailRow label={t("workflowControl.labels.component")} value={step.component} />
        <DetailRow label={t("workflowControl.labels.action")} value={step.action} />
        <DetailRow
          label={t("workflowControl.labels.timestamp")}
          value={step.timestamp ? new Date(step.timestamp).toLocaleString() : null}
        />
        <DetailRow
          label={t("workflowControl.labels.dependsOn")}
          value={step.depends_on_step_id}
        />
        <DetailRow label={t("workflowControl.labels.severity")} value={step.severity} />
      </div>

      <ExecutionStepRelationsSection
        step={step}
        onSelectRuntimeService={onSelectRuntimeService}
        onSelectControlDomain={onSelectControlDomain}
        t={t}
      />

      <div className="mt-5 space-y-3">
        <ExecutionStepActionsSection
          step={step}
          isLoading={isLoading}
          onExecutionStepAction={onExecutionStepAction}
          t={t}
        />
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.24em] text-slate-500">
          <Database className="h-4 w-4" />
          {t("workflowControl.actions.details")}
        </div>
        <pre className="max-h-[420px] overflow-auto rounded-2xl border border-white/10 bg-slate-900/80 p-4 text-xs text-slate-200">
          {step.details ?? t("workflowControl.common.na")}
        </pre>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Clock3 className="h-4 w-4" />
          {t("workflowControl.messages.stepSelectionHint")}
        </div>
      </div>
    </div>
  );
}

function InspectorEmptyState({ t }: Readonly<{ t: (path: string) => string }>) {
  return (
    <div className="rounded-[28px] border border-white/10 bg-slate-950/90 p-6 shadow-[0_18px_60px_rgba(2,6,23,0.45)]">
      <div className="flex items-center gap-3">
        <Cpu className="h-5 w-5 text-cyan-400" />
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-400">
            {t("workflowControl.panels.propertyInspector")}
          </div>
          <h3 className="mt-2 text-lg font-semibold text-slate-100">
            {t("workflowControl.messages.inspectorEmptyTitle")}
          </h3>
        </div>
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-400">
        {t("workflowControl.messages.inspectorEmptyHint")}
      </p>
    </div>
  );
}

export function WorkflowInspectorPanel({
  selection,
  systemState,
  draftState,
  propertyPanelOptions,
  onUpdateNode,
  onRuntimeServiceAction,
  onExecutionStepAction,
  onSelectRuntimeService,
  onSelectControlDomain,
  expandedGroupKeys,
  groupSizes,
  groupToStepIds,
  onSelectExecutionStep,
  onToggleExecutionGroup,
  isLoading,
}: Readonly<WorkflowInspectorPanelProps>) {
  const t = useTranslation();
  const unavailableMessage = t("workflowControl.messages.inspectorUnavailable");

  if (selection?.kind === "control-domain") {
    return (
      <PropertyPanel
        selectedNode={buildSelectionNode(selection, draftState)}
        onUpdateNode={onUpdateNode}
        availableOptions={propertyPanelOptions}
        configFields={draftState?.config_fields}
      />
    );
  }

  if (selection?.kind === "runtime-service") {
    const service = findRuntimeService(systemState?.runtime_services, selection.serviceId);
    if (!service) {
      return <InspectorUnavailable message={unavailableMessage} />;
    }
    return (
      <RuntimeServiceInspector
        service={service}
        onRuntimeServiceAction={onRuntimeServiceAction}
        isLoading={isLoading}
        t={t}
      />
    );
  }

  if (selection?.kind === "execution-step") {
    const step = findExecutionStep(systemState?.execution_steps, selection.stepId);
    if (!step) {
      return <InspectorUnavailable message={unavailableMessage} />;
    }
    return (
      <ExecutionStepInspector
        step={step}
        groupKey={selection.groupKey}
        groupSizes={groupSizes}
        groupToStepIds={groupToStepIds}
        expandedGroupKeys={expandedGroupKeys}
        executionSteps={systemState?.execution_steps ?? []}
        onToggleExecutionGroup={onToggleExecutionGroup}
        onSelectExecutionStep={onSelectExecutionStep}
        onSelectRuntimeService={onSelectRuntimeService}
        onSelectControlDomain={onSelectControlDomain}
        onExecutionStepAction={onExecutionStepAction}
        isLoading={isLoading}
        t={t}
      />
    );
  }

  return <InspectorEmptyState t={t} />;
}
