import { ApiError } from "./api-client";

export function runtimeControlErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError) || !error.data || typeof error.data !== "object") return null;
  const detail = (error.data as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

export function runtimeControlErrorHint(error: unknown, t: (key: string) => string): string | null {
  const code = runtimeControlErrorCode(error);
  if (code === "runtime_recovery_required") return t("cockpit.modelActivation.recoveryRequired");
  if (code === "runtime_busy") return t("cockpit.modelActivation.runtimeBusy");
  if (code === "remote_provider_disabled") return t("cockpit.modelActivation.providerDisabled");
  return null;
}
