export type StatusTone = "success" | "warning" | "danger" | "neutral";

export function statusTone(status?: string | null): StatusTone {
  if (!status) return "neutral";
  const normalized = status.trim().toUpperCase();

  if (
    normalized === "COMPLETED" ||
    normalized === "DONE" ||
    normalized.includes("COMPLETE") ||
    normalized.includes("SUCCESS")
  ) {
    return "success";
  }

  if (
    normalized === "FAILED" ||
    normalized === "FAIL" ||
    normalized.includes("ERROR") ||
    normalized.includes("BLOCK")
  ) {
    return "danger";
  }

  if (
    normalized === "PROCESSING" ||
    normalized === "RUNNING" ||
    normalized === "PENDING" ||
    normalized.includes("PROGRESS") ||
    normalized.includes("DOING")
  ) {
    return "warning";
  }

  return "neutral";
}
