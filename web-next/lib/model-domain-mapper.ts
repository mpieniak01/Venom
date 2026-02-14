/**
 * Model Domain Mapper v2
 * 
 * Maps models from various sources (catalog, installed, trainable) to a unified
 * domain model with source_type, model_role, and academy_trainable classifications.
 */

import type {
  ModelInfo,
  ModelCatalogEntry,
  EnrichedModelInfo,
  ModelSourceType,
  ModelRole,
  ModelTrainabilityStatus,
} from "./types";
import type { TrainableModelInfo } from "./academy-api";

/**
 * Determines the source type based on provider and runtime information
 */
export function inferSourceType(provider?: string | null, runtime?: string): ModelSourceType {
  if (!provider) {
    return "local-runtime";
  }

  const providerLower = provider.toLowerCase();

  // Cloud API providers (OpenAI, Gemini, Anthropic, etc.)
  if (
    providerLower === "openai" ||
    providerLower === "gemini" ||
    providerLower === "anthropic" ||
    providerLower === "cohere"
  ) {
    return "cloud-api";
  }

  // Integrator catalogs (HuggingFace, Ollama)
  if (
    providerLower === "huggingface" ||
    providerLower === "ollama" ||
    providerLower === "hf"
  ) {
    return "integrator-catalog";
  }

  // Runtime providers (vLLM, etc.)
  if (providerLower === "vllm" || runtime === "vllm") {
    return "local-runtime";
  }

  // Default to local runtime for unknown providers
  return "local-runtime";
}

/**
 * Determines the model role based on tags and model name
 */
export function inferModelRole(
  modelName: string,
  tags?: string[] | null
): ModelRole {
  const nameLower = modelName.toLowerCase();
  const tagsLower = tags?.map((t) => t.toLowerCase()) || [];

  // Check for embedding models
  if (
    nameLower.includes("embed") ||
    nameLower.includes("bge-") ||
    nameLower.includes("e5-") ||
    tagsLower.includes("embedding") ||
    tagsLower.includes("sentence-similarity") ||
    tagsLower.includes("feature-extraction")
  ) {
    return "intent-embedding";
  }

  // Default to LLM engine for text generation models
  return "llm-engine";
}

/**
 * Determines trainability status and reason
 */
export function inferTrainability(
  modelName: string,
  trainableModels?: TrainableModelInfo[] | null
): {
  status: ModelTrainabilityStatus;
  reason?: string | null;
} {
  if (!trainableModels || trainableModels.length === 0) {
    // Default to not-trainable if we don't have trainable models data
    return {
      status: "not-trainable",
      reason: "Trainability information not available",
    };
  }

  // Find matching model in trainable list
  const trainableInfo = trainableModels.find(
    (tm) => tm.model_id === modelName || tm.model_id.toLowerCase() === modelName.toLowerCase()
  );

  if (trainableInfo) {
    return {
      status: trainableInfo.trainable ? "trainable" : "not-trainable",
      reason: trainableInfo.reason_if_not_trainable || null,
    };
  }

  // Not found in trainable list
  return {
    status: "not-trainable",
    reason: "Model not in Academy trainable catalog",
  };
}

/**
 * Enriches a ModelCatalogEntry with domain classifications
 */
export function enrichCatalogModel(
  catalogEntry: ModelCatalogEntry,
  trainableModels?: TrainableModelInfo[] | null
): EnrichedModelInfo {
  const sourceType = inferSourceType(catalogEntry.provider, catalogEntry.runtime);
  const modelRole = inferModelRole(catalogEntry.model_name, catalogEntry.tags);
  const trainability = inferTrainability(catalogEntry.model_name, trainableModels);

  return {
    name: catalogEntry.model_name,
    display_name: catalogEntry.display_name,
    size_gb: catalogEntry.size_gb,
    provider: catalogEntry.provider,
    runtime: catalogEntry.runtime,
    installed: false,
    active: false,
    source_type: sourceType,
    model_role: modelRole,
    academy_trainable: trainability.status,
    trainability_reason: trainability.reason,
    tags: catalogEntry.tags,
    downloads: catalogEntry.downloads,
    likes: catalogEntry.likes,
  };
}

/**
 * Enriches a ModelInfo (installed model) with domain classifications
 */
export function enrichInstalledModel(
  modelInfo: ModelInfo,
  trainableModels?: TrainableModelInfo[] | null
): EnrichedModelInfo {
  const sourceType = inferSourceType(modelInfo.provider, modelInfo.type);
  const modelRole = inferModelRole(modelInfo.name);
  const trainability = inferTrainability(modelInfo.name, trainableModels);

  return {
    name: modelInfo.name,
    display_name: modelInfo.name,
    size_gb: modelInfo.size_gb,
    provider: modelInfo.provider || "unknown",
    runtime: modelInfo.type,
    installed: modelInfo.installed,
    active: modelInfo.active,
    source_type: sourceType,
    model_role: modelRole,
    academy_trainable: trainability.status,
    trainability_reason: trainability.reason,
    quantization: modelInfo.quantization,
    path: modelInfo.path,
  };
}

/**
 * Batch enrichment for catalog entries
 */
export function enrichCatalogModels(
  catalogEntries: ModelCatalogEntry[],
  trainableModels?: TrainableModelInfo[] | null
): EnrichedModelInfo[] {
  return catalogEntries.map((entry) => enrichCatalogModel(entry, trainableModels));
}

/**
 * Batch enrichment for installed models
 */
export function enrichInstalledModels(
  installedModels: ModelInfo[],
  trainableModels?: TrainableModelInfo[] | null
): EnrichedModelInfo[] {
  return installedModels.map((model) => enrichInstalledModel(model, trainableModels));
}
