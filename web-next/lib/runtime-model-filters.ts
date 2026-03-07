export function isRuntimeAdapterArtifactModel(
  model: {
    is_adapter_artifact?: boolean;
    model_kind?: string | null;
  },
): boolean {
  if (typeof model.is_adapter_artifact === "boolean") {
    return model.is_adapter_artifact;
  }
  return (model.model_kind || "").trim().toLowerCase() === "adapter_artifact";
}

export function filterRuntimeBaseModels<
  T extends {
    is_adapter_artifact?: boolean;
    model_kind?: string | null;
  },
>(
  models: ReadonlyArray<T>,
): T[] {
  return models.filter((model) => !isRuntimeAdapterArtifactModel(model));
}
