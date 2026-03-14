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

export function normalizeRuntimeId(value: string | null | undefined): string {
  const candidate = (value || "").trim();
  if (!candidate) {
    return "";
  }
  const atIndex = candidate.indexOf("@");
  if (atIndex <= 0) {
    return candidate.toLowerCase();
  }
  return candidate.slice(0, atIndex).trim().toLowerCase();
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

function findActiveCatalogRuntime(
  catalogRuntimes: ReadonlyArray<CatalogRuntime>,
  declaredRuntimeId: string,
): CatalogRuntime | null {
  let firstActiveRuntime: CatalogRuntime | null = null;
  for (const runtime of catalogRuntimes) {
    if (!firstActiveRuntime && runtime.active) {
      firstActiveRuntime = runtime;
    }
    if (
      declaredRuntimeId &&
      normalizeRuntimeId(runtime.runtime_id) === declaredRuntimeId
    ) {
      return runtime;
    }
  }
  return firstActiveRuntime;
}

function resolveCatalogActiveModel(
  activeRuntime: CatalogRuntime | null,
  catalog: UnifiedModelCatalogLike,
  fallback: ActiveRuntimeInfo,
  activeRuntimeId: string,
  fallbackRuntimeId: string,
): string | null {
  const runtimeModels = activeRuntime?.models ?? [];
  const declaredActiveModel = (catalog?.active?.active_model || "").trim();
  const runtimeActiveModel = runtimeModels.find((model) => model.active)?.name || "";
  const activeModelFromCatalog = declaredActiveModel || runtimeActiveModel.trim();
  if (activeModelFromCatalog) {
    return activeModelFromCatalog;
  }
  return fallbackRuntimeId === activeRuntimeId ? fallback?.active_model || null : null;
}

export function resolveCockpitActiveRuntimeInfo(
  catalog: UnifiedModelCatalogLike,
  fallback: ActiveRuntimeInfo,
): ActiveRuntimeInfo {
  const catalogRuntimes = catalog?.runtimes ?? [];
  const declaredRuntimeId = normalizeRuntimeId(
    catalog?.active?.runtime_id || catalog?.active?.active_server,
  );

  let activeRuntime = findActiveCatalogRuntime(catalogRuntimes, declaredRuntimeId);
  activeRuntime ??= null;

  const activeRuntimeNormalizedId = normalizeRuntimeId(activeRuntime?.runtime_id || "");
  const fallbackRuntimeId = normalizeRuntimeId(
    fallback?.active_server || fallback?.runtime_id || "",
  );
  const activeRuntimeId = declaredRuntimeId || activeRuntimeNormalizedId || fallbackRuntimeId;

  if (!activeRuntimeId) {
    return fallback;
  }

  const resolvedActiveModel = resolveCatalogActiveModel(
    activeRuntime,
    catalog,
    fallback,
    activeRuntimeId,
    fallbackRuntimeId,
  );

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
