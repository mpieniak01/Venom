import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type {
  OperatorConfigField,
  OperatorExecutionStep,
  OperatorRuntimeService,
  OperatorGraphEdge,
  OperatorGraphNode,
  SystemState,
} from "@/types/workflow-control";

type SourceTag = "local" | "cloud";
type RelationKind = "domain" | "runtime" | "sequence";
type CanonicalBackendNodeType = "control_domain" | "runtime_service" | "execution_step";

export type BuildWorkflowGraphOptions = {
  expandedGroupKeys?: Set<string>;
};

const CLOUD_PROVIDERS = new Set([
  "openai",
  "google",
  "gemini",
  "anthropic",
  "azure-openai",
  "azure",
  "cohere",
  "mistral",
  "together",
  "groq",
  "bedrock",
]);

const CLOUD_EMBEDDING_MARKERS = [
  "text-embedding",
  "openai",
  "gemini",
  "google",
  "voyage",
  "cohere",
];

function isCloudProvider(provider: string | undefined): boolean {
  if (!provider) return false;
  return CLOUD_PROVIDERS.has(provider.trim().toLowerCase());
}

function normalizeSourceTag(source: unknown): SourceTag | null {
  if (typeof source !== "string") {
    return null;
  }
  const normalized = source.trim().toLowerCase();
  if (normalized === "cloud") return "cloud";
  if (
    normalized === "local" ||
    normalized === "installed_local" ||
    normalized === "installed-local"
  ) {
    return "local";
  }
  return null;
}

function resolveEmbeddingSource(
  embeddingModel: string | undefined,
  activeProvider: string | undefined
): SourceTag {
  const model = (embeddingModel || "").trim().toLowerCase();
  if (model && CLOUD_EMBEDDING_MARKERS.some((marker) => model.includes(marker))) {
    return "cloud";
  }
  if (isCloudProvider(activeProvider)) {
    return "cloud";
  }
  return "local";
}

function hasBackendGraph(systemState: SystemState): boolean {
  const hasRuntimeOrSteps =
    (systemState.runtime_services?.length ?? 0) > 0 ||
    (systemState.execution_steps?.length ?? 0) > 0;
  const backendNodes = systemState.graph?.nodes ?? [];
  const backendEdges = systemState.graph?.edges ?? [];

  if (backendNodes.length === 0) {
    return false;
  }
  if (hasRuntimeOrSteps && backendEdges.length === 0) {
    return false;
  }

  return Boolean(
    systemState.graph?.nodes &&
      systemState.graph?.edges &&
      systemState.graph.nodes.length > 0
  );
}

const LEGACY_BACKEND_NODE_TYPES = new Set([
  "decision",
  "intent",
  "kernel",
  "runtime",
  "provider",
  "embedding",
  "config",
]);

const SUPPORTED_BACKEND_NODE_TYPES = new Set([
  "control_domain",
  "runtime_service",
  "execution_step",
  "swimlane",
]);

function firstStringValue(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === "string") {
      return value;
    }
  }
  return undefined;
}

function resolveCanvasLane(
  nodeData: Record<string, unknown>,
  fallback: CanonicalBackendNodeType,
): string {
  const lane = nodeData.canvasLane;
  return typeof lane === "string" ? lane : fallback;
}

function markerEndForRelation(relationKind: RelationKind) {
  if (relationKind === "domain") {
    return {
      type: MarkerType.ArrowClosed,
      color: "#22d3ee",
      width: 18,
      height: 18,
    };
  }
  if (relationKind === "runtime") {
    return {
      type: MarkerType.ArrowClosed,
      color: "#a78bfa",
      width: 18,
      height: 18,
    };
  }
  return {
    type: MarkerType.ArrowClosed,
    color: "#34d399",
    width: 18,
    height: 18,
  };
}

function resolveRelationLabel(
  relationKind: RelationKind | undefined,
): string | undefined {
  if (relationKind === "domain") {
    return "domain";
  }
  if (relationKind === "runtime") {
    return "runtime";
  }
  if (relationKind === "sequence") {
    return "depends";
  }
  return undefined;
}

function backendNodeTypeFromId(nodeId: string): CanonicalBackendNodeType | null {
  if (nodeId.startsWith("control-domain:")) return "control_domain";
  if (nodeId.startsWith("runtime-service:")) return "runtime_service";
  if (nodeId.startsWith("execution-step:") || nodeId.startsWith("step:")) {
    return "execution_step";
  }
  return null;
}

function normalizeBackendNodeType(node: OperatorGraphNode): string {
  const normalizedType = String(node.type || "")
    .trim()
    .toLowerCase()
    .replaceAll("-", "_");

  if (normalizedType === "control_domain") return "control_domain";
  if (
    normalizedType === "runtime_service" ||
    normalizedType === "runtime_service_node" ||
    normalizedType === "service"
  ) {
    return "runtime_service";
  }
  if (
    normalizedType === "execution_step" ||
    normalizedType === "execution" ||
    normalizedType === "step" ||
    normalizedType === "workflow_step"
  ) {
    return "execution_step";
  }

  const inferredById = backendNodeTypeFromId(node.id);
  if (inferredById) {
    return inferredById;
  }

  return normalizedType;
}

function mapExecutionStepData(node: OperatorGraphNode): Record<string, unknown> {
  const nodeData = node.data ?? {};
  const fallbackStepId = node.id.split(":").slice(1).join(":") || node.id;
  const stepId = firstStringValue(nodeData.stepId) ?? fallbackStepId;
  const action = firstStringValue(nodeData.variant, nodeData.action);
  const label = firstStringValue(nodeData.label, nodeData.component) ?? node.label;
  const status = firstStringValue(nodeData.status, nodeData.state);

  return {
    ...nodeData,
    stepId,
    label,
    variant: action,
    status,
    canvasLane: resolveCanvasLane(nodeData, "execution_step"),
  };
}

function mapRuntimeServiceData(node: OperatorGraphNode): Record<string, unknown> {
  const nodeData = node.data ?? {};
  const fallbackServiceId = node.id.split(":").slice(1).join(":") || node.id;
  const serviceId = firstStringValue(nodeData.serviceId) ?? fallbackServiceId;
  const label = firstStringValue(nodeData.label, nodeData.name) ?? node.label;
  const dependencyCount = Array.isArray(nodeData.dependencies)
    ? nodeData.dependencies.length
    : typeof nodeData.dependencyCount === "number"
      ? nodeData.dependencyCount
      : 0;
  return {
    ...nodeData,
    serviceId,
    label,
    dependencyCount,
    canvasLane: resolveCanvasLane(nodeData, "runtime_service"),
  };
}

function mapControlDomainData(node: OperatorGraphNode): Record<string, unknown> {
  const nodeData = node.data ?? {};
  const fallbackDomainId = node.id.split(":").slice(1).join(":") || node.id;
  const domainId = firstStringValue(nodeData.domainId) ?? fallbackDomainId;
  return {
    ...nodeData,
    domainId,
    label: firstStringValue(nodeData.label) ?? node.label,
    canvasLane: resolveCanvasLane(nodeData, "control_domain"),
  };
}

function mapBackendNodes(nodes: OperatorGraphNode[]): Node[] {
  return nodes.map((node) => {
    const normalizedType = normalizeBackendNodeType(node);
    let mappedData: Record<string, unknown>;
    if (normalizedType === "execution_step") {
      mappedData = mapExecutionStepData(node);
    } else if (normalizedType === "runtime_service") {
      mappedData = mapRuntimeServiceData(node);
    } else if (normalizedType === "control_domain") {
      mappedData = mapControlDomainData(node);
    } else {
      mappedData = node.data ?? {};
    }

    return {
      id: node.id,
      type: normalizedType,
      data: mappedData,
      position: {
        x: node.position?.x ?? 0,
        y: node.position?.y ?? 0,
      },
    };
  });
}

function mapBackendEdges(edges: OperatorGraphEdge[]): Edge[] {
  const inferRelationKind = (
    edgeId: string,
    sourceId: string,
    targetId: string,
  ): RelationKind | null => {
    const normalizedId = edgeId.toLowerCase();
    if (
      normalizedId.startsWith("domain-step:") ||
      normalizedId.startsWith("domain-link:") ||
      normalizedId.startsWith("domain:") ||
      sourceId.startsWith("control-domain:")
    ) {
      return "domain";
    }
    if (
      normalizedId.startsWith("runtime-step:") ||
      normalizedId.startsWith("runtime-link:") ||
      normalizedId.startsWith("service-link:") ||
      normalizedId.startsWith("runtime:") ||
      sourceId.startsWith("runtime-service:")
    ) {
      return "runtime";
    }
    if (
      normalizedId.startsWith("step-") ||
      normalizedId.startsWith("step-sequence:") ||
      normalizedId.startsWith("sequence-link:") ||
      normalizedId.startsWith("depends-link:") ||
      normalizedId.startsWith("step-link:") ||
      normalizedId.startsWith("sequence:") ||
      normalizedId.startsWith("execution:") ||
      sourceId.startsWith("execution-step:") ||
      targetId.startsWith("execution-step:")
    ) {
      return "sequence";
    }
    return null;
  };

  return edges.map((edge) => {
    const typedEdge = edge as OperatorGraphEdge & {
      type?: string;
      data?: Record<string, unknown>;
    };
    const inferredRelationKind = inferRelationKind(edge.id, edge.source, edge.target);
    const inferredWorkflowRelation = inferredRelationKind !== null;
    const edgeData = typedEdge.data as
      | { relationKind?: RelationKind; relationLabel?: string }
      | undefined;
    const relationKind = edgeData?.relationKind ?? inferredRelationKind ?? undefined;
    const relationLabel =
      edgeData?.relationLabel ??
      edge.label ??
      resolveRelationLabel(relationKind);

    return {
      id: edge.id,
      type: inferredWorkflowRelation ? "workflow_relation" : typedEdge.type,
      source: edge.source,
      target: edge.target,
      animated: edge.animated ?? false,
      label: edge.label,
      data: inferredWorkflowRelation
        ? {
            ...typedEdge.data,
            relationKind,
            relationLabel,
          }
        : typedEdge.data,
      markerEnd:
        inferredWorkflowRelation && relationKind
          ? markerEndForRelation(relationKind)
          : undefined,
    };
  });
}

function findConfigField(
  fields: OperatorConfigField[] | undefined,
  key: string,
): OperatorConfigField | undefined {
  return (fields ?? []).find((field) => field.key === key);
}

function readFieldValue(field: OperatorConfigField | undefined): string | null {
  if (!field) return null;
  const candidate = field.effective_value ?? field.value;
  if (typeof candidate === "string") {
    return candidate;
  }
  if (typeof candidate === "number" || typeof candidate === "boolean") {
    return String(candidate);
  }
  return null;
}

function buildStepAlternativePreview(
  configFields: OperatorConfigField[] | undefined,
  relatedConfigKeys: string[] | undefined,
): { alternatives: string[]; alternativeCount: number } {
  const keys = relatedConfigKeys ?? [];
  const alternatives = keys.flatMap((configKey) => {
    const field = findConfigField(configFields, configKey);
    const currentValue = readFieldValue(field);
    const options = (field?.options ?? []).filter((option) => option !== currentValue);
    if (options.length === 0) {
      return [];
    }
    if (keys.length === 1) {
      return options;
    }
    return options.map((option) => `${configKey}:${option}`);
  });

  return {
    alternatives: alternatives.slice(0, 3),
    alternativeCount: alternatives.length,
  };
}

function uniqueValues(values: Array<string | null | undefined>): string[] {
  return Array.from(
    new Set(
      values.filter((value): value is string => typeof value === "string" && value.trim().length > 0),
    ),
  );
}

function mapConfigKeyToDomainId(configKey: string): string | null {
  if (configKey === "AI_MODE") return "decision";
  if (configKey === "INTENT_MODE") return "intent";
  if (configKey === "KERNEL") return "kernel";
  if (configKey === "ACTIVE_PROVIDER") return "provider";
  if (configKey === "EMBEDDING_MODEL") return "embedding";
  return configKey === "WORKFLOW_RUNTIME" ? "config" : null;
}

function buildFallbackControlDomainNodes(
  systemState: SystemState,
  providerSourceTag: SourceTag,
  embeddingSourceTag: SourceTag,
): Node[] {
  const configFields = systemState.config_fields ?? [];
  const domains = [
    {
      id: "control-domain:decision",
      domainId: "decision",
      label: "Decision",
      variant: systemState.decision_strategy,
      optionsCount: findConfigField(configFields, "AI_MODE")?.options?.length ?? 0,
      row: 0,
    },
    {
      id: "control-domain:intent",
      domainId: "intent",
      label: "Intent",
      variant: systemState.intent_mode,
      optionsCount: findConfigField(configFields, "INTENT_MODE")?.options?.length ?? 0,
      row: 1,
    },
    {
      id: "control-domain:kernel",
      domainId: "kernel",
      label: "Kernel",
      variant: systemState.kernel,
      optionsCount: findConfigField(configFields, "KERNEL")?.options?.length ?? 0,
      row: 2,
    },
    {
      id: "control-domain:provider",
      domainId: "provider",
      label: "Provider",
      variant: systemState.provider?.active,
      optionsCount: findConfigField(configFields, "ACTIVE_PROVIDER")?.options?.length ?? 0,
      row: 3,
      sourceTag: providerSourceTag,
    },
    {
      id: "control-domain:embedding",
      domainId: "embedding",
      label: "Embedding",
      variant: systemState.embedding_model,
      optionsCount: findConfigField(configFields, "EMBEDDING_MODEL")?.options?.length ?? 0,
      row: 4,
      sourceTag: embeddingSourceTag,
    },
    {
      id: "control-domain:config",
      domainId: "config",
      label: "Config",
      variant: `${configFields.length} fields`,
      optionsCount: 0,
      row: 5,
    },
  ];

  return domains.map((domain) => ({
    id: domain.id,
    type: "control_domain",
    data: {
      domainId: domain.domainId,
      label: domain.label,
      variant: domain.variant,
      optionsCount: domain.optionsCount,
      sourceTag: domain.sourceTag,
      canvasLane: "control_domain",
      canvasColumn: 0,
      canvasRow: domain.row,
    },
    position: { x: 0, y: 0 },
  }));
}

function buildFallbackRuntimeServiceNodes(
  systemState: SystemState,
): Node[] {
  const services: OperatorRuntimeService[] =
    systemState.runtime_services ??
    ((systemState.runtime?.services ?? []).map((service) =>
      typeof service === "string"
        ? { id: service, name: service }
        : {
            id: service.id ?? service.name ?? "runtime-service",
            name: service.name ?? service.id ?? "runtime-service",
          },
    ) as OperatorRuntimeService[]);
  const depthCache = new Map<string, number>();
  const byId = new Map(services.map((service) => [service.id, service]));
  const computeDepth = (service: OperatorRuntimeService, visiting = new Set<string>()): number => {
    if (depthCache.has(service.id)) return depthCache.get(service.id) ?? 0;
    if (visiting.has(service.id)) return 0;
    visiting.add(service.id);
    const depth = Math.max(
      0,
      ...(service.dependencies ?? []).map((dependencyId) => {
        const dependency = byId.get(dependencyId);
        if (!dependency) return 0;
        return computeDepth(dependency, visiting) + 1;
      }),
    );
    visiting.delete(service.id);
    depthCache.set(service.id, depth);
    return depth;
  };

  const rowsByDepth = new Map<number, number>();
  return services.map((service) => {
    const depth = computeDepth(service);
    const row = rowsByDepth.get(depth) ?? 0;
    rowsByDepth.set(depth, row + 1);
    return {
      id: `runtime-service:${service.id}`,
      type: "runtime_service",
      data: {
        serviceId: service.id,
        label: service.name,
        kind: service.kind,
        status: service.status,
        dependencyCount: (service.dependencies ?? []).length,
        canvasLane: "runtime_service",
        canvasColumn: depth + 1,
        canvasRow: row,
      },
      position: { x: 0, y: 0 },
    };
  });
}

type ExecutionStepNodeBuildResult = {
  nodes: Node[];
  nodeIdByStepId: Map<string, string>;
  visibleStepOrder: string[];
};

function buildFallbackExecutionStepNodes(
  configFields: OperatorConfigField[] | undefined,
  steps: OperatorExecutionStep[] | undefined,
  expandedGroupKeys: Set<string>,
): ExecutionStepNodeBuildResult {
  const orderedSteps = steps ?? [];
  const depthCache = new Map<string, number>();
  const byId = new Map(orderedSteps.map((step) => [step.id, step]));
  const rowsByLane = new Map<string, number>();
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

  const groups = new Map<
    string,
    {
      key: string;
      stepIds: string[];
      steps: OperatorExecutionStep[];
      depth: number;
      stage: string;
      component: string;
      relatedServiceId: string | null;
      relatedConfigKeys: string[];
      parentId: string | null;
      firstIndex: number;
    }
  >();
  const groupOrder: string[] = [];

  orderedSteps.forEach((step, index) => {
    const stage = step.stage?.trim() || "execution";
    const depth = computeDepth(step);
    const parentId = step.depends_on_step_id ?? null;
    const relatedConfigKeys = (step.related_config_keys ?? [])
      .map((key) => String(key))
      .sort((left, right) => left.localeCompare(right));
    const groupKey = [
      parentId ?? "root",
      depth,
      stage,
      step.component,
      step.related_service_id ?? "",
      relatedConfigKeys.join("|"),
    ].join("::");

    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        key: groupKey,
        stepIds: [],
        steps: [],
        depth,
        stage,
        component: step.component,
        relatedServiceId: step.related_service_id ?? null,
        relatedConfigKeys,
        parentId,
        firstIndex: index,
      });
      groupOrder.push(groupKey);
    }

    const group = groups.get(groupKey);
    group?.stepIds.push(step.id);
    group?.steps.push(step);
  });

  const nodeIdByStepId = new Map<string, string>();
  const visibleStepOrder: string[] = [];
  const nodes = groupOrder.flatMap((groupKey) => {
    const group = groups.get(groupKey);
    if (!group) {
      throw new Error(`Missing execution step group: ${groupKey}`);
    }
    const isExpanded = expandedGroupKeys.has(groupKey) && group.steps.length > 1;
    if (isExpanded) {
      return group.steps.map((step, groupIndex) => {
        const alternativePreview = buildStepAlternativePreview(
          configFields,
          step.related_config_keys,
        );
        const laneKey = `${group.depth}:${group.stage}:expanded`;
        const row = rowsByLane.get(laneKey) ?? 0;
        rowsByLane.set(laneKey, row + 1);
        const nodeId = `execution-step:${step.id}`;
        nodeIdByStepId.set(step.id, nodeId);
        visibleStepOrder.push(nodeId);
        return {
          id: nodeId,
          type: "execution_step",
          data: {
            stepId: step.id,
            label: group.component,
            variant: step.action,
            status: step.status,
            stage: group.stage,
            relatedConfigKeys: step.related_config_keys ?? [],
            relatedServiceId: step.related_service_id ?? undefined,
            sequenceIndex: group.firstIndex + groupIndex + 1,
            alternativeVariants: alternativePreview.alternatives,
            alternativeCount: alternativePreview.alternativeCount,
            collapsedStepCount: 0,
            groupKey,
            canExpand: true,
            isExpanded: true,
            groupSize: group.steps.length,
            canvasLane: "execution_step",
            canvasColumn: group.depth + 2,
            canvasRow: row,
          },
          position: { x: 0, y: 0 },
        };
      });
    }
    const primaryStep = group.steps[0];
    const alternativePreview = buildStepAlternativePreview(
      configFields,
      primaryStep?.related_config_keys,
    );
    const groupedActions = uniqueValues(group.steps.slice(1).map((step) => step.action));
    const mergedAlternatives = uniqueValues([
      ...groupedActions,
      ...alternativePreview.alternatives,
    ]);
    const alternativeCount = groupedActions.length + alternativePreview.alternativeCount;
    const laneKey = `${group.depth}:${group.stage}`;
    const row = rowsByLane.get(laneKey) ?? 0;
    rowsByLane.set(laneKey, row + 1);
    const nodeId = `execution-step:${primaryStep.id}`;

    group.stepIds.forEach((stepId) => {
      nodeIdByStepId.set(stepId, nodeId);
    });
    visibleStepOrder.push(nodeId);

    return {
      id: nodeId,
      type: "execution_step",
      data: {
        stepId: primaryStep.id,
        label: group.component,
        variant: primaryStep.action,
        status: primaryStep.status,
        stage: group.stage,
        relatedConfigKeys: group.relatedConfigKeys,
        relatedServiceId: group.relatedServiceId ?? undefined,
        sequenceIndex: group.firstIndex + 1,
        alternativeVariants: mergedAlternatives.slice(0, 4),
        alternativeCount,
        collapsedStepCount: Math.max(0, group.steps.length - 1),
        groupKey,
        canExpand: group.steps.length > 1,
        isExpanded: false,
        groupSize: group.steps.length,
        canvasLane: "execution_step",
        canvasColumn: group.depth + 2,
        canvasRow: row,
      },
      position: { x: 0, y: 0 },
    };
  });

  return {
    nodes,
    nodeIdByStepId,
    visibleStepOrder,
  };
}

function buildFallbackEdges(
  systemState: SystemState,
  runtimeNodes: Node[],
  nodeIdByStepId: Map<string, string>,
  visibleStepOrder: string[],
): Edge[] {
  const edges: Edge[] = [];
  const steps = systemState.execution_steps ?? [];
  const seenEdges = new Set<string>();

  steps.forEach((step, index) => {
    const stepNodeId = nodeIdByStepId.get(step.id) ?? `execution-step:${step.id}`;

    if (step.depends_on_step_id) {
      const sourceNodeId =
        nodeIdByStepId.get(step.depends_on_step_id) ?? `execution-step:${step.depends_on_step_id}`;
      const edgeId = `step-edge:${sourceNodeId}->${stepNodeId}`;
      if (!seenEdges.has(edgeId) && sourceNodeId !== stepNodeId) {
        seenEdges.add(edgeId);
        edges.push({
          id: edgeId,
          type: "workflow_relation",
          source: sourceNodeId,
          target: stepNodeId,
          animated: true,
          markerEnd: markerEndForRelation("sequence"),
          data: {
            relationKind: "sequence",
            relationLabel: "depends",
          },
        });
      }
    } else if (index > 0) {
      const sourceNodeId =
        nodeIdByStepId.get(steps[index - 1]?.id ?? "") ??
        visibleStepOrder[Math.max(0, visibleStepOrder.indexOf(stepNodeId) - 1)];
      const edgeId = `step-sequence:${sourceNodeId}->${stepNodeId}`;
      if (sourceNodeId && !seenEdges.has(edgeId) && sourceNodeId !== stepNodeId) {
        seenEdges.add(edgeId);
        edges.push({
          id: edgeId,
          type: "workflow_relation",
          source: sourceNodeId,
          target: stepNodeId,
          animated: true,
          markerEnd: markerEndForRelation("sequence"),
          data: {
            relationKind: "sequence",
            relationLabel: "flow",
          },
        });
      }
    }

    if (step.related_service_id) {
      const runtimeNodeId = `runtime-service:${step.related_service_id}`;
      const edgeId = `runtime-step:${runtimeNodeId}->${stepNodeId}`;
      if (
        runtimeNodes.some((node) => node.id === runtimeNodeId) &&
        !seenEdges.has(edgeId)
      ) {
        seenEdges.add(edgeId);
        edges.push({
          id: edgeId,
          type: "workflow_relation",
          source: runtimeNodeId,
          target: stepNodeId,
          animated: true,
          markerEnd: markerEndForRelation("runtime"),
          data: {
            relationKind: "runtime",
            relationLabel: "runtime",
          },
        });
      }
    }

    (step.related_config_keys ?? []).forEach((configKey) => {
      const domainId = mapConfigKeyToDomainId(configKey);
      if (!domainId) return;
      const edgeId = `domain-step:${domainId}->${stepNodeId}:${configKey}`;
      if (seenEdges.has(edgeId)) return;
      seenEdges.add(edgeId);
      edges.push({
        id: edgeId,
        type: "workflow_relation",
        source: `control-domain:${domainId}`,
        target: stepNodeId,
        animated: false,
        markerEnd: markerEndForRelation("domain"),
        data: {
          relationKind: "domain",
          relationLabel: configKey,
        },
      });
    });
  });

  return edges;
}

export function buildWorkflowGraph(systemState: SystemState | null): {
  nodes: Node[];
  edges: Edge[];
}

export function buildWorkflowGraph(
  systemState: SystemState | null,
  options: BuildWorkflowGraphOptions,
): {
  nodes: Node[];
  edges: Edge[];
}

export function buildWorkflowGraph(
  systemState: SystemState | null,
  options: BuildWorkflowGraphOptions = {},
): {
  nodes: Node[];
  edges: Edge[];
} {
  if (!systemState) {
    return { nodes: [], edges: [] };
  }

  const buildDerivedGraph = () => {
    const activeProvider = systemState.provider?.active;
    const providerSourceTag: SourceTag =
      normalizeSourceTag(systemState.provider_source) ??
      normalizeSourceTag(systemState.provider?.sourceType) ??
      (isCloudProvider(activeProvider) ? "cloud" : "local");
    const embeddingSourceTag: SourceTag =
      normalizeSourceTag(systemState.embedding_source) ??
      resolveEmbeddingSource(systemState.embedding_model, activeProvider);
    const controlNodes = buildFallbackControlDomainNodes(
      systemState,
      providerSourceTag,
      embeddingSourceTag,
    );
    const runtimeNodes = buildFallbackRuntimeServiceNodes(systemState);
    const expandedGroupKeys = options.expandedGroupKeys ?? new Set<string>();
    const executionGraph = buildFallbackExecutionStepNodes(
      systemState.config_fields,
      systemState.execution_steps,
      expandedGroupKeys,
    );
    const edges = buildFallbackEdges(
      systemState,
      runtimeNodes,
      executionGraph.nodeIdByStepId,
      executionGraph.visibleStepOrder,
    );

    return {
      nodes: [...controlNodes, ...runtimeNodes, ...executionGraph.nodes],
      edges,
    };
  };

  if (hasBackendGraph(systemState)) {
    const backendNodes = mapBackendNodes(systemState.graph?.nodes ?? []);
    const backendEdges = mapBackendEdges(systemState.graph?.edges ?? []);
    const backendNodeTypes = new Set(
      backendNodes.map((node) => String(node.type || "").trim().toLowerCase()),
    );
    const hasLegacyNodes = Array.from(backendNodeTypes).some((type) =>
      LEGACY_BACKEND_NODE_TYPES.has(type),
    );
    const hasUnsupportedNodes = Array.from(backendNodeTypes).some(
      (type) =>
        !LEGACY_BACKEND_NODE_TYPES.has(type) &&
        !SUPPORTED_BACKEND_NODE_TYPES.has(type),
    );
    if (hasLegacyNodes || hasUnsupportedNodes) {
      return buildDerivedGraph();
    }

    return { nodes: backendNodes, edges: backendEdges };
  }

  return buildDerivedGraph();
}
