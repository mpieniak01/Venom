import type { Node } from "@xyflow/react";

import type {
  OperatorConfigField,
  OperatorExecutionStep,
  OperatorRuntimeService,
  SystemState,
} from "@/types/workflow-control";

export const CONTROL_DOMAIN_ORDER = [
  "decision",
  "intent",
  "kernel",
  "provider",
  "embedding",
  "config",
] as const;

export type ControlDomainId = (typeof CONTROL_DOMAIN_ORDER)[number];

export type WorkflowControlSelection =
  | { kind: "control-domain"; id: ControlDomainId }
  | { kind: "runtime-service"; serviceId: string }
  | { kind: "execution-step"; stepId: string; groupKey?: string };

export type StatusTone = "success" | "warning" | "danger" | "neutral";

export type RuntimeServiceTrack = {
  depth: number;
  services: OperatorRuntimeService[];
};

export type ExecutionStepLane = {
  stage: string;
  steps: OperatorExecutionStep[];
};

export type ExecutionStepGroupState = {
  stepToGroupKey: Map<string, string>;
  groupSizes: Map<string, number>;
  groupToStepIds: Map<string, string[]>;
};

export type ControlDomainCard = {
  id: ControlDomainId;
  value: string;
  source: string | null;
  restartRequired: boolean;
  editable: boolean;
  changed: boolean;
  affectedServices: string[];
};

const DOMAIN_TO_CONFIG_KEY: Record<Exclude<ControlDomainId, "config">, string> = {
  decision: "AI_MODE",
  intent: "INTENT_MODE",
  kernel: "KERNEL",
  provider: "ACTIVE_PROVIDER",
  embedding: "EMBEDDING_MODEL",
};

const CONFIG_KEY_TO_DOMAIN: Record<string, ControlDomainId> = {
  AI_MODE: "decision",
  INTENT_MODE: "intent",
  KERNEL: "kernel",
  ACTIVE_PROVIDER: "provider",
  EMBEDDING_MODEL: "embedding",
};

function formatValue(value: unknown): string {
  if (value == null || value === "") {
    return "N/A";
  }
  if (typeof value === "string") {
    return value;
  }
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "N/A";
  }
}

function findConfigField(
  configFields: OperatorConfigField[] | undefined,
  key: string,
): OperatorConfigField | undefined {
  return (configFields ?? []).find((field) => field.key === key);
}

function resolveDomainSource({
  id,
  sourceField,
  currentField,
  draft,
  systemState,
}: {
  id: ControlDomainId;
  sourceField: OperatorConfigField | undefined;
  currentField: OperatorConfigField | undefined;
  draft: SystemState;
  systemState: SystemState | null;
}): string | null {
  if (sourceField?.source) {
    return sourceField.source;
  }
  if (currentField?.source) {
    return currentField.source;
  }
  if (id === "provider") {
    return draft.provider_source ?? systemState?.provider_source ?? null;
  }
  if (id === "embedding") {
    return draft.embedding_source ?? systemState?.embedding_source ?? null;
  }
  return null;
}

function resolveRuntimeFieldValue(
  field: OperatorConfigField | undefined,
): string | null {
  if (typeof field?.effective_value === "string") {
    return field.effective_value;
  }
  if (typeof field?.value === "string") {
    return field.value;
  }
  return null;
}

export function getStatusTone(status: string | null | undefined): StatusTone {
  const normalized = (status ?? "").trim().toLowerCase();
  if (["running", "completed", "ok", "success", "succeeded"].includes(normalized)) {
    return "success";
  }
  if (["paused", "draft", "queued", "pending", "warning"].includes(normalized)) {
    return "warning";
  }
  if (["failed", "error", "cancelled", "stopped", "blocked"].includes(normalized)) {
    return "danger";
  }
  return "neutral";
}

export function getSeverityTone(severity: string | null | undefined): StatusTone {
  const normalized = (severity ?? "").trim().toLowerCase();
  if (["error", "critical", "fatal"].includes(normalized)) {
    return "danger";
  }
  if (["warning", "warn", "degraded", "blocked"].includes(normalized)) {
    return "warning";
  }
  if (["normal", "ok", "success"].includes(normalized)) {
    return "success";
  }
  return "neutral";
}

export function buildControlDomainCards(
  systemState: SystemState | null,
  draftState: SystemState | null,
): ControlDomainCard[] {
  const draft = draftState ?? systemState;
  if (!draft) {
    return CONTROL_DOMAIN_ORDER.map((id) => ({
      id,
      value: "N/A",
      source: null,
      restartRequired: false,
      editable: id !== "config",
      changed: false,
      affectedServices: [],
    }));
  }

  return CONTROL_DOMAIN_ORDER.map((id) => {
    if (id === "config") {
      const fields = draft.config_fields ?? [];
      const editableCount = fields.filter((field) => field.editable !== false).length;
      const restartCount = fields.filter((field) => field.restart_required).length;
      return {
        id,
        value: `${fields.length} fields`,
        source: editableCount > 0 ? `${editableCount} editable` : null,
        restartRequired: restartCount > 0,
        editable: editableCount > 0,
        changed: JSON.stringify(systemState?.config_fields ?? []) !== JSON.stringify(fields),
        affectedServices: fields.flatMap((field) => field.affected_services ?? []),
      };
    }

    const configKey = DOMAIN_TO_CONFIG_KEY[id];
    const sourceField = findConfigField(draft.config_fields, configKey);
    const currentField = findConfigField(systemState?.config_fields, configKey);

    let draftValue: unknown;
    let currentValue: unknown;

    if (id === "decision") {
      draftValue = draft.decision_strategy;
      currentValue = systemState?.decision_strategy;
    } else if (id === "intent") {
      draftValue = draft.intent_mode;
      currentValue = systemState?.intent_mode;
    } else if (id === "kernel") {
      draftValue = draft.kernel;
      currentValue = systemState?.kernel;
    } else if (id === "provider") {
      draftValue = draft.provider?.active;
      currentValue = systemState?.provider?.active;
    } else {
      draftValue = draft.embedding_model;
      currentValue = systemState?.embedding_model;
    }

    return {
      id,
      value: formatValue(draftValue ?? sourceField?.effective_value ?? sourceField?.value),
      source: resolveDomainSource({ id, sourceField, currentField, draft, systemState }),
      restartRequired: Boolean(sourceField?.restart_required ?? currentField?.restart_required),
      editable: sourceField?.editable !== false,
      changed: JSON.stringify(currentValue) !== JSON.stringify(draftValue),
      affectedServices: sourceField?.affected_services ?? currentField?.affected_services ?? [],
    };
  });
}

export function buildSelectionNode(selection: WorkflowControlSelection | null, draftState: SystemState | null): Node | null {
  if (!draftState || selection?.kind !== "control-domain") {
    return null;
  }

  if (selection.id === "decision") {
    return {
      id: "decision",
      type: "decision",
      position: { x: 0, y: 0 },
      data: { strategy: draftState.decision_strategy },
    };
  }

  if (selection.id === "intent") {
    const embeddingField = findConfigField(draftState.config_fields, "EMBEDDING_MODEL");
    return {
      id: "intent",
      type: "intent",
      position: { x: 0, y: 0 },
      data: {
        intentMode: draftState.intent_mode,
        embeddingModel:
          draftState.embedding_model ??
          embeddingField?.effective_value ??
          embeddingField?.value,
      },
    };
  }

  if (selection.id === "kernel") {
    const runtimeField = findConfigField(draftState.config_fields, "WORKFLOW_RUNTIME");
    return {
      id: "kernel",
      type: "kernel",
      position: { x: 0, y: 0 },
      data: {
        kernel: draftState.kernel,
        workflowRuntime: resolveRuntimeFieldValue(runtimeField),
      },
    };
  }

  if (selection.id === "provider") {
    const providerSource = draftState.provider?.sourceType ?? draftState.provider_source ?? "local";
    const providerData = draftState.provider ?? undefined;
    return {
      id: "provider",
      type: "provider",
      position: { x: 0, y: 0 },
      data: {
        provider: {
          ...providerData,
          sourceType: providerSource,
        },
        embeddingModel: draftState.embedding_model,
        sourceType: providerSource,
        sourceTag: providerSource,
      },
    };
  }

  if (selection.id === "embedding") {
    const embeddingSource = draftState.embedding_source ?? "local";
    return {
      id: "embedding",
      type: "embedding",
      position: { x: 0, y: 0 },
      data: {
        model: draftState.embedding_model,
        providerActive: draftState.provider?.active,
        sourceType: embeddingSource,
        sourceTag: embeddingSource,
      },
    };
  }

  return {
    id: "config",
    type: "config",
    position: { x: 0, y: 0 },
    data: {
      configFields: draftState.config_fields ?? [],
      fieldCount: (draftState.config_fields ?? []).length,
    },
  };
}

export function findRuntimeService(
  services: OperatorRuntimeService[] | undefined,
  serviceId: string | null | undefined,
): OperatorRuntimeService | null {
  if (!serviceId) return null;
  return (services ?? []).find((service) => service.id === serviceId) ?? null;
}

export function findExecutionStep(
  steps: OperatorExecutionStep[] | undefined,
  stepId: string | null | undefined,
): OperatorExecutionStep | null {
  if (!stepId) return null;
  return (steps ?? []).find((step) => step.id === stepId) ?? null;
}

export function mapConfigKeyToControlDomain(
  configKey: string | null | undefined,
): ControlDomainId | null {
  if (!configKey) return null;
  return CONFIG_KEY_TO_DOMAIN[configKey] ?? null;
}

function computeServiceDepth(
  service: OperatorRuntimeService,
  serviceMap: Map<string, OperatorRuntimeService>,
  visiting: Set<string>,
  cache: Map<string, number>,
): number {
  if (cache.has(service.id)) {
    return cache.get(service.id) ?? 0;
  }

  if (visiting.has(service.id)) {
    return 0;
  }

  visiting.add(service.id);
  const dependencyDepths = (service.dependencies ?? []).map((dependencyId) => {
    const dependency = serviceMap.get(dependencyId);
    if (!dependency) return 0;
    return computeServiceDepth(dependency, serviceMap, visiting, cache) + 1;
  });
  visiting.delete(service.id);

  const depth = dependencyDepths.length > 0 ? Math.max(...dependencyDepths) : 0;
  cache.set(service.id, depth);
  return depth;
}

export function buildRuntimeServiceTracks(
  services: OperatorRuntimeService[] | undefined,
): RuntimeServiceTrack[] {
  const serviceList = services ?? [];
  const serviceMap = new Map(serviceList.map((service) => [service.id, service]));
  const depthCache = new Map<string, number>();
  const grouped = new Map<number, OperatorRuntimeService[]>();

  serviceList.forEach((service) => {
    const depth = computeServiceDepth(service, serviceMap, new Set<string>(), depthCache);
    const bucket = grouped.get(depth) ?? [];
    bucket.push(service);
    grouped.set(depth, bucket);
  });

  return [...grouped.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([depth, trackServices]) => ({
      depth,
      services: [...trackServices].sort((left, right) => left.name.localeCompare(right.name)),
    }));
}

export function buildExecutionStepLanes(
  steps: OperatorExecutionStep[] | undefined,
): ExecutionStepLane[] {
  const lanes = new Map<string, OperatorExecutionStep[]>();

  (steps ?? []).forEach((step) => {
    const stage = step.stage?.trim() || "unassigned";
    const bucket = lanes.get(stage) ?? [];
    bucket.push(step);
    lanes.set(stage, bucket);
  });

  return [...lanes.entries()].map(([stage, laneSteps]) => ({
    stage,
    steps: laneSteps,
  }));
}

export function buildExecutionStepGroupState(
  steps: OperatorExecutionStep[] | undefined,
): ExecutionStepGroupState {
  const stepList = steps ?? [];
  const byId = new Map(stepList.map((step) => [step.id, step]));
  const depthCache = new Map<string, number>();
  const computeDepth = (step: OperatorExecutionStep, visiting = new Set<string>()): number => {
    if (depthCache.has(step.id)) return depthCache.get(step.id) ?? 0;
    if (visiting.has(step.id)) return 0;
    visiting.add(step.id);
    const parentId = step.depends_on_step_id;
    let depth = 0;
    if (parentId) {
      const parent = byId.get(parentId);
      depth = parent ? computeDepth(parent, visiting) + 1 : 1;
    }
    visiting.delete(step.id);
    depthCache.set(step.id, depth);
    return depth;
  };

  const stepToGroupKey = new Map<string, string>();
  const groupSizes = new Map<string, number>();
  const groupToStepIds = new Map<string, string[]>();

  for (const step of stepList) {
    const stage = step.stage?.trim() || "execution";
    const depth = computeDepth(step);
    const parentId = step.depends_on_step_id ?? "root";
    const configKeyPart = (step.related_config_keys ?? [])
      .map((key) => String(key))
      .sort((left, right) => left.localeCompare(right))
      .join("|");
    const groupKey = [
      parentId,
      depth,
      stage,
      step.component,
      step.related_service_id ?? "",
      configKeyPart,
    ].join("::");
    stepToGroupKey.set(step.id, groupKey);
    groupSizes.set(groupKey, (groupSizes.get(groupKey) ?? 0) + 1);
    const members = groupToStepIds.get(groupKey) ?? [];
    members.push(step.id);
    groupToStepIds.set(groupKey, members);
  }

  return { stepToGroupKey, groupSizes, groupToStepIds };
}
