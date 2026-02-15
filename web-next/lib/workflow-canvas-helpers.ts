import type { Edge, Node } from "@xyflow/react";
import type { SystemState } from "@/types/workflow-control";

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

export function buildWorkflowGraph(systemState: SystemState | null): {
  nodes: Node[];
  edges: Edge[];
} {
  if (!systemState) {
    return { nodes: [], edges: [] };
  }

  const activeProvider = systemState.provider?.active;
  const providerSourceTag: SourceTag = isCloudProvider(activeProvider) ? "cloud" : "local";
  const embeddingSourceTag: SourceTag = resolveEmbeddingSource(
    systemState.embedding_model,
    activeProvider
  );

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
        provider: systemState.provider,
        sourceTag: providerSourceTag,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "embedding",
      type: "embedding",
      data: {
        model: systemState.embedding_model,
        sourceTag: embeddingSourceTag,
      },
      position: { x: 0, y: 0 },
    },
  ];

  const edges: Edge[] = [
    { id: "e1", source: "decision", target: "intent", animated: true },
    { id: "e2", source: "intent", target: "kernel", animated: true },
    { id: "e3", source: "kernel", target: "runtime", animated: true },
    { id: "e4", source: "runtime", target: "embedding", animated: true },
    { id: "e5", source: "embedding", target: "provider", animated: true },
  ];

  return { nodes, edges };
}
