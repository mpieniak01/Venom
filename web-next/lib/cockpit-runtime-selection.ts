export function resolveCockpitRuntimeModelSelection(
  currentSelection: string,
  runtimeModels: ReadonlyArray<string>,
): string {
  const normalizedSelection = currentSelection.trim();
  if (!normalizedSelection) {
    return "";
  }
  return runtimeModels.includes(normalizedSelection) ? normalizedSelection : "";
}

type CatalogRuntimeModel = {
  name: string;
  active?: boolean;
};

type CatalogRuntime = {
  runtime_id: string;
  active?: boolean;
  source_type?: "local-runtime" | "cloud-api";
  models?: ReadonlyArray<CatalogRuntimeModel>;
};

type UnifiedModelCatalogLike = {
  active?: {
    runtime_id?: string | null;
    active_server?: string | null;
    active_model?: string | null;
  } | null;
  runtimes?: ReadonlyArray<CatalogRuntime>;
} | null;

type ActiveRuntimeInfo = {
  status?: string;
  active_server?: string | null;
  active_endpoint?: string | null;
  active_model?: string | null;
  config_hash?: string | null;
  runtime_id?: string | null;
  source_type?: "local-runtime" | "cloud-api";
  requested_model_alias?: string | null;
  resolved_model_id?: string | null;
  resolution_reason?: "exact" | "fallback" | "resource_guard" | "not_found" | null;
  last_models?: {
    ollama?: string;
    vllm?: string;
    previous_ollama?: string;
    previous_vllm?: string;
  };
  start_result?: {
    ok?: boolean;
    exit_code?: number | null;
    error?: string;
  } | null;
  stop_results?: Record<
    string,
    { ok?: boolean; exit_code?: number | null; error?: string }
  > | null;
} | null;

export function resolveCockpitActiveRuntimeInfo(
  catalog: UnifiedModelCatalogLike,
  fallback: ActiveRuntimeInfo,
): ActiveRuntimeInfo {
  const catalogRuntimes = catalog?.runtimes ?? [];
  const declaredRuntimeId =
    (catalog?.active?.runtime_id || catalog?.active?.active_server || "").trim();
  const activeRuntime =
    catalogRuntimes.find((runtime) => runtime.runtime_id === declaredRuntimeId) ??
    catalogRuntimes.find((runtime) => runtime.active) ??
    null;
  const activeRuntimeId =
    declaredRuntimeId ||
    (activeRuntime?.runtime_id || "").trim() ||
    (fallback?.runtime_id || fallback?.active_server || "").trim();

  if (!activeRuntimeId) {
    return fallback;
  }

  const runtimeModels = activeRuntime?.models ?? [];
  const declaredActiveModel = (catalog?.active?.active_model || "").trim();
  const runtimeActiveModel = runtimeModels.find((model) => model.active)?.name || "";
  const activeModelFromCatalog = declaredActiveModel || runtimeActiveModel.trim();
  const fallbackMatchesActiveRuntime =
    (fallback?.active_server || fallback?.runtime_id || "").trim() === activeRuntimeId;
  let resolvedActiveModel: string | null = null;
  if (activeModelFromCatalog) {
    resolvedActiveModel = activeModelFromCatalog;
  } else if (fallbackMatchesActiveRuntime) {
    resolvedActiveModel = fallback?.active_model || null;
  }

  return {
    ...fallback,
    active_server: activeRuntimeId,
    runtime_id: activeRuntimeId,
    active_model: resolvedActiveModel,
    ...(activeRuntime?.source_type ?? fallback?.source_type
      ? { source_type: activeRuntime?.source_type ?? fallback?.source_type }
      : {}),
  };
}
