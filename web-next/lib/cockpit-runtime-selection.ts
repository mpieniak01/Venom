import type { LlmRuntimeSourceType, LlmRuntimeTargetOption } from "./types";

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

export function resolveCockpitEmptyRuntimeModelUpdate(
  runtimeId: string,
  activeModel: string,
  currentSelection: string,
): string | null {
  if (runtimeId === "vast_ollama" || runtimeId === "openrouter") {
    return currentSelection.trim() ? "" : null;
  }
  const normalizedSelection = currentSelection.trim();
  const fallbackModel = (activeModel || normalizedSelection).trim();
  if (!fallbackModel) {
    return currentSelection ? "" : null;
  }
  return fallbackModel !== normalizedSelection ? fallbackModel : null;
}

export function normalizeRuntimeId(value: string | null | undefined): string {
  const candidate = (value || "").trim();
  if (!candidate) {
    return "";
  }
  if (candidate.toLowerCase().startsWith("ollama@vast:")) return "vast_ollama";
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
  source_type?: LlmRuntimeSourceType;
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

export type ActiveRuntimeInfo = {
  status?: string;
  active_server?: string | null;
  active_endpoint?: string | null;
  active_model?: string | null;
  config_hash?: string | null;
  runtime_id?: string | null;
  source_type?: LlmRuntimeSourceType;
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
  runtime_switch_gate?: {
    in_progress?: boolean;
    active_requests?: number;
    switch_id?: string | null;
    source?: string | null;
    from_runtime?: string | null;
    to_runtime?: string | null;
    started_at_utc?: string | null;
    reason?: string | null;
  } | null;
  last_runtime_switch?: {
    at_utc?: string | null;
    from_runtime?: string | null;
    to_runtime?: string | null;
    source?: string | null;
    reason?: string | null;
    model?: string | null;
  } | null;
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

function resolveCatalogRuntimeIdentity(
  activeRuntimeId: string,
  catalog: UnifiedModelCatalogLike,
  fallback: ActiveRuntimeInfo,
  fallbackRuntimeId: string,
): string {
  if (activeRuntimeId !== "vast_ollama" && activeRuntimeId !== "openrouter") {
    return activeRuntimeId;
  }
  const declaredIdentity = catalog?.active?.runtime_id;
  if (declaredIdentity?.startsWith("ollama@vast:") || declaredIdentity?.startsWith("openrouter@")) {
    return declaredIdentity;
  }
  if (fallbackRuntimeId === activeRuntimeId) {
    return fallback?.runtime_id ?? activeRuntimeId;
  }
  return activeRuntimeId;
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
    runtime_id: resolveCatalogRuntimeIdentity(
      activeRuntimeId, catalog, fallback, fallbackRuntimeId,
    ),
    active_model: resolvedActiveModel,
    ...(activeRuntime?.source_type ?? fallback?.source_type
      ? { source_type: activeRuntime?.source_type ?? fallback?.source_type }
      : {}),
  };
}
export function resolveCockpitSelectedRuntimeId(
  selectedRuntime: string,
  catalog: UnifiedModelCatalogLike,
  fallback: ActiveRuntimeInfo,
): string {
  return normalizeRuntimeId(
    selectedRuntime || resolveCockpitActiveRuntimeInfo(catalog, fallback)?.active_server,
  );
}

export function isCockpitRuntimeDisabled(
  runtime: (Pick<LlmRuntimeTargetOption, "configured" | "status" | "reason"> & Partial<Pick<LlmRuntimeTargetOption, "runtime_id" | "source_type" | "available" | "models">>) | null | undefined,
): boolean {
  if (!runtime) return true;
  if ((runtime.runtime_id === "vast_ollama" || runtime.runtime_id === "openrouter" || runtime.source_type === "remote")
    && (!runtime.available || !runtime.models?.length)) return true;
  return runtime.configured === false
    || (runtime.status || "").trim().toLowerCase() === "disabled"
    || ["runtime_disabled_by_profile", "runtime_not_installed", "runtime_not_supported"].includes(runtime.reason ?? "");
}

export function isCockpitAdapterDeployAvailable(
  runtime: Pick<LlmRuntimeTargetOption,
    "configured" | "status" | "reason" | "adapter_deploy_supported" | "supports_adapter_runtime_apply"
  > | null | undefined,
): boolean {
  if (!runtime || isCockpitRuntimeDisabled(runtime)) return false;
  const supported = runtime.adapter_deploy_supported ?? runtime.supports_adapter_runtime_apply;
  return supported === true && (runtime.status || "").trim().toLowerCase() !== "offline";
}
