import { ApiError } from "./api-client";
/** Render known validation reasons as decisions, never arbitrary upstream payloads. */
export function chatMaterialError(error: unknown, t: (key: string) => string): string | null {
  if (!(error instanceof ApiError)) return null;
  let data: unknown = error.data;
  if (typeof data === "string" && data.length <= 65536) { try { data = JSON.parse(data); } catch { return null; } }
  const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : null;
  const reason = detail && typeof detail === "object" ? (detail as { reason_code?: unknown }).reason_code : null;
  if (typeof reason !== "string") return null;
  if (reason.startsWith("omni_native_text_")) {
    if (reason.includes("context") || reason.includes("token_limit")) return t("chat2.nativeText.context");
    if (reason.includes("unsupported")) return t("chat2.nativeText.unsupported");
    if (reason.includes("changed") || reason.includes("conflict")) return t("chat2.nativeText.changed");
    if (reason.includes("not_configured")) return t("chat2.nativeText.unavailable");
    return t("chat2.nativeText.failed");
  }
  if (!reason.startsWith("material_")) return null;
  if (reason.includes("not_found") || reason.includes("unavailable")) return t("chat2.stale");
  if (reason.includes("context") || reason.includes("text_too")) return t("chat2.contextTooLarge");
  if (reason.includes("unsupported") || reason.includes("capability")) return t("chat2.incompatible");
  if (reason.includes("too_large")) return t("chat2.fileTooLarge");
  return t("chat2.error");
}
