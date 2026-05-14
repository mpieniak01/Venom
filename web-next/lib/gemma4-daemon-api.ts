/**
 * TypeScript types and fetch helpers for the Gemma 4 Audio Daemon API (214A).
 * All functions take an explicit baseUrl so callers can inject the resolved URL
 * from getGemma4ApiBaseUrl() without coupling this module to browser globals.
 */

export type VRAMStatus = {
  backend: string;
  allocated_mb: number;
  reserved_mb: number;
  total_mb: number;
  free_mb: number;
};

export type DaemonParamsInfo = {
  max_new_tokens: number;
  enable_thinking: boolean;
  image_token_budget: number;
  reasoning_summary_enabled: boolean;
  emotion_detection_enabled: boolean;
  emotion_response_style_enabled: boolean;
  cache_implementation: string | null;
  execution_mode: "balanced" | "vision_priority" | "voice_priority";
  image_strategy: "vlm_only" | "ocr_first" | "hybrid";
  retrieval_mode: "off" | "auto" | "always";
  audio_output_mode: "off" | "text_first" | "voice_first";
  assistant_mode: "off" | "attached" | "conditional";
  economy_mode: "off" | "auto";
};

export type RuntimeComponentSnapshotItem = {
  component_id: string;
  component_type: string;
  enabled: boolean;
  available: boolean;
  backend: string;
  model_id: string | null;
  device_target: string;
  health: string;
  last_error: string | null;
};

export type DaemonStatus = {
  target_model: string;
  assistant_model: string | null;
  mode: "target_only" | "target_with_assistant";
  target_loaded: boolean;
  assistant_loaded: boolean;
  params: DaemonParamsInfo;
  vram: VRAMStatus;
  raw_thinking_available: boolean;
  reasoning_summary_status: "disabled" | "summary" | "raw_available";
  reasoning_summary: string | null;
  emotion_label: string | null;
  emotion_confidence: number | null;
  emotion_source: string | null;
  pending_reload: boolean;
  reload_reason: string | null;
  supports_image_input: boolean;
  component_snapshot: RuntimeComponentSnapshotItem[];
};

export type ReloadSignal = "none" | "soft_reload" | "hard_restart";

export type DaemonConfigRequest = {
  max_new_tokens?: number | null;
  enable_thinking?: boolean | null;
  image_token_budget?: number | null;
  reasoning_summary_enabled?: boolean | null;
  emotion_detection_enabled?: boolean | null;
  emotion_response_style_enabled?: boolean | null;
  cache_implementation?: string | null;
  execution_mode?: "balanced" | "vision_priority" | "voice_priority" | null;
  image_strategy?: "vlm_only" | "ocr_first" | "hybrid" | null;
  retrieval_mode?: "off" | "auto" | "always" | null;
  audio_output_mode?: "off" | "text_first" | "voice_first" | null;
  assistant_mode?: "off" | "attached" | "conditional" | null;
  economy_mode?: "off" | "auto" | null;
};

export type DaemonConfigResponse = {
  reload_signal: ReloadSignal;
  applied: DaemonParamsInfo;
  message: string;
};

export type DaemonRespondRequest = {
  model?: string | null;
  messages: Array<{
    role: "system" | "user" | "assistant";
    content: Array<
      | { type: "text"; text: string }
      | { type: "audio"; path: string }
      | { type: "image"; url?: string; path?: string; data?: string }
    >;
  }>;
  task?: string | null;
  max_new_tokens?: number;
};

export type DaemonRespondResponse = {
  text: string;
  model: string;
  input_modalities: string[];
  output_modalities: string[];
  execution_trace: string[];
  selected_policy: string | null;
  selected_image_strategy: string | null;
  retrieval_used: boolean;
  retrieval_context_items: number;
  assistant_used: boolean;
  economy_mode_activated: boolean;
  degradation_reasons: string[];
  component_snapshot: RuntimeComponentSnapshotItem[];
};

async function daemonFetch<T>(
  baseUrl: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${baseUrl}${path}`;
  const resp = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    const detail = text ? `: ${text}` : "";
    throw new Error(`Daemon ${path} → ${resp.status}${detail}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export const fetchDaemonStatus = (baseUrl: string): Promise<DaemonStatus> =>
  daemonFetch<DaemonStatus>(baseUrl, "/v1/daemon/status");

export const postDaemonConfig = (
  baseUrl: string,
  params: DaemonConfigRequest,
): Promise<DaemonConfigResponse> =>
  daemonFetch<DaemonConfigResponse>(baseUrl, "/v1/daemon/config", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const postDaemonReload = (baseUrl: string): Promise<unknown> =>
  daemonFetch(baseUrl, "/v1/daemon/reload", { method: "POST" });

export const postDaemonRestart = (baseUrl: string): Promise<unknown> =>
  daemonFetch(baseUrl, "/v1/daemon/restart", { method: "POST" });

export const postDaemonFallback = (
  baseUrl: string,
): Promise<{ reload_signal: ReloadSignal; message: string }> =>
  daemonFetch(baseUrl, "/v1/daemon/fallback", { method: "POST" });

export const postAttachAssistant = (
  baseUrl: string,
  modelId: string,
): Promise<unknown> =>
  daemonFetch(baseUrl, "/v1/daemon/assistant/attach", {
    method: "POST",
    body: JSON.stringify({ model_id: modelId }),
  });

export const postDetachAssistant = (baseUrl: string): Promise<unknown> =>
  daemonFetch(baseUrl, "/v1/daemon/assistant/detach", { method: "POST" });

export const postDaemonRespond = (
  baseUrl: string,
  payload: DaemonRespondRequest,
): Promise<DaemonRespondResponse> =>
  daemonFetch<DaemonRespondResponse>(baseUrl, "/v1/respond", {
    method: "POST",
    body: JSON.stringify(payload),
  });

// ---------------------------------------------------------------------------
// multi_runtime_profile — system API (goes to /api/v1/runtime/multi-runtime/profile)
// ---------------------------------------------------------------------------

export type MultiRuntimeApplyMode =
  | "live"
  | "soft_reload"
  | "hard_restart"
  | "unsupported";

export type MultiRuntimeProfile = {
  profile_id: string;
  display_name: string;
  runtime_id: string;
  compatibility: string;
  model_id: string;
  assistant_model_id: string | null;
  cache_implementation: string | null;
  max_new_tokens: number;
  image_token_budget: number;
  enable_thinking: boolean;
  reasoning_summary_enabled: boolean;
  emotion_detection_enabled: boolean;
  emotion_response_style_enabled: boolean;
  execution_mode: "balanced" | "vision_priority" | "voice_priority";
  image_strategy: "vlm_only" | "ocr_first" | "hybrid";
  retrieval_mode: "off" | "auto" | "always";
  audio_output_mode: "off" | "text_first" | "voice_first";
  assistant_mode: "off" | "attached" | "conditional";
  economy_mode: "off" | "auto";
  precision: string;
  quantization_backend: string | null;
  device_target: string;
};

export type MultiRuntimeApplyMatrix = {
  model_id: MultiRuntimeApplyMode;
  assistant_model_id: MultiRuntimeApplyMode;
  cache_implementation: MultiRuntimeApplyMode;
  max_new_tokens: MultiRuntimeApplyMode;
  image_token_budget: MultiRuntimeApplyMode;
  enable_thinking: MultiRuntimeApplyMode;
  reasoning_summary_enabled: MultiRuntimeApplyMode;
  emotion_detection_enabled: MultiRuntimeApplyMode;
  emotion_response_style_enabled: MultiRuntimeApplyMode;
  execution_mode: MultiRuntimeApplyMode;
  image_strategy: MultiRuntimeApplyMode;
  retrieval_mode: MultiRuntimeApplyMode;
  audio_output_mode: MultiRuntimeApplyMode;
  assistant_mode: MultiRuntimeApplyMode;
  economy_mode: MultiRuntimeApplyMode;
  precision: MultiRuntimeApplyMode;
  quantization_backend: MultiRuntimeApplyMode;
  device_target: MultiRuntimeApplyMode;
};

export type MultiRuntimeSupportedOptions = {
  cache_implementation: (string | null)[];
  precision: string[];
  device_target: string[];
  quantization_backend: (string | null)[];
  execution_mode: string[];
  image_strategy: string[];
  retrieval_mode: string[];
  audio_output_mode: string[];
  assistant_mode: string[];
  economy_mode: string[];
};

export type MultiRuntimeProfileResponse = {
  runtime_id: string;
  profile: MultiRuntimeProfile;
  apply_matrix: MultiRuntimeApplyMatrix;
  supported_options: MultiRuntimeSupportedOptions;
  daemon_reachable: boolean;
};

export type MultiRuntimeProfileUpdateRequest = {
  model_id?: string | null;
  assistant_model_id?: string | null;
  cache_implementation?: string | null;
  max_new_tokens?: number | null;
  image_token_budget?: number | null;
  enable_thinking?: boolean | null;
  reasoning_summary_enabled?: boolean | null;
  emotion_detection_enabled?: boolean | null;
  emotion_response_style_enabled?: boolean | null;
  execution_mode?: "balanced" | "vision_priority" | "voice_priority" | null;
  image_strategy?: "vlm_only" | "ocr_first" | "hybrid" | null;
  retrieval_mode?: "off" | "auto" | "always" | null;
  audio_output_mode?: "off" | "text_first" | "voice_first" | null;
  assistant_mode?: "off" | "attached" | "conditional" | null;
  economy_mode?: "off" | "auto" | null;
  precision?: string | null;
  quantization_backend?: string | null;
  device_target?: string | null;
};

export type MultiRuntimeFieldRejection = {
  field: string;
  value: unknown;
  reason: string;
  detail: string;
};

export type MultiRuntimeProfileUpdateResponse = {
  accepted: Record<string, unknown>;
  rejected: MultiRuntimeFieldRejection[];
  required_apply_mode: MultiRuntimeApplyMode;
  applied: boolean;
  message: string;
};

async function systemApiFetch<T>(
  apiBaseUrl: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${apiBaseUrl}${path}`;
  const resp = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    const detail = text ? `: ${text}` : "";
    throw new Error(`System API ${path} → ${resp.status}${detail}`);
  }
  return resp.json() as Promise<T>;
}

export const getMultiRuntimeProfile = (
  apiBaseUrl: string,
): Promise<MultiRuntimeProfileResponse> =>
  systemApiFetch<MultiRuntimeProfileResponse>(
    apiBaseUrl,
    "/api/v1/runtime/multi-runtime/profile",
  );

export const updateMultiRuntimeProfile = (
  apiBaseUrl: string,
  update: MultiRuntimeProfileUpdateRequest,
): Promise<MultiRuntimeProfileUpdateResponse> =>
  systemApiFetch<MultiRuntimeProfileUpdateResponse>(
    apiBaseUrl,
    "/api/v1/runtime/multi-runtime/profile",
    { method: "POST", body: JSON.stringify(update) },
  );
