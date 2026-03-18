import type { Edge, Node } from "@xyflow/react";
import type {
  OperatorGraphEdge,
  OperatorGraphNode,
  SystemState,
} from "@/types/workflow-control";

type SourceTag = "local" | "cloud";

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
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    animated: edge.animated ?? false,
    label: edge.label,
  }));
}

export function buildWorkflowGraph(systemState: SystemState | null): {
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

  const nodes: Node[] = [
    {
      id: "decision",
      type: "decision",
      data: {
        strategy: systemState.decision_strategy,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "intent",
      type: "intent",
      data: {
        intentMode: systemState.intent_mode,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "kernel",
      type: "kernel",
      data: {
        kernel: systemState.kernel,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "runtime",
      type: "runtime",
      data: {
        runtime: systemState.runtime,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "provider",
      type: "provider",
      data: {
        provider: systemState.provider
          ? { ...systemState.provider, sourceType: providerSourceTag }
          : { sourceType: providerSourceTag },
        sourceType: providerSourceTag,
        sourceTag: providerSourceTag,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "embedding",
      type: "embedding",
      data: {
        model: systemState.embedding_model,
        sourceType: embeddingSourceTag,
        sourceTag: embeddingSourceTag,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "config",
      type: "config",
      data: {
        configFields: systemState.config_fields ?? [],
        fieldCount: (systemState.config_fields ?? []).length,
      },
      position: { x: 0, y: 0 },
    },
  ];

  const edges: Edge[] = [
    { id: "e1", source: "decision", target: "intent", animated: true },
    { id: "e2", source: "intent", target: "kernel", animated: true },
    { id: "e3", source: "kernel", target: "runtime", animated: true },
    { id: "e4", source: "runtime", target: "embedding", animated: true },
    { id: "e5", source: "embedding", target: "config", animated: true },
    { id: "e6", source: "config", target: "provider", animated: true },
  ];

  return { nodes, edges };
}
