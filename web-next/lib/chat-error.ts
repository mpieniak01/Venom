import { ApiError } from "./api-client";

function apiReason(error: ApiError): string | null {
  let data: unknown = error.data;
  if (typeof data === "string" && data.length <= 65536) {
    try { data = JSON.parse(data); } catch { return null; }
  }
  const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : null;
  const reason = detail && typeof detail === "object" ? (detail as { reason_code?: unknown }).reason_code : null;
  return typeof reason === "string" ? reason : null;
}

function nativeError(reason: string, t: (key: string) => string): string | null {
  if (!reason.startsWith("omni_native_text_")) return null;
  if (reason.includes("context") || reason.includes("token_limit")) return t("chat2.nativeText.context");
  if (reason.includes("unsupported")) return t("chat2.nativeText.unsupported");
  if (reason.includes("changed") || reason.includes("conflict")) return t("chat2.nativeText.changed");
  if (reason.includes("not_configured")) return t("chat2.nativeText.unavailable");
  return t("chat2.nativeText.failed");
}

function materialError(reason: string, t: (key: string) => string): string | null {
  if (!reason.startsWith("material_")) return null;
  if (reason.includes("not_found") || reason.includes("unavailable")) return t("chat2.stale");
  if (reason.includes("context") || reason.includes("text_too")) return t("chat2.contextTooLarge");
  if (reason.includes("unsupported") || reason.includes("capability")) return t("chat2.incompatible");
  if (reason.includes("too_large")) return t("chat2.fileTooLarge");
  return t("chat2.error");
}

/** Translate known API/local guard decisions without echoing arbitrary upstream payloads. */
export function chatMaterialError(error: unknown, t: (key: string) => string): string | null {
  let reason: string | null = null;
  if (error instanceof ApiError) reason = apiReason(error);
  else if (error instanceof Error) reason = error.message;
  if (!reason) return null;
  return nativeError(reason, t) ?? (error instanceof ApiError ? materialError(reason, t) : null);
}
