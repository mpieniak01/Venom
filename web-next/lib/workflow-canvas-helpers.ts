import type { Edge, Node } from "@xyflow/react";
import type {
  OperatorConfigField,
  OperatorExecutionStep,
  OperatorRuntimeService,
  OperatorGraphEdge,
  OperatorGraphNode,
  SystemState,
} from "@/types/workflow-control";

type SourceTag = "local" | "cloud";

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
  return Boolean(
    systemState.graph?.nodes &&
      systemState.graph?.edges &&
      systemState.graph.nodes.length > 0
  );
}

function mapBackendNodes(nodes: OperatorGraphNode[]): Node[] {
  return nodes.map((node) => ({
    id: node.id,
    type: node.type,
    data: node.data ?? {},
    position: {
      x: node.position?.x ?? 0,
      y: node.position?.y ?? 0,
    },
  }));
}

function mapBackendEdges(edges: OperatorGraphEdge[]): Edge[] {
  return edges.map((edge) => {
    const typedEdge = edge as OperatorGraphEdge & {
      type?: string;
      data?: Record<string, unknown>;
    };
    const inferredWorkflowRelation =
      edge.id.startsWith("domain-step:") ||
      edge.id.startsWith("runtime-step:") ||
      edge.id.startsWith("step-") ||
      edge.id.startsWith("step-sequence:") ||
      edge.id.startsWith("runtime-link:") ||
      edge.id.startsWith("domain-link:") ||
      edge.id.startsWith("service-link:") ||
      edge.id.startsWith("sequence-link:") ||
      edge.id.startsWith("depends-link:") ||
      edge.id.startsWith("step-link:") ||
      edge.id.startsWith("link:") ||
      edge.id.startsWith("edge:") ||
      edge.id.startsWith("graph:") ||
      edge.id.startsWith("flow:") ||
      edge.id.startsWith("execution:") ||
      edge.id.startsWith("runtime:") ||
      edge.id.startsWith("domain:") ||
      edge.id.startsWith("sequence:");

    return {
      id: edge.id,
      type: inferredWorkflowRelation ? "workflow_relation" : typedEdge.type,
      source: edge.source,
      target: edge.target,
      animated: edge.animated ?? false,
      label: edge.label,
      data:
        typedEdge.data ??
        (edge.label
          ? {
              relationLabel: edge.label,
            }
          : undefined),
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
    const relatedConfigKeys = [...(step.related_config_keys ?? [])].sort();
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
  const nodes = groupOrder.map((groupKey) => {
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
  }).flat();

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

  if (hasBackendGraph(systemState)) {
    return {
      nodes: mapBackendNodes(systemState.graph?.nodes ?? []),
      edges: mapBackendEdges(systemState.graph?.edges ?? []),
    };
  }

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
}
