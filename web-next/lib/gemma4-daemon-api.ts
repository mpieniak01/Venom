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
  cache_implementation: string | null;
};

export type DaemonStatus = {
  target_model: string;
  assistant_model: string | null;
  mode: "target_only" | "target_with_assistant";
  target_loaded: boolean;
  assistant_loaded: boolean;
  params: DaemonParamsInfo;
  vram: VRAMStatus;
  pending_reload: boolean;
  reload_reason: string | null;
};

export type ReloadSignal = "none" | "soft_reload" | "hard_restart";

export type DaemonConfigRequest = {
  max_new_tokens?: number | null;
  enable_thinking?: boolean | null;
  cache_implementation?: string | null;
};

export type DaemonConfigResponse = {
  reload_signal: ReloadSignal;
  applied: DaemonParamsInfo;
  message: string;
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
    throw new Error(`Daemon ${path} → ${resp.status}${text ? `: ${text}` : ""}`);
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
